import datetime as dt
from unittest.mock import patch
from scripts.replay_csv import csv_timestamp, replay_wait
from app.core.time import utc_naive


def test_csv_time_roundtrip_matches_training_hour():
    value=dt.datetime(2026,1,6,8)
    encoded=dt.datetime.fromisoformat(csv_timestamp(value))
    assert utc_naive(encoded)==dt.datetime(2026,1,6,5)
    assert encoded.utcoffset()==dt.timedelta(hours=3)


def test_replay_accounts_for_http_time_and_catches_up():
    start=dt.datetime(2026,1,6,8)
    with patch('scripts.replay_csv.time.monotonic',return_value=105):
        assert replay_wait(start+dt.timedelta(minutes=3),start,100,30)==1
    with patch('scripts.replay_csv.time.monotonic',return_value=110):
        assert replay_wait(start+dt.timedelta(minutes=3),start,100,30)==0
    with patch('scripts.replay_csv.time.monotonic',return_value=100):
        assert replay_wait(start+dt.timedelta(minutes=30),start,100,30)==60
