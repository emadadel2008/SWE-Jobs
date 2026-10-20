"""Send only user-approved, previously reviewed stale job URLs."""

from __future__ import annotations

import logging
import os
import sys
from datetime import UTC, datetime

from config import PRODUCTION_SOURCE_KEYS
from db import (
    canonicalize_url,
    connect,
    _row_to_stored_job,
    get_sent_topic_keys,
)
from freshness import iso_utc
from main import send_pending_jobs, should_keep_job
from telegram_sender import send_job

log = logging.getLogger("manual_review_send")
MANUAL_REVIEW_APPROVED_REASON = "manual_review_approved"
MAX_REVIEW_CANDIDATES = 10


def send_approved_review_candidates(
    db_path: str,
    urls: list[str],
    *,
    sender=send_job,
    reference_time: datetime | None = None,
) -> tuple[int, int, int, int]:
    """Queue and send only expired, explicitly approved review candidates."""
    normalized_urls = [canonicalize_url(url) for url in urls if url.strip()]
    if not normalized_urls:
        raise ValueError("At least one review candidate URL is required.")
    if len(normalized_urls) > MAX_REVIEW_CANDIDATES:
        raise ValueError(f"At most {MAX_REVIEW_CANDIDATES} review candidates may be sent per run.")
    if len(set(normalized_urls)) != len(normalized_urls):
        raise ValueError("Duplicate review candidate URLs are not allowed.")

    approved_at = iso_utc(reference_time or datetime.now(UTC))
    approved_ids: set[int] = set()

    with connect(db_path) as conn:
        rows = []
        for url in normalized_urls:
            matches = conn.execute(
                """
                SELECT id, source, title, url, canonical_url, preferred_url,
                       send_status, freshness_status, freshness_reason
                FROM jobs
                WHERE url = ? OR canonical_url = ? OR preferred_url = ?
                """,
                (url, url, url),
            ).fetchall()
            if len(matches) != 1:
                raise ValueError(
                    f"Expected exactly one stored job for approved URL {url}; found {len(matches)}."
                )
            rows.append(matches[0])

        for row in rows:
            job_id = int(row["id"])
            source_key = str(row["source"] or "").strip().lower()
            if source_key not in {key.lower() for key in PRODUCTION_SOURCE_KEYS}:
                raise ValueError(f"Job {job_id} is not from an enabled production source.")
            if row["send_status"] != "expired":
                raise ValueError(f"Job {job_id} is not expired; refusing manual re-send.")
            if row["freshness_status"] != "TOO_OLD" or row["freshness_reason"] != "publication_time_too_old":
                raise ValueError(f"Job {job_id} is not an old-publication review candidate.")
            if get_sent_topic_keys(conn, job_id):
                raise ValueError(f"Job {job_id} has already been delivered to a Telegram topic.")

            stored_job = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
            if not should_keep_job(_row_to_stored_job(stored_job).to_job()):
                raise ValueError(f"Job {job_id} no longer passes the current Microsoft Cloud filter.")
            approved_ids.add(job_id)

        for job_id in approved_ids:
            conn.execute(
                """
                UPDATE jobs
                SET send_status = 'pending',
                    freshness_reason = ?,
                    last_seen_at = ?
                WHERE id = ?
                """,
                (MANUAL_REVIEW_APPROVED_REASON, approved_at, job_id),
            )
        conn.commit()

        counts = send_pending_jobs(
            conn,
            limit=len(approved_ids),
            sender=sender,
            reference_time=reference_time,
            check_live_quiet_hours=True,
            job_ids=approved_ids,
        )

    processed, successes, failures, skipped = counts
    log.info(
        "Manual review send complete: selected=%s, processed=%s, sent=%s, failures=%s, skipped=%s",
        len(approved_ids),
        processed,
        successes,
        failures,
        skipped,
    )
    if successes != len(approved_ids):
        raise RuntimeError(
            f"Only {successes} of {len(approved_ids)} approved review candidates were sent."
        )
    return counts


def main() -> int:
    raw_urls = os.getenv("REVIEW_CANDIDATE_URLS", "")
    urls = [line.strip() for line in raw_urls.splitlines() if line.strip()]
    try:
        send_approved_review_candidates(os.getenv("JOBS_DB_PATH", "jobs.db"), urls)
    except Exception:
        log.exception("Manual review candidate delivery failed.")
        return 1
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    sys.exit(main())
