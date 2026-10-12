import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from models import Job
from telegram_sender import format_job_message, route_job
from config import CHANNELS


class TelegramRoutingTests(unittest.TestCase):
    def test_only_microsoft_cloud_topic_is_active(self):
        self.assertEqual(set(CHANNELS), {"microsoft_cloud"})
        self.assertEqual(CHANNELS["microsoft_cloud"]["thread_env"], "TOPIC_MICROSOFT_CLOUD")

    def test_backend_job_routes_once_even_when_linkedin_and_in_egypt(self):
        job = Job(
            title="Backend Developer",
            company="Acme",
            location="Cairo, Egypt",
            url="https://www.linkedin.com/jobs/view/1234567890",
            source="linkedin",
            tags=["Python", "Azure"],
        )
        self.assertEqual(route_job(job), ["microsoft_cloud"])

    def test_cloud_internship_routes_to_same_topic_without_cross_posting(self):
        job = Job(
            title="Backend Developer Intern",
            company="Acme",
            location="Riyadh, Saudi Arabia",
            url="https://example.com/intern",
            source="wuzzuf",
            tags=[".NET", "Azure"],
        )
        self.assertEqual(route_job(job), ["microsoft_cloud"])

    def test_data_engineering_without_cloud_evidence_is_rejected(self):
        job = Job(
            title="Data Engineer",
            company="Acme",
            location="Riyadh, Saudi Arabia",
            url="https://example.com/data",
            source="linkedin",
            tags=["Airflow", "dbt"],
        )
        self.assertEqual(route_job(job), [])

    def test_generic_tech_role_has_no_fallback_topic(self):
        job = Job(
            title="Software Engineer",
            company="Acme",
            location="Cairo, Egypt",
            url="https://example.com/swe",
            source="linkedin",
            tags=[],
        )
        self.assertEqual(route_job(job), [])

    def test_unrelated_linkedin_role_is_not_kept_just_for_its_source(self):
        job = Job(
            title="People Operations Coordinator",
            company="Acme",
            location="Cairo, Egypt",
            url="https://www.linkedin.com/jobs/view/1234567890",
            source="linkedin",
            tags=[],
        )
        self.assertEqual(route_job(job), [])

    def test_market_is_metadata_not_an_extra_topic(self):
        job = Job(
            title="Azure Backend Developer",
            company="Acme",
            location="Riyadh, Saudi Arabia",
            url="https://example.com/backend",
            source="linkedin",
        )
        message = format_job_message(job)
        self.assertEqual(route_job(job), ["microsoft_cloud"])
        self.assertIn("#SaudiArabia", message)
        self.assertNotIn("#Egypt", message)



    def test_official_apply_link_keeps_discovery_source_visible(self):
        job = Job(
            title="Backend Developer",
            company="HALA",
            location="Riyadh, Saudi Arabia",
            url="https://job-boards.greenhouse.io/hala/jobs/123",
            source="linkedin",
            original_source="HALA Careers",
            apply_source_key="ats_greenhouse_hala",
        )
        message = format_job_message(job)
        self.assertIn("Apply on official careers", message)
        self.assertIn("Discovered via: LinkedIn", message)
        self.assertIn("Apply: HALA Careers (official)", message)

    def test_official_primary_source_is_not_described_as_discovered_elsewhere(self):
        job = Job(
            title="Backend Developer",
            company="HALA",
            location="Riyadh, Saudi Arabia",
            url="https://job-boards.greenhouse.io/hala/jobs/124",
            source="ats_greenhouse_hala",
            original_source="HALA Careers",
            apply_source_key="ats_greenhouse_hala",
        )
        message = format_job_message(job)
        self.assertIn("Source: HALA Careers (official)", message)
        self.assertNotIn("Discovered via:", message)

    def test_saudi_eligibility_is_metadata_not_a_topic(self):
        saudi_only = Job(
            title="Azure Backend Developer",
            company="Acme",
            location="Riyadh, Saudi Arabia",
            url="https://example.com/saudi-only",
            source="linkedin",
            eligibility="SAUDI_ONLY",
        )
        message = format_job_message(saudi_only)
        self.assertIn("Eligibility: Saudi nationals only", message)
        self.assertIn("#SaudiOnly", message)
        self.assertEqual(route_job(saudi_only), ["microsoft_cloud"])

        explicitly_open = Job(
            title="Backend Developer",
            company="Acme",
            location="Riyadh, Saudi Arabia",
            url="https://example.com/open",
            source="linkedin",
            eligibility="EXPLICITLY_OPEN",
        )
        open_message = format_job_message(explicitly_open)
        self.assertIn("Explicitly open to non-Saudis", open_message)
        self.assertIn("#OpenEligibility", open_message)

        unspecified = Job(
            title="Backend Developer",
            company="Acme",
            location="Riyadh, Saudi Arabia",
            url="https://example.com/unknown",
            source="linkedin",
        )
        self.assertIn("Eligibility: Not specified", format_job_message(unspecified))

    def test_send_job_records_false_for_unconfigured_topic(self):
        import telegram_sender

        job = Job(
            title="Azure Backend Developer",
            company="Acme",
            location="Remote",
            url="https://example.com/job",
            source="wuzzuf",
            is_remote=True,
        )
        result = telegram_sender.send_job(job, target_topics=["missing_topic_for_test"])
        delivery = result["missing_topic_for_test"]
        self.assertFalse(delivery.success)
        self.assertEqual(delivery.outcome, telegram_sender.CONFIG_ERROR)


if __name__ == "__main__":
    unittest.main()
