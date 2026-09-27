"""Delay model for the backend.

The booster predicts a correction to cur_dev_s. This module rebuilds the same
features as the submission that scored 1.0 and adds the hint back.

    from model.predictor import DelayPredictor

    predictor = DelayPredictor()
    predictor.load_schedule("validate/schedule_plan.csv")
    predictor.set_telemetry("validate/traffic.csv")
    predictor.predict(tr_id=131672, T="2026-01-06 03:35:00", cur_dev_s=274)
"""
from __future__ import annotations

from pathlib import Path

import lightgbm as lgb
import pandas as pd


try:
    from .timing import measure
    from .features import build, clean_traffic, load_schedule, predict
    from .probability import DelayProbability
except ImportError:  # running as a script from this directory
    from timing import measure
    from features import build, clean_traffic, load_schedule, predict
    from probability import DelayProbability

_RAW_COLUMNS = ["event_time", "location_valid", "lon", "lat", "speed"]


def _as_timestamp(value) -> pd.Timestamp:
    """Integers and floats are Unix seconds, matching the NDTP timestamp field."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return pd.Timestamp(value, unit="s")
    return pd.Timestamp(value)


class DelayPredictor:
    def __init__(self, model_path: str | Path | None = None):
        path = Path(model_path) if model_path else Path(__file__).with_name("model.txt")
        self.model = lgb.Booster(model_file=str(path))
        import json
        meta = path.parent / "metadata.json"
        required = meta.exists() and json.loads(meta.read_text()).get("bundle_version", 1) >= 2
        self.probability = DelayProbability.load(path.parent, required=required)
        if self.probability and self.probability.calibration["features"] != self.model.feature_name():
            raise ValueError("regressor/classifier feature mismatch")
        self.sched: dict = {}
        self._raw: dict[int, pd.DataFrame] = {}

    def load_schedule(self, path: str | Path | pd.DataFrame) -> None:
        """Planned schedule CSV: tr_id, time_begin, tt_action_item_id, manual_fill, geom (POINT)."""
        self.sched = load_schedule(path)

    def set_telemetry(self, source) -> None:
        """Replace the telemetry buffer.

        `source` is a path to traffic.csv (tr_id, event_time, location_valid, lon, lat, speed)
        or a DataFrame with those columns. Cleaning (Sheremetyevo disc, jumps over 150 km/h)
        happens at predict time, on fixes with event_time <= T.
        """
        if isinstance(source, (str, Path)):
            frame = pd.read_csv(source, usecols=["tr_id", *_RAW_COLUMNS], low_memory=False)
        else:
            frame = source.copy()
        frame["event_time"] = pd.to_datetime(frame["event_time"], format="mixed")
        self._raw = {
            int(tr): g.loc[:, _RAW_COLUMNS].reset_index(drop=True)
            for tr, g in frame.groupby("tr_id")
        }

    def add_fix(self, tr_id: int, event_time, lon: float, lat: float, speed: float,
                location_valid: bool = True) -> None:
        """Append one parsed telemetry fix. The buffer is cleaned when predict() is called."""
        tr_id = int(tr_id)
        row = pd.DataFrame([{
            "event_time": _as_timestamp(event_time),
            "location_valid": bool(location_valid),
            "lon": float(lon),
            "lat": float(lat),
            "speed": float(speed),
        }])
        prev = self._raw.get(tr_id)
        self._raw[tr_id] = pd.concat([prev, row], ignore_index=True) if prev is not None else row

    def _traffic(self) -> dict:
        return {tr: clean_traffic(g) for tr, g in self._raw.items()}

    def predict(self, tr_id: int, T, cur_dev_s: float = 0.0,
                target_stop_id: int | None = None, target_time_begin=None) -> dict:
        """Delay in seconds at the stop planned in (T+10, T+15].

        Positive means late. If target_stop_id is omitted, the target is the first
        planned stop in that window, the same rule as the labels.
        """
        tr_id = int(tr_id)
        T = _as_timestamp(T)
        schedule = self.sched.get(tr_id)
        if schedule is None:
            return {"error": f"no schedule for tr_id={tr_id}"}
        if target_stop_id is None:
            window = schedule[(schedule.time_begin > T + pd.Timedelta("10min"))
                              & (schedule.time_begin <= T + pd.Timedelta("15min"))]
            if window.empty:
                return {"error": "no planned stop in (T+10, T+15] min"}
            target_stop_id = int(window.tt_action_item_id.iloc[0])
            target_time_begin = window.time_begin.iloc[0]
        point = {"tr_id": tr_id, "T": T, "target_stop_id": int(target_stop_id),
                 "target_time_begin": pd.Timestamp(target_time_begin), "cur_dev_s": float(cur_dev_s)}
        pred = float(self.predict_points(pd.DataFrame([point]))[0])
        return {
            "tr_id": tr_id,
            "T": str(T),
            "target_stop_id": int(target_stop_id),
            "target_time_begin": str(_as_timestamp(target_time_begin)),
            "cur_dev_s": float(cur_dev_s),
            "predicted_delay_s": round(pred, 1),
        }

    def predict_points(self, points: pd.DataFrame):
        """Batch predict. `points` needs tr_id, T, target_stop_id, target_time_begin, cur_dev_s."""
        X = build(points, self.sched, self._traffic())
        return predict(self.model, X)

    def predict_points_with_probability(self, points: pd.DataFrame):
        with measure("traffic_clean_ms"):
            traffic = self._traffic()
        with measure("features_ms"):
            X = build(points, self.sched, traffic)
        with measure("regression_ms"):
            delays = predict(self.model, X)
        with measure("probability_ms"):
            probabilities = self.probability.predict(X) if self.probability else [None] * len(X)
        return delays, probabilities
