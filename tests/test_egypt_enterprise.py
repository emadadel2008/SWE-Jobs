import unittest
from unittest.mock import patch

from sources import egypt_careers as careers
from sources import egypt_enterprise as enterprise


def dxc_row(path="/job/Cairo/Azure_123"):
    return {"title": "Azure Engineer", "externalPath": path, "locationsText": "2 Locations"}


def dxc_detail(location="Cairo", country="Egypt"):
    return {"jobPostingInfo": {
        "title": "Azure Engineer", "location": location, "country": {"descriptor": country},
        "jobDescription": "<p>Azure and Microsoft 365</p>", "jobReqId": "123",
        "startDate": "2026-10-21", "timeType": "Full time",
    }}


class EgyptEnterpriseTests(unittest.TestCase):
    @patch.object(enterprise, "get_json", return_value=dxc_detail())
    @patch.object(enterprise, "post_json", return_value={"total": 1, "jobPostings": [dxc_row()]})
    def test_dxc_merges_searches_and_keeps_full_description(self, post_json, get_json):
        jobs = enterprise.fetch_dxc_egypt()
        self.assertEqual(len(jobs), 1)
        self.assertEqual(get_json.call_count, 1)
        self.assertEqual(post_json.call_count, 3)
        self.assertEqual(jobs[0].source_job_id, "123")
        self.assertEqual(jobs[0].description, "Azure and Microsoft 365")
        self.assertEqual(jobs[0].location, "Cairo")
        self.assertIn("/en-US/DXCJobs/job/Cairo/", jobs[0].url)

    @patch.object(enterprise, "get_json", return_value=dxc_detail("London", "United Kingdom"))
    @patch.object(enterprise, "post_json", return_value={"total": 1, "jobPostings": [dxc_row()]})
    def test_dxc_search_match_is_not_country_evidence(self, _, __):
        self.assertEqual(enterprise.fetch_dxc_egypt(), [])

    @patch.object(enterprise, "get_json", return_value=dxc_detail())
    @patch.object(enterprise, "post_json")
    def test_dxc_uses_actual_returned_offset(self, post_json, _):
        post_json.side_effect = [
            {"total": 2, "jobPostings": [dxc_row()]},
            {"total": 2, "jobPostings": [dxc_row("/job/Cairo/Azure_124")]},
            {"total": 0, "jobPostings": []},
            {"total": 0, "jobPostings": []},
        ]
        self.assertEqual(len(enterprise.fetch_dxc_egypt()), 2)
        self.assertEqual(post_json.call_args_list[1].kwargs["payload"]["offset"], 1)

    @patch.object(enterprise, "post_json", return_value={"total": 1, "jobPostings": []})
    def test_dxc_incomplete_empty_response_fails(self, _):
        with self.assertRaisesRegex(ValueError, "empty page"):
            enterprise.fetch_dxc_egypt()

    def test_talentera_extracts_visible_full_description_not_teaser(self):
        parser = enterprise._TalenteraDescription()
        parser.feed('<p>Navigation</p><div class="job-desc border"><h4>Job Description</h4>'
                    '<div><p>Azure &amp; Microsoft 365</p></div><p>Skills: Intune</p></div>'
                    '<p>Related jobs</p>')
        text = "".join(parser.parts)
        self.assertIn("Azure & Microsoft 365", text)
        self.assertIn("Skills: Intune", text)
        self.assertNotIn("Navigation", text)
        self.assertNotIn("Related jobs", text)

    @patch.object(enterprise, "get_text")
    @patch.object(enterprise, "get_json")
    def test_giza_paginated_egypt_jobs_preserve_real_subsidiary(self, get_json, get_text):
        row = {"id": "10", "title": "Azure Engineer", "loc": "Cairo, Egypt",
               "url": "/en/egypt/jobs/azure-engineer-10/", "companyName": "VAS Integrated Solutions"}
        get_text.side_effect = [
            "var initJSON = {};", '<div class="job-desc"><p>Azure administration</p></div>',
        ]
        get_json.side_effect = [
            {"totalJobs": 2, "currentPage": 1, "jobs": [row]},
            {"totalJobs": 2, "currentPage": 2, "jobs": [dict(row, id="11", loc="Riyadh, Saudi Arabia")]},
        ]
        jobs = enterprise.fetch_giza_systems_egypt()
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].company, "VAS Integrated Solutions")
        self.assertEqual(jobs[0].description, "Azure administration")
        self.assertIn("page=2", get_json.call_args.kwargs["params"]["query"])
        self.assertEqual(get_text.call_count, 2)

    @patch.object(enterprise, "get_text", return_value="var initJSON = {};")
    @patch.object(enterprise, "get_json", return_value={
        "totalJobs": 1, "currentPage": 1, "jobs": [
            {"id": "10", "title": "Azure", "loc": "Egypt", "url": "https://unrelated.example/job"},
        ],
    })
    def test_giza_rejects_unexpected_detail_urls(self, _, __):
        with self.assertRaisesRegex(ValueError, "unexpected job URL"):
            enterprise.fetch_giza_systems_egypt()

    @patch.object(enterprise, "get_text", return_value=None)
    def test_giza_failed_landing_is_not_empty_success(self, _):
        with self.assertRaises(RuntimeError):
            enterprise.fetch_giza_systems_egypt()

    @patch.object(enterprise, "get_text", return_value="var initJSON = {};")
    @patch.object(enterprise, "get_json", return_value={
        "totalJobs": 1, "currentPage": 2, "jobs": [],
    })
    def test_giza_wrong_page_is_reported(self, _, __):
        with self.assertRaisesRegex(ValueError, "incorrect page"):
            enterprise.fetch_giza_systems_egypt()

    @patch.object(careers, "_fetch_phenom_egypt", return_value=[])
    def test_ntt_uses_verified_tenant_and_global_detail_route(self, fetch):
        self.assertEqual(careers.fetch_nttdata_egypt(), [])
        self.assertEqual(fetch.call_args.kwargs["ref_num"], "NTT1GLOBAL")
        self.assertEqual(fetch.call_args.kwargs["site_path"], "global/en")
        self.assertEqual(fetch.call_args.kwargs["source_key"], "ats_phenom_nttdata_egypt")

    @patch.object(careers, "_fetch_oracle_cloud_egypt", return_value=[])
    def test_raya_uses_verified_corporate_careers_site(self, fetch):
        self.assertEqual(careers.fetch_raya_egypt(), [])
        self.assertEqual(fetch.call_args.kwargs["site"], "RayaCareers")
        self.assertEqual(fetch.call_args.kwargs["source_key"], "ats_oracle_raya_egypt")


if __name__ == "__main__":
    unittest.main()
