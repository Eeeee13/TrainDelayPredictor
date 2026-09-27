import unittest
import pandas as pd
from model.features import compute_passages


class PassageBoundaryTests(unittest.TestCase):
    def test_arrival_and_later_confirmation(self):
        schedule = pd.DataFrame(dict(time_begin=pd.to_datetime(['2026-01-01 12:00']),
                                     slon=[37.0], slat=[55.0], trip_first=[False]))
        traffic = pd.DataFrame(dict(
            event_time=pd.to_datetime(['2026-01-01 11:59:00', '2026-01-01 12:00:00',
                                      '2026-01-01 12:01:00']),
            lon=[37.0001, 37.0, 37.01], lat=[55.0]*3, location_valid=[True]*3))
        result = compute_passages(schedule, traffic)
        self.assertEqual(len(result), 1)
        self.assertEqual(result.arrival.iloc[0], pd.Timestamp('2026-01-01 12:00'))
        self.assertEqual(result.confirm.iloc[0], pd.Timestamp('2026-01-01 12:01'))
        self.assertEqual(result.dev.iloc[0], 0)
        self.assertTrue(compute_passages(schedule, traffic.iloc[:2]).empty)
        schedule['trip_first'] = True
        self.assertTrue(compute_passages(schedule, traffic).empty)

    def test_window_excludes_upper_bound_and_includes_lower(self):
        schedule = pd.DataFrame(dict(time_begin=pd.to_datetime(['2026-01-01 12:00']),
                                     slon=[37.0], slat=[55.0], trip_first=[False]))
        traffic = pd.DataFrame(dict(
            event_time=pd.to_datetime(['2026-01-01 11:48:00', '2026-01-01 11:49:00',
                                      '2026-01-01 12:12:00', '2026-01-01 12:13:00']),
            lon=[37.0,37.01,37.0,37.01], lat=[55.0]*4, location_valid=[True]*4))
        self.assertEqual(compute_passages(schedule,traffic).dev.iloc[0], -720)
        self.assertTrue(compute_passages(schedule,traffic.iloc[1:]).empty)


if __name__ == '__main__':
    unittest.main()
