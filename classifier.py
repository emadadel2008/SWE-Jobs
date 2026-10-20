"""Microsoft Cloud relevance gate and broad bilingual discovery classifier.

The classifier is intentionally deterministic and auditable. It is not meant to
replace richer enrichment later; it provides a measured baseline that can be
regression-tested before broadening LinkedIn searches.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata

from config import TECH_CATEGORIES, TECH_CATEGORY_ORDER
from models import Job, _flatten_tags

_ARABIC_DIACRITICS = re.compile(r"[\u0610-\u061a\u064b-\u065f\u0670\u06d6-\u06ed]")
_NON_WORD = re.compile(r"[^\w+#.]+", re.UNICODE)

ARABIC_TOPIC_KEYWORDS: dict[str, tuple[str, ...]] = {
    "internships": (
        "متدرب", "تدريب", "تدريب تعاوني", "تمهير", "حديث التخرج", "حديثي التخرج",
        "برنامج خريجين", "برنامج الخريجين", "خريج جديد",
    ),
    "backend": (
        "مطور باك اند", "باك اند", "مطور خلفي", "مطور خلفية", "برمجة خلفية",
        "مطور دوت نت", "مهندس دوت نت", "مطور جافا", "مطور بايثون", "مطور واجهات برمجية",
    ),
    "frontend": (
        "مطور فرونت اند", "فرونت اند", "مطور واجهات امامية", "مطور واجهات أمامية",
        "مطور واجهة مستخدم", "مطور رياكت", "مطور انجولار",
    ),
    "mobile": (
        "مطور تطبيقات", "مطور جوال", "مطور موبايل", "مطور اندرويد", "مطور أندرويد",
        "مطور ايفون", "مطور آيفون", "مطور فلاتر",
    ),
    "ai_ml": (
        "ذكاء اصطناعي", "تعلم آلي", "تعلم الاله", "تعلم الآلة", "علم بيانات", "عالم بيانات",
        "مهندس بيانات", "محلل بيانات", "هندسة البيانات", "ذكاء الاعمال", "ذكاء الأعمال",
    ),
    "devops": (
        "ديف اوبس", "ديف أوبس", "مهندس سحابة", "هندسة سحابية", "بنية تحتية",
        "مهندس منصات", "موثوقية المواقع",
    ),
    "qa": (
        "ضمان الجودة", "اختبار البرمجيات", "مختبر برمجيات", "مهندس اختبار", "اختبار آلي",
        "اختبار تلقائي",
    ),
    "cybersecurity": (
        "امن سيبراني", "أمن سيبراني", "امن المعلومات", "أمن المعلومات", "محلل امن", "محلل أمن",
        "اختبار اختراق", "امن تطبيقات", "أمن تطبيقات",
    ),
    "erp": (
        "تخطيط موارد المؤسسات", "مطور ساب", "استشاري ساب", "مطور اودو", "مطور أودو",
        "استشاري اودو", "استشاري أودو", "داينمكس 365", "ديناميكس 365", "مطور اوراكل", "مطور أوراكل",
    ),
}

ARABIC_GENERAL_TECH = (
    "مهندس برمجيات", "مطور برمجيات", "مبرمج", "تطوير برمجيات", "هندسة برمجيات",
    "مهندس نظم", "محلل نظم", "دعم تطبيقات", "دعم فني", "دعم تقني", "تقنية المعلومات",
    "تكنولوجيا المعلومات", "مهندس شبكات", "مسؤول شبكات", "مدير قواعد بيانات",
    "مطور قواعد بيانات", "مصمم تجربة المستخدم", "مصمم واجهة المستخدم", "محلل اعمال تقني",
    "محلل أعمال تقني", "مدير منتج تقني", "مدير مشروع تقني",
)

# Strong negative evidence. We only use terms that clearly indicate a non-tech
# role so broad searches do not accidentally reject technical hybrids.
NON_TECH_EXCLUSIONS = (
    "human resources", "hr officer", "hr specialist", "recruiter", "talent acquisition",
    "sales representative", "sales executive", "account executive", "cashier", "waiter",
    "nurse", "physician", "pharmacist", "dentist", "civil engineer", "mechanical engineer",
    "electrical engineer", "architectural engineer", "accountant", "bookkeeper",
    "موارد بشرية", "اخصائي موارد بشرية", "أخصائي موارد بشرية", "مسؤول موارد بشرية",
    "مندوب مبيعات", "تنفيذي مبيعات", "محاسب", "ممرض", "ممرضة", "طبيب", "صيدلي",
    "مهندس مدني", "مهندس ميكانيكي", "مهندس كهربائي",
)

GENERAL_TECH_ENGLISH = (
    "software engineer", "software developer", "developer", "programmer", "application engineer",
    "application developer", "application support", "systems engineer", "systems analyst",
    "technical support engineer", "it support", "it engineer", "information technology",
    "network engineer", "database administrator", "database developer", "integration engineer",
    "solutions engineer", "solution architect", "technical product manager", "technical project manager",
    "technical business analyst", "business systems analyst", "ui ux", "ui/ux", "ux designer",
    "product designer",
)

MICROSOFT_CLOUD_KEYWORDS = (
    "azure", "microsoft cloud", "microsoft 365", "microsoft365", "m365",
    "office 365", "office365", "o365", "ms365", "ms 365",
    "entra", "entraid", "azure ad", "azuread", "aad", "aks",
    "dynamics 365", "dynamics365", "d365", "d365fo", "d365ce", "d365bc", "microsoft dynamics",
    "dynamics crm", "dynamics ax", "dynamics nav", "business central",
    "power platform", "powerplatform", "power apps", "powerapps",
    "power automate", "powerautomate", "power bi", "powerbi",
    "power pages", "powerpages", "copilot studio", "dataverse",
    "sharepoint online", "exchange online", "microsoft teams", "ms teams",
    "intune", "microsoft endpoint manager", "microsoft defender",
    "microsoft sentinel", "microsoft purview", "microsoft fabric",
    "azure devops", "azure arc", "azure openai", "microsoft copilot",
    "microsoft security",
    "ازور", "أزور", "اجور", "أجور", "مايكروسوفت 365", "ميكروسوفت 365",
    "ديناميكس 365", "داينمكس 365", "باور بلاتفورم", "باور ابس", "باور بي اي",
    "شيربوينت", "تيمز", "إنتون", "ديفندر", "سينتينل", "بورفيو",
)

MICROSOFT_CLOUD_ROLE_KEYWORDS = (
    "cloud architect", "cloud engineer", "azure architect", "azure engineer",
    "azure administrator",
    "microsoft 365", "m365", "intune",
    "cloud security", "cyber security", "cybersecurity", "soc analyst", "siem",
    "presales", "pre sales", "solutions architect", "consultant",
    "technical trainer", "azure devops", "sre", "site reliability",
    "power platform", "dynamics 365", "copilot", "sap", "erp", "it support",
    "data engineer", "data analyst", "system administrator", "systems administrator",
    "security engineer",
    "مهندس سحابة", "أمن سيبراني", "امن سيبراني", "دعم فني",
    "مسؤول أنظمة", "مسؤول انظمة",
    "استشاري", "مدرب تقني", "مدرب فني", "مهندس أمن سيبراني", "مهندس امن سيبراني",
    "محلل أمن سيبراني", "محلل امن سيبراني", "مهندس أمن المعلومات", "مهندس امن المعلومات",
    "مدير النظام", "مدير الأنظمة", "مدير الانظمة", "مسؤول تقنية المعلومات",
    "مهندس مايكروسوفت",
)


@dataclass(frozen=True)
class Classification:
    is_tech: bool
    topic: str | None
    matched: str = ""
    reason: str = ""


def normalize_text(value: str) -> str:
    text = unicodedata.normalize("NFKC", value or "").lower()
    text = _ARABIC_DIACRITICS.sub("", text)
    text = text.replace("ـ", "")
    text = text.translate(str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ى": "ي", "ؤ": "و", "ئ": "ي"}))
    text = _NON_WORD.sub(" ", text)
    return " ".join(text.split())


def _job_text(job: Job) -> str:
    return normalize_text(f"{job.title} {_flatten_tags(job.tags)}")


def _first_match(text: str, patterns) -> str:
    for pattern in patterns:
        normalized = normalize_text(pattern)
        if normalized and normalized in text:
            return str(pattern)
    return ""


def classify_job(job: Job) -> Classification:
    """Classify broad tech jobs for source discovery (not Telegram routing)."""
    text = _job_text(job)
    if not text:
        return Classification(False, None, reason="empty")

    excluded = _first_match(text, NON_TECH_EXCLUSIONS)
    if excluded:
        return Classification(False, None, excluded, "non_tech_exclusion")

    for topic in TECH_CATEGORY_ORDER:
        english = (TECH_CATEGORIES.get(topic) or {}).get("keywords", [])
        matched = _first_match(text, english)
        if not matched:
            matched = _first_match(text, ARABIC_TOPIC_KEYWORDS.get(topic, ()))
        if matched:
            return Classification(True, topic, matched, "topic_keyword")

    general_match = _first_match(text, GENERAL_TECH_ENGLISH)
    if not general_match:
        general_match = _first_match(text, ARABIC_GENERAL_TECH)
    if general_match:
        return Classification(True, "general", general_match, "general_tech")

    return Classification(False, None, reason="no_tech_signal")


def is_tech_job(job: Job) -> bool:
    return classify_job(job).is_tech


def is_microsoft_cloud_job(job: Job) -> bool:
    """Require explicit product evidence, never an employer-name match."""
    fields = (job.title, _flatten_tags(job.tags), job.description)
    return any(_MICROSOFT_CLOUD_PATTERN.search(normalize_text(value)) for value in fields)


def is_target_microsoft_cloud_role(job: Job) -> bool:
    """Match the job families requested for the Microsoft Cloud feed."""
    searchable = normalize_text(f"{job.title} {_flatten_tags(job.tags)} {job.description}")
    return any(
        re.search(rf"(?<!\w){re.escape(normalize_text(keyword))}(?!\w)", searchable)
        for keyword in MICROSOFT_CLOUD_ROLE_KEYWORDS
    )


_MICROSOFT_CLOUD_PATTERN = re.compile(
    r"(?<!\w)(?:"
    + "|".join(re.escape(normalize_text(keyword)) for keyword in MICROSOFT_CLOUD_KEYWORDS)
    + r")(?!\w)"
)
