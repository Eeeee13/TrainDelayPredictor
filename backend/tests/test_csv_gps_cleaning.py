from app.adapters.csv_telemetry_adapter import read_traffic_csv


def test_replay_filters_spoof_and_jumps_without_dropping_records(tmp_path):
    path = tmp_path / 'traffic.csv'
    path.write_text(
        'tr_id,event_time,location_valid,lon,lat,speed\n'
        '7,2026-01-06 06:00:45,True,37.5002,55.7,12\n'
        '7,2026-01-06 06:00:00,True,37.5,55.7,12\n'
        '8,2026-01-06 06:00:01,True,37.8,55.8,12\n'
        '7,2026-01-06 06:00:15,True,37.42,55.9731,99\n'
        '7,2026-01-06 06:00:30,True,37.8,55.7,12\n'
        '7,2026-01-06 06:01:00,False,37.5003,55.7,12\n'
        '7,2026-01-06 06:01:15,True,,,12\n'
    )
    points = list(read_traffic_csv(str(path)))
    assert len(points) == 7
    assert [p.location_valid for p in points] == [True, True, False, False, True, False, False]
    assert points[4].longitude == 37.5002
    assert all(p.latitude == p.longitude == 0 for p in points if not p.location_valid)
