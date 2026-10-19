import os
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import main
from db import connect, get_source_state, update_source_run
from source_runtime import (
    classify_source_health,
    compute_next_poll_at,
    detect_ats_adapter_outages,
    is_source_due,
)


class SourceRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 4, 18, 0, tzinfo=UTC)

    def test_telegram_quiet_hours_follow_cairo_time_and_boundaries(self):
        self.assertFalse(main.is_telegram_quiet_hours(datetime(2026, 10, 19, 18, 59, tzinfo=UTC)))  # 21:59 Cairo
        self.assertTrue(main.is_telegram_quiet_hours(datetime(2026, 10, 19, 19, 0, tzinfo=UTC)))   # 22:00 Cairo
        self.assertTrue(main.is_telegram_quiet_hours(datetime(2026, 10, 20, 5, 59, tzinfo=UTC)))   # 08:59 Cairo
        self.assertFalse(main.is_telegram_quiet_hours(datetime(2026, 10, 20, 6, 0, tzinfo=UTC)))  # 09:00 Cairo

    def test_quiet_hours_skip_delivery_without_advancing_queue(self):
        with tempfile.TemporaryDirectory() as tmp, patch("main.send_pending_jobs") as send_pending:
            main.run_bot(
                db_path=os.path.join(tmp, "jobs.db"),
                fetchers=[],
                cleanup_func=lambda: None,
                reference_time=datetime(2026, 10, 19, 19, 0, tzinfo=UTC),
            )
            send_pending.assert_not_called()

    def test_success_uses_configured_interval_and_failure_retries_next_cycle(self):
        self.assertEqual(
            compute_next_poll_at(
                run_at=self.now, status="ok", poll_interval_minutes=60
            ),
            "2026-10-04T19:00:00Z",
        )
        self.assertEqual(
            compute_next_poll_at(
                run_at=self.now, status="failed", poll_interval_minutes=60
            ),
            "2026-10-04T18:15:00Z",
        )

    def test_due_check_prefers_persisted_next_poll(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "jobs.db")
            with connect(db_path) as conn:
                update_source_run(
                    conn,
                    "ats_greenhouse_hala",
                    "ok",
                    last_run_at="2026-10-04T18:00:00Z",
                    poll_interval_minutes=30,
                    next_poll_at="2026-10-04T18:30:00Z",
                    health_status="HEALTHY",
                )
                state = get_source_state(conn, "ats_greenhouse_hala")
                self.assertFalse(
                    is_source_due(
                        state,
                        now=self.now + timedelta(minutes=15),
                        poll_interval_minutes=30,
                    )
                )
                self.assertTrue(
                    is_source_due(
                        state,
                        now=self.now + timedelta(minutes=30),
                        poll_interval_minutes=30,
                    )
                )

    def test_ats_empty_is_idle_but_repeated_fetch_failures_become_unhealthy(self):
        self.assertEqual(
            classify_source_health(
                "ats_greenhouse_hala", status="ok", raw_count=0
            ),
            "IDLE",
        )
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "jobs.db")
            with connect(db_path) as conn:
                update_source_run(
                    conn,
                    "ats_greenhouse_hala",
                    "failed",
                    last_run_at="2026-10-04T17:30:00Z",
                )
                update_source_run(
                    conn,
                    "ats_greenhouse_hala",
                    "failed",
                    last_run_at="2026-10-04T17:45:00Z",
                )
                state = get_source_state(conn, "ats_greenhouse_hala")
                self.assertEqual(
                    classify_source_health(
                        "ats_greenhouse_hala",
                        status="failed",
                        raw_count=0,
                        previous_state=state,
                    ),
                    "UNHEALTHY",
                )

    def test_adapter_outage_requires_multiple_failed_tenants(self):
        self.assertEqual(
            detect_ats_adapter_outages({
                "ats_greenhouse_hala": "failed",
                "ats_greenhouse_minio": "failed",
                "ats_lever_soum": "ok",
            }),
            ["greenhouse"],
        )
        self.assertEqual(
            detect_ats_adapter_outages({
                "ats_greenhouse_hala": "failed",
                "ats_greenhouse_minio": "ok",
            }),
            [],
        )

    def test_run_bot_skips_source_until_due_without_losing_sender_cycle(self):
        calls = []

        def fetcher():
            calls.append("fetch")
            return []

        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "jobs.db")
            first = main.run_bot(
                db_path=db_path,
                fetchers=[("ATS Greenhouse hala", fetcher)],
                cleanup_func=lambda: None,
                reference_time=self.now,
                source_poll_intervals={"ats_greenhouse_hala": 30},
            )
            self.assertEqual(first.source_runs_recorded, 1)
            self.assertEqual(calls, ["fetch"])

            second = main.run_bot(
                db_path=db_path,
                fetchers=[("ATS Greenhouse hala", fetcher)],
                cleanup_func=lambda: None,
                reference_time=self.now + timedelta(minutes=15),
                source_poll_intervals={"ats_greenhouse_hala": 30},
            )
            self.assertEqual(second.source_runs_recorded, 0)
            self.assertEqual(second.sources_skipped_not_due, 1)
            self.assertEqual(calls, ["fetch"])

            third = main.run_bot(
                db_path=db_path,
                fetchers=[("ATS Greenhouse hala", fetcher)],
                cleanup_func=lambda: None,
                reference_time=self.now + timedelta(minutes=30),
                source_poll_intervals={"ats_greenhouse_hala": 30},
            )
            self.assertEqual(third.source_runs_recorded, 1)
            self.assertEqual(calls, ["fetch", "fetch"])

            with connect(db_path) as conn:
                state = get_source_state(conn, "ats_greenhouse_hala")
                self.assertEqual(state["poll_interval_minutes"], 30)
                self.assertEqual(state["health_status"], "IDLE")
                self.assertEqual(state["next_poll_at"], "2026-10-04T19:00:00Z")

    def test_manual_force_poll_ignores_deadline_then_reschedules_source(self):
        calls = []

        def fetcher():
            calls.append("fetch")
            return []

        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "jobs.db")
            main.run_bot(
                db_path=db_path,
                fetchers=[("ATS Greenhouse hala", fetcher)],
                cleanup_func=lambda: None,
                reference_time=self.now,
                source_poll_intervals={"ats_greenhouse_hala": 30},
            )

            forced = main.run_bot(
                db_path=db_path,
                fetchers=[("ATS Greenhouse hala", fetcher)],
                cleanup_func=lambda: None,
                reference_time=self.now + timedelta(minutes=15),
                source_poll_intervals={"ats_greenhouse_hala": 30},
                force_poll_all_sources=True,
            )
            self.assertEqual(forced.source_runs_recorded, 1)
            self.assertEqual(forced.sources_skipped_not_due, 0)
            self.assertEqual(calls, ["fetch", "fetch"])

            scheduled = main.run_bot(
                db_path=db_path,
                fetchers=[("ATS Greenhouse hala", fetcher)],
                cleanup_func=lambda: None,
                reference_time=self.now + timedelta(minutes=30),
                source_poll_intervals={"ats_greenhouse_hala": 30},
                force_poll_all_sources=False,
            )
            self.assertEqual(scheduled.source_runs_recorded, 0)
            self.assertEqual(scheduled.sources_skipped_not_due, 1)
            self.assertEqual(calls, ["fetch", "fetch"])


if __name__ == "__main__":
    unittest.main()
