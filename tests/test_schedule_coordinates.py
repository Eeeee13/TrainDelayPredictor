"""Numeric DB coordinates must preserve the legacy CSV feature contract."""
import unittest

import numpy as np
import pandas as pd

from model.features import load_schedule


class ScheduleCoordinatesTests(unittest.TestCase):
    def test_numeric_matches_wkt_including_incomplete_points(self):
        numeric = pd.DataFrame({
            'tr_id': [2, 1, 1, 1],
            'tt_action_item_id': [20, 12, 11, 13],
            'time_begin': ['2026-01-06 12:00', '2026-01-06 12:12',
                           '2026-01-06 12:00', '2026-01-06 12:14'],
            'manual_fill': [False, True, False, False],
            'longitude': [37.62, None, 37.123456789, 37.5],
            'latitude': [55.75, 55.75, 55.987654321, None],
        })
        legacy = numeric.copy()
        legacy['geom'] = legacy.apply(lambda r: f'POINT ({r.longitude} {r.latitude})', axis=1)
        expected, actual = load_schedule(legacy), load_schedule(numeric)
        for tr in expected:
            pd.testing.assert_frame_equal(expected[tr].drop(columns='geom'), actual[tr])

    def test_csv_geometry_remains_authoritative(self):
        frame = pd.DataFrame(dict(tr_id=[1], tt_action_item_id=[1],
                                  time_begin=['2026-01-06 12:00'], manual_fill=[False],
                                  geom=['POINT (37.5 55.5)'], longitude=[0.0], latitude=[0.0]))
        result = load_schedule(frame)[1]
        self.assertEqual(result.slon.iloc[0], 37.5)
        self.assertEqual(result.slat.iloc[0], 55.5)


if __name__ == '__main__':
    unittest.main()
