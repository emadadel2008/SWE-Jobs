import tempfile
import os
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import main
from db import connect, upsert_job
from freshness import parse_iso_publication
from models import Job
from sources import linkedin


class UnrestrictedDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.object(main, "FRESH_ONLY", False))
        self.now = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)

    def job(self, source="linkedin", publication=True):
        job = Job(
            "Azure Engineer", "Acme", "Cairo, Egypt",
            "https://www.linkedin.com/jobs/view/4480000001", source,
        )
        if publication:
            evidence = parse_iso_publication("2026-09-01T12:00:00Z")
            job.published_at_raw = evidence.raw
            job.published_at_earliest = evidence.earliest
            job.published_at_latest = evidence.latest
            job.published_at_est = evidence.estimate
            job.published_precision = evidence.precision
            job.time_semantics = evidence.semantics
        return job

    def run_cycle(self, db_path, jobs, sent):
        return main.run_bot(
            db_path=str(db_path),
            fetchers=[("LinkedIn", lambda: jobs)],
            sender=lambda job, topics: sent.append((job.title, topics))
            or {topic: True for topic in topics},
            cleanup_func=lambda: None,
            reference_time=self.now,
            seed_mode=False,
            force_poll_all_sources=True,
        )

    def test_old_and_missing_date_jobs_send_without_baseline_and_do_not_repeat(self):
        for publication in (True, False):
            with self.subTest(publication=publication), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "jobs.db"
                sent = []
                job = self.job(publication=publication)
                first = self.run_cycle(path, [job], sent)
                second = self.run_cycle(path, [job], sent)
                self.assertEqual(first.topic_send_successes, 1)
                self.assertEqual(second.topic_send_successes, 0)
                self.assertEqual(sent, [("Azure Engineer", ["microsoft_cloud"])])

    def test_stored_expired_delivery_requeues_without_age_deadline(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "jobs.db"
            with connect(path) as conn:
                job_id, _ = upsert_job(conn, self.job())
                conn.execute(
                    "UPDATE jobs SET send_status='expired', first_seen_at='2026-09-01T12:00:00Z' "
                    "WHERE id=?", (job_id,),
                )
                main.ensure_topic_deliveries(conn, job_id, ["microsoft_cloud"], "2026-09-01T13:00:00Z")
                conn.execute("UPDATE job_sends SET status='expired' WHERE job_id=?", (job_id,))
                conn.commit()
            sent = []
            first = self.run_cycle(path, [], sent)
            second = self.run_cycle(path, [], sent)
            self.assertEqual(first.topic_send_successes, 1)
            self.assertEqual(second.topic_send_successes, 0)
            self.assertEqual(len(sent), 1)
            with connect(path) as conn:
                state = main.get_topic_delivery_states(conn, job_id)["microsoft_cloud"]
                self.assertEqual(state["status"], "sent")
                self.assertFalse(state["deadline_at"])

    def test_successful_or_ambiguous_delivery_is_never_requeued(self):
        for status in ("sent", "unknown", "sending"):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "jobs.db"
                with connect(path) as conn:
                    job_id, _ = upsert_job(conn, self.job())
                    conn.execute("UPDATE jobs SET send_status='expired' WHERE id=?", (job_id,))
                    main.ensure_topic_deliveries(conn, job_id, ["microsoft_cloud"], "")
                    conn.execute("UPDATE job_sends SET status=? WHERE job_id=?", (status, job_id))
                    conn.commit()
                sent = []
                summary = self.run_cycle(path, [self.job()], sent)
                self.assertEqual(summary.topic_send_successes, 0)
                self.assertEqual(sent, [])

    def test_linkedin_fetch_does_not_filter_old_cards(self):
        html = """
        <li><a href="https://www.linkedin.com/jobs/view/4480000001"></a>
        <h3 class="base-search-card__title">Azure Engineer</h3>
        <h4 class="base-search-card__subtitle">Acme</h4>
        <span class="job-search-card__location">Cairo, Egypt</span>
        <time>30 days ago</time></li>
        """
        requests = []

        def getter(url, params=None, headers=None):
            requests.append(params)
            return html

        with patch.object(linkedin, "FRESH_ONLY", False):
            jobs = linkedin.fetch_linkedin(
                searches=[linkedin.LINKEDIN_SEARCHES[0]],
                request_delay=0, max_pages_per_search=1, http_getter=getter,
            )
        self.assertEqual(len(jobs), 1)
        self.assertNotIn("f_TPR", requests[0])

    def test_quiet_hours_override_is_explicit_and_not_default(self):
        night = datetime(2026, 10, 20, 20, 0, tzinfo=UTC)
        with patch.dict(os.environ, {"ALLOW_QUIET_HOURS_SEND": "false"}):
            self.assertTrue(main.is_telegram_quiet_hours(night))
        with patch.dict(os.environ, {"ALLOW_QUIET_HOURS_SEND": "true"}):
            self.assertFalse(main.is_telegram_quiet_hours(night))
