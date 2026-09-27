import datetime as dt
import struct

from app.adapters.csv_telemetry_adapter import read_schedule_csv, read_traffic_csv
from app.ndtp.server import NAV, crc16, decode_frame


def test_organizer_csv_columns(tmp_path):
    schedule = tmp_path / "schedule.csv"
    schedule.write_text("tt_action_item_id,time_begin,manual_fill,tr_id,geom\n"
                        "2,2026-01-06 12:10:00,True,7,POINT (37.5 55.7)\n"
                        "1,2026-01-06 12:00:00,False,7,POINT (37.4 55.6)\n")
    stops = list(read_schedule_csv(str(schedule)))
    assert [(s.stop_id, s.seq) for s in stops] == [(1, 0), (2, 1)]
    assert (stops[1].longitude, stops[1].latitude, stops[1].manual_fill) == (37.5, 55.7, True)
    assert stops[0].address is None

    addressed = tmp_path / "addressed.csv"
    addressed.write_text(
        "tt_action_item_id,time_begin,manual_fill,tr_id,geom,building_address\n"
        '1,2026-01-06 12:00:00,False,7,POINT (37.4 55.6),"Ярцевская ул., д.25"\n'
        "2,2026-01-06 12:10:00,True,7,POINT (37.5 55.7),\n"
    )
    with_address = list(read_schedule_csv(str(addressed)))
    assert with_address[0].address == "Ярцевская ул., д.25"
    assert with_address[1].address is None

    traffic = tmp_path / "traffic.csv"
    traffic.write_text("tr_id,event_time,location_valid,lon,lat,speed\n"
                       "7,2026-01-06 12:00:00,True,37.5,55.7,12\n"
                       "7,2026-01-06 12:00:15,False,,,\n")
    points = list(read_traffic_csv(str(traffic)))
    assert points[0].vehicle_id == "7" and points[0].location_valid
    assert not points[1].location_valid


def test_ndtp_nav00_decoding():
    nav = NAV.pack(1767682800, 376173210, 557551234, 0xE0, 0, 18, 20, 90, 0, 120, 8, 2)
    body = struct.pack("<HHHI", 1, 101, 1, 1) + bytes([0, 0]) + nav
    npl = bytearray(15)
    npl[:2] = b"~~"
    struct.pack_into("<H", npl, 2, len(body))
    npl[8] = 2
    struct.pack_into("<I", npl, 9, 1166336)
    npl[6:8] = crc16(body).to_bytes(2, "big")
    row = decode_frame(bytes(npl), body, {"1166336": 131672})
    assert row["tr_id"] == 131672
    assert row["location_valid"]
    assert abs(row["longitude"] - 37.617321) < 1e-6
    assert abs(row["latitude"] - 55.7551234) < 1e-6
    assert row["speed"] == 18.0
