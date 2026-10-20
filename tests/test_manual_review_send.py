import os
import tempfile
import unittest
from datetime import UTC, datetime, timedelta

from db import (
    connect,
    expire_stale_unsent_jobs,
    get_jobs_for_sending,
    set_job_freshness_state,
    set_job_send_status,
    upsert_job,
)
from models import Job
from send_review_candidates import send_approved_review_candidates


class ManualReviewSendTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 20, 13, 40, tzinfo=UTC)

    def _add_old_candidate(self, conn, url, title="Azure Engineer"):
        job = Job(title, "Acme", "Cairo, Egypt", url, "linkedin")
        job_id, _ = upsert_job(conn, job)
        first_seen = (self.now - timedelta(days=1)).isoformat().replace("+00:00", "Z")
        conn.execute("UPDATE jobs SET first_seen_at = ? WHERE id = ?", (first_seen, job_id))
        set_job_freshness_state(conn, job_id, "TOO_OLD", "publication_time_too_old")
        set_job_send_status(conn, job_id, "expired")
        return job_id

    def test_manual_approval_sends_only_selected_old_candidates(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "jobs.db")
            urls = [
                f"https://www.linkedin.com/jobs/view/{index}"
                for index in range(101, 105)
            ]
            with connect(db_path) as conn:
                job_ids = {self._add_old_candidate(conn, url) for url in urls}
                unrelated_id, _ = upsert_job(
                    conn,
                    Job(
                        "Azure Engineer", "Acme", "Cairo, Egypt",
                        "https://www.linkedin.com/jobs/view/999", "linkedin",
                    ),
                )

            sent = []
            counts = send_approved_review_candidates(
                db_path,
                urls,
                sender=lambda job, topics: sent.append(job.url)
                or {topic: True for topic in topics},
                reference_time=self.now,
            )

            self.assertEqual(counts, (4, 4, 0, 0))
            self.assertEqual(set(sent), set(urls))
            with connect(db_path) as conn:
                rows = conn.execute(
                    "SELECT id, send_status, freshness_status, freshness_reason FROM jobs"
                ).fetchall()
                by_id = {int(row["id"]): row for row in rows}
                for job_id in job_ids:
                    self.assertEqual(by_id[job_id]["send_status"], "sent")
                    self.assertEqual(by_id[job_id]["freshness_status"], "TOO_OLD")
                    self.assertEqual(by_id[job_id]["freshness_reason"], "manual_review_approved")
                self.assertEqual(by_id[unrelated_id]["send_status"], "pending")

    def test_manual_review_delivery_deadline_starts_at_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "jobs.db")
            url = "https://www.linkedin.com/jobs/view/201"
            with connect(db_path) as conn:
                job_id = self._add_old_candidate(conn, url)

            send_approved_review_candidates(
                db_path,
                [url],
                sender=lambda job, topics: {topic: True for topic in topics},
                reference_time=self.now,
            )

            with connect(db_path) as conn:
                expire_stale_unsent_jobs(conn, 60, reference_time=self.now)
                self.assertNotIn(job_id, {
                    stored.id for stored in get_jobs_for_sending(conn)
                })
                delivery = conn.execute(
                    "SELECT deadline_at FROM job_sends WHERE job_id = ?", (job_id,)
                ).fetchone()
                expected = (self.now + timedelta(minutes=60)).isoformat().replace("+00:00", "Z")
                self.assertEqual(delivery["deadline_at"], expected)

    def test_manual_approval_refuses_unreviewed_or_already_sent_jobs(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "jobs.db")
            url = "https://www.linkedin.com/jobs/view/301"
            with connect(db_path) as conn:
                job_id, _ = upsert_job(
                    conn,
                    Job("Azure Engineer", "Acme", "Cairo", url, "linkedin"),
                )

            with self.assertRaisesRegex(ValueError, "not expired"):
                send_approved_review_candidates(
                    db_path,
                    [url],
                    sender=lambda job, topics: {topic: True for topic in topics},
                    reference_time=self.now,
                )


if __name__ == "__main__":
    unittest.main()
