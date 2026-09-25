"""Historical replay and retraining stages called by the Airflow DAG."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from pathlib import Path

import lightgbm as lgb
import pandas as pd

from training import train as ml

DATA = Path(os.getenv("DATASET_DIR", "/dataset"))
ARTIFACTS = Path(os.getenv("MODEL_DIR", "/models"))
WORK = Path(os.getenv("PIPELINE_WORK_DIR", "/pipeline-work"))
SPEED = float(os.getenv("TRAIN_REPLAY_SPEED", "6"))


def _clock() -> pd.Timestamp:
    WORK.mkdir(parents=True, exist_ok=True)
    anchor_file = WORK / "replay_anchor.json"
    if anchor_file.exists():
        anchor = json.loads(anchor_file.read_text())
    else:
        schedule = pd.read_csv(DATA / "train/schedule.csv", usecols=["time_begin"])
        dates = pd.to_datetime(schedule.time_begin, format="mixed")
        start = dates.min() + (dates.max() - dates.min()) / 2
        anchor = {"start": start.isoformat(), "wall": dt.datetime.now(dt.timezone.utc).isoformat()}
        tmp = anchor_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(anchor))
        os.replace(tmp, anchor_file)
    elapsed = dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(anchor["wall"])
    return pd.Timestamp(anchor["start"]) + elapsed * SPEED


def check_new_labels() -> str | None:
    cutoff = _clock()
    labels = pd.read_csv(DATA / "labels/labels_train.csv")
    known = labels[pd.to_datetime(labels.target_time_begin, format="mixed") <= cutoff]
    if known.empty:
        return None
    identifier = hashlib.sha256("\n".join(sorted(known.sample_id.astype(str))).encode()).hexdigest()[:16]
    if (WORK / identifier / "processed.json").exists():
        return None
    active = ARTIFACTS / "active.json"
    if active.exists() and json.loads(active.read_text()).get("dataset_id") == identifier:
        return None
    return json.dumps({"cutoff": cutoff.isoformat(), "dataset_id": identifier})


def snapshot(spec: str) -> str:
    params = json.loads(spec)
    path = WORK / params["dataset_id"]
    path.mkdir(parents=True, exist_ok=True)
    if (path / "snapshot.json").exists():
        return str(path)
    cutoff = pd.Timestamp(params["cutoff"])
    schedule = pd.read_csv(DATA / "train/schedule.csv")
    fact = pd.to_datetime(schedule.time_fact_begin, format="mixed")
    schedule.loc[fact > cutoff, "time_fact_begin"] = None
    traffic = pd.read_csv(DATA / "train/traffic.csv")
    traffic = traffic[pd.to_datetime(traffic.event_time, format="mixed") <= cutoff]
    labels = pd.read_csv(DATA / "labels/labels_train.csv")
    labels = labels[pd.to_datetime(labels.target_time_begin, format="mixed") <= cutoff]
    schedule.to_csv(path / "schedule.csv", index=False)
    traffic.to_csv(path / "traffic.csv", index=False)
    labels.to_csv(path / "labels.csv", index=False)
    (path / "snapshot.json").write_text(json.dumps(params))
    return str(path)


def build_features(path: str) -> str:
    root = Path(path)
    if (root / "features.pkl").exists():
        return path
    sched = ml.load_schedule(root / "schedule.csv")
    traffic = ml.load_traffic(root / "traffic.csv")
    labels = pd.read_csv(root / "labels.csv")
    X = ml.build(labels, sched, traffic)
    # Generated points use only stops whose fact is known by the replay cutoff.
    completed = {tr: group[group.time_fact_begin.notna()].reset_index(drop=True)
                 for tr, group in sched.items()}
    completed = {tr: group for tr, group in completed.items() if len(group) >= 2}
    generated = ml.generate_points(completed) if completed else pd.DataFrame()
    if not generated.empty:
        X = pd.concat([X, ml.build(generated, sched, traffic)], ignore_index=True)
        y = pd.concat([labels.target_delay_s, generated.target_delay_s], ignore_index=True)
    else:
        y = labels.target_delay_s.reset_index(drop=True)
    pd.to_pickle({"X": X, "y": y}, root / "features.pkl")
    return path


def train_candidate(path: str) -> str:
    root = Path(path)
    if (root / "model.txt").exists():
        return path
    bundle = pd.read_pickle(root / "features.pkl")
    model = ml.fit(bundle["X"], bundle["y"])
    model.save_model(str(root / "model.txt"))
    return path


def evaluate(path: str) -> str:
    root = Path(path)
    if (root / "evaluation.json").exists():
        return path
    test_labels = pd.read_csv(DATA / "labels/labels_test.csv")
    X = ml.build(test_labels, ml.load_schedule(DATA / "test/schedule.csv"),
                 ml.load_traffic(DATA / "test/traffic.csv"))
    y = test_labels.target_delay_s
    candidate = lgb.Booster(model_file=str(root / "model.txt"))
    candidate_mae = ml.mae(y, ml.predict(candidate, X))
    active = ARTIFACTS / "active.json"
    if active.exists():
        current = json.loads(active.read_text())
        previous = lgb.Booster(model_file=str(ARTIFACTS / current["version"] / "model.txt"))
        reference_mae = ml.mae(y, ml.predict(previous, X))
    else:
        reference_mae = ml.mae(y, X.cur_dev_s)
    (root / "evaluation.json").write_text(json.dumps({"candidate_mae": candidate_mae,
                                                        "reference_mae": reference_mae}))
    return path


def publish(path: str) -> bool:
    root = Path(path)
    metrics = json.loads((root / "evaluation.json").read_text())
    if metrics["candidate_mae"] > metrics["reference_mae"]:
        (root / "processed.json").write_text(json.dumps({"published": False, "metrics": metrics}))
        return False
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    version = root.name
    target = ARTIFACTS / version
    target.mkdir(exist_ok=True)
    (target / "model.txt").write_bytes((root / "model.txt").read_bytes())
    metadata = {"version": version, "dataset_id": version, "metrics": metrics,
                "features": ml.FEATURES}
    (target / "metadata.json").write_text(json.dumps(metadata))
    pointer = ARTIFACTS / "active.json"
    tmp = ARTIFACTS / "active.tmp"
    tmp.write_text(json.dumps(metadata))
    os.replace(tmp, pointer)
    (root / "processed.json").write_text(json.dumps({"published": True, "metrics": metrics}))
    return True
