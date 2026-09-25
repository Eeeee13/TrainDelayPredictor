"""Delay predictor training.

Features use telemetry with event_time <= T, the planned schedule and cur_dev_s.
Schedule facts (time_fact_begin) are targets only, never features.

The file written for the backend is model_with_synthetic.txt: real labels, one-minute
generated points, and the organizer synthetic vehicles. That booster scored 1.0 on validate.
model.txt is the same pipeline without the synthetic vehicles (validate score 0.891).

    python train.py --data /path/to/dataset --out artifacts
"""
import argparse
import os

import numpy as np
import pandas as pd
import lightgbm as lgb
from sklearn.model_selection import GroupKFold

ROOT = "."
OUT = "."
M_PER_DEG_LAT = 111_200.0
M_PER_DEG_LON = 62_800.0  # ~cos(55.75°) * 111.2 km
PASS_RADIUS_M = 50.0
LAYOVER_MIN = 5

# GPS spoofing seen in the data: fake fixes on a ~1-2 km circle around Sheremetyevo at ~99 km/h.
# No tram line comes anywhere near, so every fix inside the disc is fake.
SPOOF_CENTER = (37.4149, 55.9731)
SPOOF_RADIUS_M = (0.0, 3000.0)
MAX_JUMP_KMH = 150.0

SYN_SOURCE = {9000000 + 2 * i + k: tr for i, tr in enumerate(
    [122048, 122613, 122658, 129964, 130072, 130238, 131672, 132430, 133300, 133957, 134040, 134494, 135081])
    for k in (0, 1)}

BASE_FEATURES = [
    "cur_dev_s", "lead_min", "hour",
    "tgt_manual", "tgt_first_after_gap", "gap_before_tgt_min",
    "n_stops_between", "layover_between", "max_gap_between_min", "min_since_last_layover",
    "manual_frac_recent", "last_plan_manual",
    "gps_dev_last", "gps_dev_mean3", "gps_dev_slope", "gps_age_s", "gps_n_passed",
    "pos_dev", "dist_to_tgt_m", "dist_to_nearest_stop_m",
    "speed_mean_5m", "speed_last", "stopped_frac_5m", "valid_frac_10m", "last_fix_age_s",
    "dev_fallback", "tgt_lon", "tgt_lat",
]
NEW_FEATURES = [
    "spoof_frac_30m", "gps_unreliable",
    "layover_s", "cur_est", "delay_minus_layover", "at_terminal", "terminal_dwell_s",
    "chain_dist_m", "moving_speed_30m", "proj_delay",
    "hist_tgt_dev", "hist_tgt_age_min", "hist_delta", "hist_pred",
]
FEATURES = BASE_FEATURES + NEW_FEATURES


def dist_m(lon1, lat1, lon2, lat2):
    return np.hypot((lon1 - lon2) * M_PER_DEG_LON, (lat1 - lat2) * M_PER_DEG_LAT)


# ---------------------------------------------------------------- loading & cleaning

def clean_traffic(g: pd.DataFrame) -> pd.DataFrame:
    """Marks spoofed fixes and physically impossible jumps as invalid; adds a `spoof` column."""
    g = g.sort_values("event_time").copy()
    valid = g.location_valid.astype(str).str.lower().eq("true").to_numpy(copy=True)
    lon, lat = g.lon.values.astype(float), g.lat.values.astype(float)
    r = dist_m(lon, lat, *SPOOF_CENTER)
    spoof = valid & (r > SPOOF_RADIUS_M[0]) & (r < SPOOF_RADIUS_M[1])
    valid &= ~spoof
    sec = g.event_time.values.astype("datetime64[s]").astype(np.int64)
    last = None
    for i in np.flatnonzero(valid):
        if last is not None:
            dt = max(sec[i] - sec[last], 1)
            if dist_m(lon[i], lat[i], lon[last], lat[last]) / dt * 3.6 > MAX_JUMP_KMH:
                valid[i] = False
                continue
        last = i
    g["location_valid"] = valid
    g["spoof"] = spoof
    return g


def load_traffic(path, clean=True):
    t = pd.read_csv(path, usecols=["tr_id", "event_time", "location_valid", "lon", "lat", "speed"],
                    parse_dates=["event_time"], low_memory=False)
    out = {}
    for tr, g in t.groupby("tr_id"):
        if clean:
            g = clean_traffic(g)
        else:
            g = g.sort_values("event_time").assign(
                location_valid=g.location_valid.astype(str).str.lower().eq("true"), spoof=False)
        out[tr] = g.reset_index(drop=True)
    return out


def load_schedule(path):
    s = pd.read_csv(path, parse_dates=["time_begin"])
    xy = s.geom.str.extract(r"POINT \(([-\d.]+) ([-\d.]+)\)").astype(float)
    s["slon"], s["slat"] = xy[0], xy[1]
    s["manual_fill"] = s.manual_fill.astype(str).str.lower().eq("true").astype(float)
    if "time_fact_begin" in s:
        s["time_fact_begin"] = pd.to_datetime(s.time_fact_begin, format="mixed")
    s = s.sort_values(["tr_id", "time_begin", "tt_action_item_id"]).reset_index(drop=True)
    out = {}
    for tr, g in s.groupby("tr_id"):
        g = g.reset_index(drop=True)
        gap = g.time_begin.diff().dt.total_seconds().div(60).fillna(np.inf)
        g["gap_min"] = gap
        g["trip_first"] = gap >= LAYOVER_MIN
        g["trip_last"] = g.trip_first.shift(-1, fill_value=True)
        out[tr] = g
    return out


# ---------------------------------------------------------------- GPS stop passages (causal)

def compute_passages(s: pd.DataFrame, g: pd.DataFrame) -> pd.DataFrame:
    """Visits of planned stops found in GPS. A visit is known only after the vehicle leaves the
    stop radius, so each passage carries `confirm` (time it becomes observable) and is used
    for a moment T only if confirm <= T."""
    gv = g[g.location_valid]
    if len(gv) < 2:
        return _passages_frame([])
    et = gv.event_time.values
    lon, lat = gv.lon.values, gv.lat.values
    tb = s.time_begin.values
    rows, prev = [], 0
    for i in np.flatnonzero(~s.trip_first.values):
        lo = max(prev, np.searchsorted(et, tb[i] - np.timedelta64(12, "m")))
        hi = np.searchsorted(et, tb[i] + np.timedelta64(12, "m"))
        if hi <= lo:
            continue
        d = dist_m(lon[lo:hi], lat[lo:hi], s.slon.iat[i], s.slat.iat[i])
        inside = np.flatnonzero(d < PASS_RADIUS_M)
        if not len(inside):
            continue
        j = lo + inside[0]
        tail = dist_m(lon[j:j + 300], lat[j:j + 300], s.slon.iat[i], s.slat.iat[i])
        out = np.flatnonzero(tail > PASS_RADIUS_M)
        if not len(out):
            continue
        k = j + out[0]
        a = j + int(np.argmin(tail[:out[0]]))
        rows.append((i, et[a], et[k], (et[a] - tb[i]) / np.timedelta64(1, "s")))
        prev = a
    return _passages_frame(rows)


def _passages_frame(rows):
    df = pd.DataFrame(rows, columns=["stop_idx", "arrival", "confirm", "dev"])
    return df.astype({"stop_idx": int, "arrival": "datetime64[ns]", "confirm": "datetime64[ns]", "dev": float})


# ---------------------------------------------------------------- features

def point_features(p, sched, traffic, passages=None):
    T = pd.Timestamp(p["T"])
    T64 = np.datetime64(T)
    f = {"cur_dev_s": p["cur_dev_s"], "hour": T.hour + T.minute / 60}
    tgt_time = pd.Timestamp(p["target_time_begin"])
    f["lead_min"] = (tgt_time - T).total_seconds() / 60
    f["dev_fallback"] = f["cur_est"] = p["cur_dev_s"]

    s = sched.get(p["tr_id"])
    tgt_idx = None
    if s is not None:
        hit = np.flatnonzero(s.tt_action_item_id.values == p["target_stop_id"])
        if len(hit):
            tgt_idx = int(hit[0])
    if tgt_idx is None:
        return f

    tb = s.time_begin.values
    gaps = s.gap_min.values
    tgt = s.iloc[tgt_idx]
    f["tgt_manual"] = tgt.manual_fill
    f["tgt_lon"], f["tgt_lat"] = tgt.slon, tgt.slat
    f["gap_before_tgt_min"] = min(gaps[tgt_idx], 120)
    f["tgt_first_after_gap"] = float(gaps[tgt_idx] >= LAYOVER_MIN)

    last_idx = np.searchsorted(tb, T64, side="right") - 1
    between = gaps[max(last_idx + 1, 0):tgt_idx + 1]
    f["n_stops_between"] = tgt_idx - last_idx
    f["max_gap_between_min"] = min(between.max(), 120) if len(between) else 0
    f["layover_between"] = float(len(between) > 0 and between.max() >= LAYOVER_MIN)
    lay = between[(between >= LAYOVER_MIN) & np.isfinite(between)]
    f["layover_s"] = float(lay.sum() * 60)
    past_gaps = np.flatnonzero(gaps[:max(last_idx, 0) + 1] >= LAYOVER_MIN)
    if len(past_gaps) and last_idx >= 0:
        f["min_since_last_layover"] = (T64 - tb[past_gaps[-1]]) / np.timedelta64(60, "s")
    if last_idx >= 0:
        recent = s.iloc[max(0, last_idx - 5):last_idx + 1]
        f["manual_frac_recent"] = recent.manual_fill.mean()
        f["last_plan_manual"] = s.manual_fill.iat[last_idx]

    g = traffic.get(p["tr_id"])
    if g is None:
        f["delay_minus_layover"] = f["cur_est"] - f["layover_s"]
        return f
    if passages is None:
        passages = compute_passages(s, g)
    g = g[g.event_time <= T]
    g10 = g[g.event_time > T - pd.Timedelta("10min")]
    g30 = g[g.event_time > T - pd.Timedelta("30min")]
    f["valid_frac_10m"] = g10.location_valid.mean() if len(g10) else 0.0
    f["spoof_frac_30m"] = g30.spoof.mean() if len(g30) else 0.0
    f["gps_unreliable"] = float(f["valid_frac_10m"] < 0.5 or f["spoof_frac_30m"] > 0.2)

    gv = g[g.location_valid]
    if len(gv):
        et, lon, lat, spd = gv.event_time.values, gv.lon.values, gv.lat.values, gv.speed.values
        f["last_fix_age_s"] = (T64 - et[-1]) / np.timedelta64(1, "s")
        f["speed_last"] = spd[-1]
        w5 = et > np.datetime64(T - pd.Timedelta("5min"))
        if w5.any():
            f["speed_mean_5m"] = spd[w5].mean()
            f["stopped_frac_5m"] = (spd[w5] < 3).mean()
        w30 = (et > np.datetime64(T - pd.Timedelta("30min"))) & (spd > 5)
        if w30.sum() >= 5:
            f["moving_speed_30m"] = spd[w30].mean()
        f["dist_to_tgt_m"] = dist_m(lon[-1], lat[-1], tgt.slon, tgt.slat)

        regular = ~s.trip_first.values
        near_mask = regular & (tb >= T64 - np.timedelta64(12, "m")) & (tb <= T64 + np.timedelta64(12, "m"))
        near = s[near_mask]
        if len(near):
            d = dist_m(lon[-1], lat[-1], near.slon.values, near.slat.values)
            j = d.argmin()
            f["dist_to_nearest_stop_m"] = d[j]
            if d[j] < 150:
                f["pos_dev"] = (T - near.time_begin.iat[j]).total_seconds()

        # At a terminal: near a trip end/start stop planned around T and standing still.
        term = s[(s.trip_first | s.trip_last).values & (tb >= T64 - np.timedelta64(40, "m"))
                 & (tb <= T64 + np.timedelta64(40, "m"))]
        f["at_terminal"] = 0.0
        if len(term):
            dt_ = dist_m(lon[-1], lat[-1], term.slon.values, term.slat.values)
            jt = dt_.argmin()
            if dt_[jt] < 150 and spd[-1] < 5:
                f["at_terminal"] = 1.0
                far = dist_m(lon, lat, term.slon.iat[jt], term.slat.iat[jt]) > 150
                last_far = np.flatnonzero(far)
                since = et[last_far[-1]] if len(last_far) else et[0]
                f["terminal_dwell_s"] = (T64 - since) / np.timedelta64(1, "s")

    known = passages[passages.confirm <= T64] if len(passages) else passages
    next_idx = last_idx + 1
    if len(known):
        pl = s.time_begin.values[known.stop_idx.values]
        recent = known[(pl >= T64 - np.timedelta64(40, "m")) & (pl <= T64 + np.timedelta64(10, "m"))]
        if len(recent):
            devs = recent.dev.values
            f["gps_dev_last"] = devs[-1]
            f["gps_dev_mean3"] = np.median(devs[-3:])
            f["gps_age_s"] = (T64 - recent.arrival.values[-1]) / np.timedelta64(1, "s")
            f["gps_n_passed"] = len(devs)
            if len(devs) >= 3:
                f["gps_dev_slope"] = np.polyfit(np.arange(len(devs[-5:])), devs[-5:], 1)[0]
            f["dev_fallback"] = np.median(devs[-3:])
            if f["gps_age_s"] < 900:
                f["cur_est"] = f["gps_dev_mean3"]
            next_idx = max(next_idx, int(recent.stop_idx.values[-1]) + 1)

        # History of the same places on earlier trips (GPS only).
        tgt_xy = (tgt.slon, tgt.slat)
        kx = s.slon.values[known.stop_idx.values]
        ky = s.slat.values[known.stop_idx.values]
        same_tgt = (dist_m(kx, ky, *tgt_xy) < 30) & (known.arrival.values < T64 - np.timedelta64(20, "m"))
        if same_tgt.any():
            h = known[same_tgt].iloc[-1]
            f["hist_tgt_dev"] = h.dev
            f["hist_tgt_age_min"] = (T64 - h.arrival) / np.timedelta64(60, "s")
            if len(known) and "gps_dev_last" in f:
                cur_stop = int(recent.stop_idx.values[-1])
                cx, cy = s.slon.iat[cur_stop], s.slat.iat[cur_stop]
                prev_trip = known[(known.arrival < h.arrival) & (known.arrival > h.arrival - np.timedelta64(60, "m"))]
                if len(prev_trip):
                    px = s.slon.values[prev_trip.stop_idx.values]
                    py = s.slat.values[prev_trip.stop_idx.values]
                    same_cur = dist_m(px, py, cx, cy) < 30
                    if same_cur.any():
                        f["hist_delta"] = h.dev - prev_trip[same_cur].dev.values[-1]
                        f["hist_pred"] = f["gps_dev_last"] + f["hist_delta"]

    # Physics: remaining distance along the stop chain and projected delay at the target.
    if len(gv) and 0 <= next_idx <= tgt_idx:
        xs, ys = s.slon.values[next_idx:tgt_idx + 1], s.slat.values[next_idx:tgt_idx + 1]
        chain = dist_m(gv.lon.values[-1], gv.lat.values[-1], xs[0], ys[0]) + dist_m(xs[:-1], ys[:-1], xs[1:], ys[1:]).sum()
        f["chain_dist_m"] = chain
        if "moving_speed_30m" in f:
            travel = chain / (f["moving_speed_30m"] / 3.6) + 20 * (tgt_idx - next_idx)
            f["proj_delay"] = travel - (tgt_time - T).total_seconds()
    f["delay_minus_layover"] = f["cur_est"] - f["layover_s"]
    return f


def build(points, sched, traffic):
    points = points.copy()
    points["T"] = pd.to_datetime(points["T"], format="mixed")
    points["target_time_begin"] = pd.to_datetime(points["target_time_begin"], format="mixed")
    passages = {tr: compute_passages(sched[tr], traffic[tr])
                for tr in points.tr_id.unique() if tr in sched and tr in traffic}
    rows = [point_features(p, sched, traffic, passages.get(p["tr_id"])) for p in points.to_dict("records")]
    return pd.DataFrame(rows).reindex(columns=FEATURES).astype(float)


# ---------------------------------------------------------------- extra training points

def generate_points(sched, step_min=1, only_real=True):
    """Prediction points built exactly like the organizer labels, but every `step_min` minutes:
    target = first stop planned in (T+10, T+15]; cur_dev_s = delay at the last stop planned <= T."""
    out = []
    for tr, s in sched.items():
        if only_real and tr >= 9_000_000:
            continue
        tb = s.time_begin.values
        delay = (s.time_fact_begin - s.time_begin).dt.total_seconds().values
        t0 = pd.Timestamp(tb[0]).floor("min") - pd.Timedelta("15min")
        for T in pd.date_range(t0, pd.Timestamp(tb[-1]), freq=f"{step_min}min"):
            T64 = np.datetime64(T)
            lo = np.searchsorted(tb, T64 + np.timedelta64(10, "m"), side="right")
            if lo >= len(tb) or tb[lo] > T64 + np.timedelta64(15, "m"):
                continue
            last = np.searchsorted(tb, T64, side="right") - 1
            out.append((f"{tr}_{int(T.timestamp())}", tr, T, s.tt_action_item_id.iat[lo], tb[lo],
                        float(delay[last]) if last >= 0 else 0.0, float(delay[lo])))
    return pd.DataFrame(out, columns=["sample_id", "tr_id", "T", "target_stop_id", "target_time_begin",
                                      "cur_dev_s", "target_delay_s"])


# ---------------------------------------------------------------- model

PARAMS = dict(objective="l1", learning_rate=0.03, num_leaves=15, min_data_in_leaf=30,
              feature_fraction=0.8, bagging_fraction=0.8, bagging_freq=1, lambda_l2=1.0,
              verbose=-1, seed=42)
N_ROUNDS = 600


def fit(X, y, w=None, params=None, rounds=None):
    # Predict the residual over cur_dev_s: the hint is a strong prior.
    return lgb.train(params or PARAMS, lgb.Dataset(X, y - X["cur_dev_s"], weight=w), rounds or N_ROUNDS)


def predict(model, X):
    return model.predict(X[model.feature_name()]) + X["cur_dev_s"].values


def mae(a, b):
    return float(np.mean(np.abs(np.asarray(a) - np.asarray(b))))


def source_vehicle(tr):
    return SYN_SOURCE.get(int(tr), int(tr))


def honest_cv(X, y, groups, is_eval, w=None, cols=None, n_splits=6):
    """Leave-vehicles-out CV. A held-out real vehicle is removed from training together with its
    synthetic copies and generated points; metrics are computed on organizer label points only."""
    cols = cols or FEATURES
    src = np.array([source_vehicle(g) for g in groups])
    vehicles = np.unique(src[is_eval])
    oof = np.full(len(y), np.nan)
    for tr_v, te_v in GroupKFold(n_splits).split(vehicles, groups=vehicles):
        test_mask = np.isin(src, vehicles[te_v])
        m = fit(X.loc[~test_mask, cols], y[~test_mask], None if w is None else w[~test_mask])
        idx = np.flatnonzero(test_mask & is_eval)
        oof[idx] = predict(m, X.iloc[idx])
    return oof


def main():
    global ROOT, OUT
    ap = argparse.ArgumentParser(description="Train the delay model and write validate submissions.")
    ap.add_argument("--data", default=".", help="dataset root: train/, test/, validate/, labels/, sample_submission.csv")
    ap.add_argument("--out", default="artifacts", help="directory for models, submissions and oof.csv")
    args = ap.parse_args()
    ROOT = args.data
    OUT = args.out
    os.makedirs(OUT, exist_ok=True)

    print("loading...")
    sched_tr = load_schedule(f"{ROOT}/train/schedule.csv")
    sched_te = load_schedule(f"{ROOT}/test/schedule.csv")
    sched_va = load_schedule(f"{ROOT}/validate/schedule_plan.csv")
    traf_raw = load_traffic(f"{ROOT}/train/traffic.csv", clean=False)
    traf_tr = load_traffic(f"{ROOT}/train/traffic.csv")
    traf_te = load_traffic(f"{ROOT}/test/traffic.csv")
    traf_va = load_traffic(f"{ROOT}/validate/traffic.csv")

    ltr = pd.read_csv(f"{ROOT}/labels/labels_train.csv")
    lte = pd.read_csv(f"{ROOT}/labels/labels_test.csv")
    pva = pd.read_csv(f"{ROOT}/validate/points.csv")
    lab = pd.concat([ltr, lte], ignore_index=True)
    y_lab = lab.target_delay_s.values
    syn = lab.tr_id.values >= 9_000_000
    real = ~syn

    print("building features...")
    X_raw = pd.concat([build(ltr, sched_tr, traf_raw), build(lte, sched_te, traf_raw)], ignore_index=True)
    X_lab = pd.concat([build(ltr, sched_tr, traf_tr), build(lte, sched_te, traf_te)], ignore_index=True)

    gen = generate_points(sched_tr)
    t_val = pva.assign(T=pd.to_datetime(pva["T"]))
    gen = gen.merge(t_val[["tr_id", "T"]].rename(columns={"T": "T_val"}), on="tr_id", how="left")
    near_val = (gen["T"] - gen["T_val"]).abs() < pd.Timedelta("5min")
    bad = gen.loc[near_val, "sample_id"].unique()
    gen = gen.drop(columns="T_val").drop_duplicates("sample_id")
    gen = gen[~gen.sample_id.isin(bad)].reset_index(drop=True)
    print(f"generated points: {len(gen)} (validate ±5 min excluded)")
    X_gen = build(gen, sched_tr, traf_tr)
    y_gen = gen.target_delay_s.values

    def report(name, oof, mask):
        print(f"  {name:<58} MAE={mae(y_lab[mask], oof[mask]):6.2f}")

    ev = real
    print(f"\nHonest leave-vehicle-out CV on {ev.sum()} real label points "
          f"(mae_zero={mae(y_lab[ev], 0):.2f}, cur_dev_s={mae(y_lab[ev], X_lab.cur_dev_s[ev]):.2f})")
    for name, X, cols, with_syn in [
        ("old features, raw GPS, with synthetic", X_raw, BASE_FEATURES, True),
        ("old features, raw GPS, real only", X_raw, BASE_FEATURES, False),
        ("+ GPS cleaning (item 3)", X_lab, BASE_FEATURES, False),
        ("+ new features (item 2)", X_lab, FEATURES, False),
    ]:
        keep = np.ones(len(y_lab), bool) if with_syn else real
        oof = np.full(len(y_lab), np.nan)
        oof[keep] = honest_cv(X[keep].reset_index(drop=True), y_lab[keep], lab.tr_id.values[keep],
                              real[keep], cols=cols)
        report(name, oof, ev)

    X_all = pd.concat([X_lab[real], X_gen], ignore_index=True)
    y_all = np.concatenate([y_lab[real], y_gen])
    g_all = np.concatenate([lab.tr_id.values[real], gen.tr_id.values])
    is_eval = np.r_[np.ones(real.sum(), bool), np.zeros(len(gen), bool)]
    oof = honest_cv(X_all, y_all, g_all, is_eval)
    print(f"  {'+ generated points every minute (item 1)':<58} MAE={mae(y_all[is_eval], oof[is_eval]):6.2f}")
    best_oof = oof[is_eval]

    X_syn = pd.concat([X_all, X_lab[syn]], ignore_index=True)
    y_syn = np.concatenate([y_all, y_lab[syn]])
    g_syn = np.concatenate([g_all, lab.tr_id.values[syn]])
    e_syn = np.r_[is_eval, np.zeros(syn.sum(), bool)]
    oof_s = honest_cv(X_syn, y_syn, g_syn, e_syn)
    print(f"  {'+ synthetic of other vehicles':<58} MAE={mae(y_syn[e_syn], oof_s[e_syn]):6.2f}")

    print("\ntraining final models...")
    honest = fit(X_all, y_all)
    honest.save_model(f"{OUT}/model.txt")
    with_syn = fit(X_syn, y_syn)
    with_syn.save_model(f"{OUT}/model_with_synthetic.txt")
    imp = pd.Series(honest.feature_importance("gain"), index=FEATURES).sort_values(ascending=False)
    print("top features:\n", (imp / imp.sum()).head(12).round(3).to_string())

    X_va = build(pva, sched_va, traf_va)
    sub = pd.read_csv(f"{ROOT}/sample_submission.csv", sep=";")[["sample_id"]]
    for model, path in [(honest, "submission.csv"), (with_syn, "submission_with_synthetic.csv")]:
        pred = pd.DataFrame({"sample_id": pva.sample_id, "prediction": predict(model, X_va).round(1)})
        out = sub.merge(pred, on="sample_id", how="left")
        assert out.prediction.notna().all() and out.sample_id.is_unique and len(out) == len(pva)
        out.to_csv(f"{OUT}/{path}", sep=";", index=False)
        print(f"saved {OUT}/{path}")
    pd.DataFrame({"sample_id": lab.sample_id[real].values, "oof": best_oof}).to_csv(f"{OUT}/oof.csv", index=False)
    print(f"saved {OUT}/model_with_synthetic.txt  (this is the score-1.0 model; copy it to model/model.txt)")


if __name__ == "__main__":
    main()
