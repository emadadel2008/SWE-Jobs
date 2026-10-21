import json
import unittest
from unittest.mock import patch

from sources import egypt_careers as careers


def posting(description="Azure administration"):
    return '<script type="application/ld+json">' + json.dumps({
        "@type": "JobPosting", "description": description,
    }) + "</script>"


def orange_page(description="Microsoft 365 and Intune"):
    return "phApp.ddo = " + json.dumps({
        "jobDetail": {"status": 200, "data": {"job": {"description": description}}},
    }) + ";"


class EgyptCareersTests(unittest.TestCase):
    @patch.object(careers, "get_text", return_value=posting())
    @patch.object(careers, "get_json")
    def test_vodafone_paginates_and_rejects_non_egypt(self, get_json, get_text):
        def row(job_id, location):
            return {"id": job_id, "name": "Azure Engineer", "locations": [location],
                    "positionUrl": f"/careers/job/{job_id}", "postedTs": 1792571716}
        get_json.side_effect = [
            {"status": 200, "data": {"positions": [row(1, "Egypt")], "count": 3}},
            {"status": 200, "data": {"positions": [row(2, "London"), row(3, "Cairo, Egypt")], "count": 3}},
        ]
        jobs = careers.fetch_vodafone_egypt()
        self.assertEqual([j.source_job_id for j in jobs], ["1", "3"])
        self.assertEqual(get_json.call_args_list[1].kwargs["params"]["start"], 1)
        self.assertEqual(get_text.call_count, 2)
        self.assertEqual(jobs[0].description, "Azure administration")
        self.assertEqual(jobs[0].source, "ats_eightfold_vodafone_egypt")
        self.assertEqual(jobs[0].published_precision, "EXACT")

    @patch.object(careers, "get_text", return_value=posting())
    @patch.object(careers, "get_json")
    def test_repeated_page_fails_instead_of_silently_truncating(self, get_json, _):
        get_json.return_value = {"status": 200, "data": {"count": 20, "positions": [{
            "id": 1, "name": "Azure Engineer", "locations": ["Egypt"], "positionUrl": "/careers/job/1",
        }]}}
        with self.assertRaisesRegex(ValueError, "repeated pagination"):
            careers.fetch_vodafone_egypt()

    @patch.object(careers, "get_json", return_value=None)
    def test_http_failure_is_not_an_empty_success(self, _):
        with self.assertRaises(ValueError):
            careers.fetch_vodafone_egypt()

    @patch.object(careers, "get_json", return_value={
        "status": 200, "data": {"positions": [], "count": 10},
    })
    def test_empty_incomplete_page_is_not_success(self, _):
        with self.assertRaisesRegex(ValueError, "empty page"):
            careers.fetch_vodafone_egypt()

    @patch.object(careers, "get_text", return_value=orange_page())
    @patch.object(careers, "post_json")
    def test_orange_egypt_facet_description_and_no_updated_date(self, post_json, get_text):
        row = {"jobId": "ICM-1", "title": "Cloud Engineer", "country": "EGYPT",
               "location": "CAIRO,EGYPT", "company": "Orange Business",
               "postedDate": "2026-10-21T10:34:42Z", "ml_skills": ["Azure"]}
        post_json.side_effect = [
            {"refineSearch": {"status": 200, "totalHits": 2, "data": {"jobs": [row]}}},
            {"refineSearch": {"status": 200, "totalHits": 2, "data": {"jobs": [
                dict(row, jobId="ICM-2", country="FRANCE")]}}},
        ]
        jobs = careers.fetch_orange_egypt()
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].description, "Microsoft 365 and Intune")
        self.assertEqual(jobs[0].company, "Orange Business")
        self.assertEqual(jobs[0].published_precision, "NONE")
        self.assertEqual(get_text.call_count, 1)
        self.assertEqual(post_json.call_args.kwargs["payload"]["selected_fields"], {"country": ["EGYPT"]})
        self.assertEqual(post_json.call_args.kwargs["payload"]["from"], 1)

    @patch.object(careers, "get_text", return_value="<html>Application unavailable</html>")
    def test_missing_detail_payload_is_reported(self, _):
        with self.assertRaisesRegex(ValueError, "no JobPosting"):
            careers._job_posting("https://jobs.vodafone.com/careers/job/1")

    def test_explicit_egypt_matching(self):
        self.assertTrue(careers._egypt("New Cairo, EG"))
        self.assertFalse(careers._egypt("Remote, Germany"))

    @patch.object(careers, "get_json")
    def test_amazon_pagination_country_and_description(self, get_json):
        row = {"id": "a1", "id_icims": "101", "title": "Cloud Engineer",
               "country_code": "EGY", "job_path": "/en/jobs/101/cloud-engineer",
               "location": "EG, Cairo", "description": "<p>Azure</p>",
               "basic_qualifications": "Microsoft 365", "posted_date": "October 21, 2026"}
        get_json.side_effect = [
            {"hits": 2, "jobs": [row]},
            {"hits": 2, "jobs": [dict(row, id="a2", country_code="DEU")]},
        ]
        jobs = careers.fetch_amazon_egypt()
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].source_job_id, "101")
        self.assertIn("Microsoft 365", jobs[0].description)
        self.assertEqual(get_json.call_args.kwargs["params"]["offset"], 1)
        self.assertEqual(jobs[0].published_precision, "NONE")

    @patch.object(careers, "get_json")
    def test_oracle_requires_expanded_jobs_and_merges_queries(self, get_json):
        row = {"Id": 42, "Title": "Azure Engineer", "PrimaryLocation": "CAIRO, Egypt",
               "PrimaryLocationCountry": "EG", "ShortDescriptionStr": "<p>Azure</p>"}
        get_json.return_value = {"items": [{"TotalJobsCount": 2, "requisitionList": [
            row, dict(row, Id=43, PrimaryLocation="London", PrimaryLocationCountry="GB"),
        ]}]}
        jobs = careers.fetch_oracle_egypt()
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].source_job_id, "42")
        self.assertEqual(jobs[0].description, "Azure")
        self.assertIn("/sites/CX_1/job/42", jobs[0].url)
        self.assertEqual(get_json.call_args.kwargs["params"]["expand"], "requisitionList")

    @patch.object(careers, "get_json", return_value={
        "items": [{"TotalJobsCount": 0, "requisitionList": []}],
    })
    def test_dell_legitimate_zero_jobs_is_success(self, get_json):
        self.assertEqual(careers.fetch_dell_egypt(), [])
        self.assertIn("siteNumber=CX_2001", get_json.call_args.kwargs["params"]["finder"])

    @patch.object(careers, "get_json", return_value={
        "items": [{"TotalJobsCount": 0}],
    })
    def test_missing_oracle_job_array_is_not_an_empty_success(self, _):
        with self.assertRaises(ValueError):
            careers.fetch_oracle_egypt()

    @patch.object(careers, "get_json")
    def test_capgemini_pages_and_rejects_other_countries(self, get_json):
        row = {"id": "cg1", "title": "Azure Engineer", "location": "Cairo",
               "country_code": "en-eg", "apply_job_url": "https://careers.capgemini.com/job/1",
               "description": "<p>Microsoft 365</p>"}
        get_json.side_effect = [
            {"total": 2, "data": [row]},
            {"total": 2, "data": [dict(row, id="cg2", country_code="en-us")]},
        ]
        jobs = careers.fetch_capgemini_egypt()
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].location, "Cairo, Egypt")
        self.assertEqual(get_json.call_args_list[0].kwargs["params"]["page"], 1)
        self.assertEqual(get_json.call_args.kwargs["params"]["page"], 2)
        self.assertEqual(get_json.call_args.kwargs["params"]["country_code"], "eg-en")

    @patch.object(careers, "get_json", return_value={"timed_out": True, "total": 0, "data": []})
    def test_capgemini_timeout_is_explicit(self, _):
        with self.assertRaisesRegex(RuntimeError, "timed out"):
            careers.fetch_capgemini_egypt()

    @patch.object(careers, "get_text", return_value=orange_page("Azure cloud"))
    @patch.object(careers, "post_json", return_value={
        "refineSearch": {"status": 200, "totalHits": 1, "data": {"jobs": [
            {"jobId": "2029304", "title": "Cloud Engineer", "country": "Egypt", "location": "Cairo, Egypt"},
        ]}},
    })
    def test_cisco_uses_global_detail_path_and_own_tenant(self, post_json, get_text):
        jobs = careers.fetch_cisco_egypt()
        self.assertEqual(jobs[0].source, "ats_phenom_cisco_egypt")
        self.assertEqual(jobs[0].company, "Cisco")
        get_text.assert_called_once_with("https://careers.cisco.com/global/en/job/2029304")
        self.assertEqual(post_json.call_args.kwargs["payload"]["refNum"], "CISCISGLOBAL")


if __name__ == "__main__":
    unittest.main()
