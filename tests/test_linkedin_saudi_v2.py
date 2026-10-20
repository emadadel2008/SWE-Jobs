import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sources import linkedin_saudi_v2

SAMPLE = """
<li>
<a href="https://www.linkedin.com/jobs/view/backend-at-acme-8888888888"></a>
<h3 class="base-search-card__title">Backend Developer</h3>
<h4 class="base-search-card__subtitle">Acme</h4>
<span class="job-search-card__location">Riyadh, Saudi Arabia</span>
<time>5 minutes ago</time>
</li>
"""


class LinkedInSaudiV2Tests(unittest.TestCase):
    def test_default_request_delay_matches_production_linkedin(self):
        self.assertEqual(
            linkedin_saudi_v2.DEFAULT_REQUEST_DELAY,
            linkedin_saudi_v2.DEFAULT_REQUEST_DELAY_SECONDS,
        )

    def test_searches_use_saudi_geoid_and_fresh_sorting(self):
        self.assertGreaterEqual(len(linkedin_saudi_v2.SAUDI_V2_SEARCHES), 1)
        for search in linkedin_saudi_v2.SAUDI_V2_SEARCHES:
            self.assertEqual(search.get("geoId"), linkedin_saudi_v2.SAUDI_GEO_ID)
            self.assertEqual(search.get("location"), "Saudi Arabia")
            self.assertNotIn("f_TPR", search)
            self.assertEqual(search.get("sortBy"), "DD")

    def test_wrapper_labels_jobs_with_source_identity(self):
        requested = []

        def getter(url, params=None, headers=None):
            requested.append(dict(params or {}))
            return SAMPLE

        jobs = linkedin_saudi_v2.fetch_linkedin_saudi_v2(
            searches=[linkedin_saudi_v2.SAUDI_V2_SEARCHES[0]],
            max_pages_per_search=1,
            request_delay=0,
            http_getter=getter,
        )
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].source, "linkedin_saudi_v2")
        self.assertEqual(jobs[0].original_source, "LinkedIn")
        self.assertEqual(jobs[0].source_job_id, "8888888888")
        self.assertEqual(requested[0]["geoId"], "100459316")
        from config import SOURCE_FRESHNESS_POLICIES

        self.assertEqual(
            SOURCE_FRESHNESS_POLICIES["linkedin_saudi_v2"]["uncertain_fallback"],
            "SOURCE_WINDOW",
        )


if __name__ == "__main__":
    unittest.main()
