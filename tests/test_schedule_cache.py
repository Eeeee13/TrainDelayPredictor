"""PostgreSQL integration checks in an isolated, disposable schema."""
import os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import unittest
import uuid

from sqlalchemy import create_engine, text
from inference.schedule_cache import ScheduleCache


@unittest.skipUnless(os.getenv('TEST_DATABASE_URL'), 'Requires disposable-schema PostgreSQL access')
class ScheduleCacheTests(unittest.TestCase):
    def setUp(self):
        self.admin = create_engine(os.environ['TEST_DATABASE_URL'])
        self.schema = 'cache_test_' + uuid.uuid4().hex
        with self.admin.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA {self.schema}'))
        self.engine = create_engine(os.environ['TEST_DATABASE_URL'],
                                    connect_args={'options': '-csearch_path=' + self.schema})
        with self.engine.begin() as conn:
            conn.execute(text('CREATE TABLE schedule_stops (tr_id bigint, stop_id bigint, scheduled_time timestamp, longitude float8, latitude float8, manual_fill boolean)'))
            migration = Path(os.environ['SCHEDULE_MIGRATION_PATH']).read_text()
            for statement in migration.split('-- next-statement'):
                conn.execute(text(statement))
            conn.execute(text("INSERT INTO schedule_stops VALUES (1,10,'2026-01-06 09:00',37.5,55.5,false), (1,11,'2026-01-06 09:02',37.51,55.51,true)"))
        self.cache = ScheduleCache()

    def tearDown(self):
        self.engine.dispose()
        with self.admin.begin() as conn:
            conn.execute(text(f'DROP SCHEMA {self.schema} CASCADE'))
        self.admin.dispose()

    def get(self):
        with self.engine.connect().execution_options(isolation_level='REPEATABLE READ') as conn:
            return self.cache.get(conn)

    def test_hit_and_edit_without_row_count_change(self):
        old = self.get()
        self.assertIs(old, self.get())
        with self.engine.begin() as conn:
            conn.execute(text("UPDATE schedule_stops SET scheduled_time=scheduled_time+interval '1 minute', longitude=38, manual_fill=true WHERE stop_id=10"))
        new = self.get()
        self.assertGreater(new.revision, old.revision)
        self.assertNotEqual(new.known, old.known)
        self.assertEqual(new.by_trip[1].slon.iloc[0], 38)
        self.assertEqual(new.by_trip[1].manual_fill.iloc[0], 1)
        self.assertEqual(old.by_trip[1].slon.iloc[0], 37.5)

    def test_insert_delete_and_truncate(self):
        before = self.get()
        with self.engine.begin() as conn:
            conn.execute(text("INSERT INTO schedule_stops VALUES (2,20,'2026-01-06 10:00',37,55,false)"))
        self.assertIn(2, self.get().by_trip)
        with self.engine.begin() as conn:
            conn.execute(text('DELETE FROM schedule_stops WHERE tr_id=1'))
        self.assertNotIn(1, self.get().by_trip)
        with self.engine.begin() as conn:
            conn.execute(text('TRUNCATE schedule_stops'))
        empty = self.get()
        self.assertFalse(empty.by_trip)
        self.assertFalse(empty.known)
        self.assertGreater(empty.revision, before.revision)
        self.assertIs(empty, self.get())

    def test_rollback_does_not_invalidate(self):
        before = self.get()
        with self.engine.connect() as conn:
            conn.execute(text('UPDATE schedule_stops SET longitude=40'))
            conn.rollback()
        self.assertIs(before, self.get())

    def test_old_request_cannot_replace_newer_snapshot(self):
        with self.engine.connect().execution_options(isolation_level='REPEATABLE READ') as old_conn:
            old = self.cache.get(old_conn)
            with self.engine.begin() as conn:
                conn.execute(text('UPDATE schedule_stops SET longitude=39'))
            new = self.get()
            still_old = self.cache.get(old_conn)
            self.assertEqual(still_old.revision, old.revision)
            self.assertEqual(still_old.by_trip[1].slon.iloc[0], 37.5)
            self.assertIs(new, self.get())

    def test_concurrent_requests_share_snapshot(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            snapshots = list(pool.map(lambda _: self.get(), range(8)))
        self.assertTrue(all(s is snapshots[0] for s in snapshots))


if __name__ == '__main__':
    unittest.main()
