"""Retrain only when historical replay has newly known targets."""
from __future__ import annotations

from datetime import datetime

from airflow.decorators import dag, task
from airflow.exceptions import AirflowSkipException

from ml_pipeline.pipeline import (build_features, check_new_labels, evaluate,
                              publish, snapshot, train_candidate)


@dag(schedule="*/5 * * * *", start_date=datetime(2026, 1, 1), catchup=False,
     max_active_runs=1, is_paused_upon_creation=False, tags=["ml"])
def delay_retraining():
    @task
    def check() -> str:
        result = check_new_labels()
        if result is None:
            raise AirflowSkipException("no newly labeled examples")
        return result

    @task
    def make_snapshot(spec: str) -> str:
        return snapshot(spec)

    @task
    def features(path: str) -> str:
        return build_features(path)

    @task
    def train(path: str) -> str:
        return train_candidate(path)

    @task
    def score(path: str) -> str:
        return evaluate(path)

    @task
    def activate(path: str) -> bool:
        return publish(path)

    activate(score(train(features(make_snapshot(check())))))


delay_retraining()
