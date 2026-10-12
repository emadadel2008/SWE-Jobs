import json
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from classifier import classify_job, is_microsoft_cloud_job, normalize_text
from models import Job


class ClassifierTests(unittest.TestCase):
    def test_normalization_handles_arabic_variants(self):
        self.assertEqual(normalize_text("أمنُ المعلومات"), "امن المعلومات")
        self.assertEqual(normalize_text("مُطوّر  برمجيات"), "مطور برمجيات")

    def test_golden_classifier_set_has_high_precision_and_recall(self):
        cases = json.loads((Path(__file__).with_name("classifier_cases.json")).read_text(encoding="utf-8"))
        tp = fp = fn = category_correct = tech_total = 0
        failures = []
        for index, case in enumerate(cases):
            expected = case["expected"]
            job = Job(
                title=case["title"], company="Test", location="Riyadh, Saudi Arabia",
                url=f"https://example.com/{index}", source="linkedin_saudi_v2",
            )
            result = classify_job(job)
            predicted = result.topic if result.is_tech else None
            expected_tech = expected is not None
            if result.is_tech and expected_tech:
                tp += 1
            elif result.is_tech and not expected_tech:
                fp += 1
            elif not result.is_tech and expected_tech:
                fn += 1
            if expected_tech:
                tech_total += 1
                if predicted == expected:
                    category_correct += 1
            if predicted != expected:
                failures.append((case["title"], expected, predicted, result.reason, result.matched))

        precision = tp / (tp + fp) if (tp + fp) else 1.0
        recall = tp / (tp + fn) if (tp + fn) else 1.0
        category_accuracy = category_correct / tech_total if tech_total else 1.0
        self.assertGreaterEqual(precision, 0.97, failures)
        self.assertGreaterEqual(recall, 0.97, failures)
        self.assertGreaterEqual(category_accuracy, 0.95, failures)

    def test_nontech_exclusion_wins_over_generic_engineer(self):
        job = Job("Electrical Engineer", "Acme", "Riyadh", "https://x/1", "linkedin")
        self.assertFalse(classify_job(job).is_tech)

    def test_microsoft_cloud_products_and_aliases(self):
        titles = (
            "Azure DevOps Engineer", "Microsoft Cloud Consultant",
            "Microsoft 365 Administrator", "M365 Support", "Office 365 Engineer",
            "O365 Migration Consultant", "Entra ID Specialist", "Azure AD Engineer",
            "AAD Administrator", "AzureAD Administrator", "EntraID Specialist",
            "AKS Platform Engineer", "MS365 Support", "MS Teams Engineer",
            "Dynamics 365 Consultant", "D365 F&O Developer", "D365FO Developer",
            "Microsoft Dynamics CRM Consultant", "Dynamics AX Consultant",
            "Business Central Developer", "Power Platform Consultant",
            "PowerApps Developer", "Power Automate Consultant", "Power BI Analyst",
            "Power Pages Developer", "Copilot Studio Developer", "Dataverse Engineer",
            "SharePoint Online Administrator", "Exchange Online Engineer",
            "Microsoft Teams Engineer", "Intune Administrator",
            "Microsoft Defender Specialist", "Microsoft Sentinel Analyst",
            "Microsoft Purview Engineer", "Microsoft Fabric Data Engineer",
            "استشاري ديناميكس 365", "مهندس أزور", "دعم مايكروسوفت 365",
        )
        for title in titles:
            with self.subTest(title=title):
                job = Job(title, "Any Employer", "Riyadh", "https://x/1", "linkedin")
                self.assertTrue(is_microsoft_cloud_job(job))

    def test_cloud_evidence_in_tags_or_description(self):
        for tags, description in (
            (["Python", ["aZuRe", "SQL"]], ""),
            ([{"name": "PowerPlatform"}], ""),
            ([{"label": "Entra ID"}], ""),
            ([], "Design workloads on Microsoft Azure and AWS."),
            ([], "<p>Manage Microsoft-365 tenant migrations.</p>"),
        ):
            with self.subTest(tags=tags, description=description):
                job = Job("Systems Specialist", "Acme", "Remote", "https://x/1", "ats_lever_acme",
                          tags=tags, description=description)
                self.assertTrue(is_microsoft_cloud_job(job))

    def test_unrelated_jobs_do_not_match_cloud(self):
        for title in (
            "Cloud Engineer", "AWS Architect", "GCP Data Engineer", ".NET Developer",
            "Windows Server Administrator", "Active Directory Engineer", "Software Engineer",
            "Dynamics of Fluid Systems Researcher", "Power Engineer", "Copilot Developer",
            "Azureus Developer", "Entranet Administrator", "M3650 Operator", "",
        ):
            with self.subTest(title=title):
                job = Job(title, "Microsoft Azure", "Remote", "https://x/1", "linkedin",
                          tags=["Python", ".NET"])
                self.assertFalse(is_microsoft_cloud_job(job))

    def test_cloud_evidence_cannot_span_independent_fields(self):
        job = Job("Microsoft", "Acme", "Remote", "https://x/1", "linkedin", tags=["365"])
        self.assertFalse(is_microsoft_cloud_job(job))


if __name__ == "__main__":
    unittest.main()
