"""Official employer careers feeds, restricted to explicitly Egyptian jobs."""
from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from html.parser import HTMLParser
from urllib.parse import urljoin

from eligibility import html_to_text
from freshness import parse_iso_publication
from models import Job
from sources.http_utils import get_json, get_text, post_json

log = logging.getLogger(__name__)
MAX_PAGES = 100


def _publication(value: str) -> dict[str, str]:
    evidence = parse_iso_publication(value)
    return {
        "published_at_raw": evidence.raw,
        "published_at_earliest": evidence.earliest,
        "published_at_latest": evidence.latest,
        "published_at_est": evidence.estimate,
        "published_precision": evidence.precision,
        "time_semantics": evidence.semantics,
    }


def _egypt(location: str) -> bool:
    return bool(re.search(r"\b(?:egypt|cairo|giza|alexandria|eg)\b|مصر|القاهرة", location, re.I))


def _object(value, context: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"{context}: expected a JSON object")
    return value


def _rows(value, context: str) -> list[dict]:
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise ValueError(f"{context}: expected a job list")
    return value


class _JSONScripts(HTMLParser):
    def __init__(self):
        super().__init__()
        self.active = False
        self.parts: list[str] = []
        self.scripts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "script" and dict(attrs).get("type") == "application/ld+json":
            self.active = True
            self.parts = []

    def handle_data(self, data):
        if self.active:
            self.parts.append(data)

    def handle_endtag(self, tag):
        if tag == "script" and self.active:
            self.scripts.append("".join(self.parts))
            self.active = False


def _job_posting(url: str) -> dict:
    text = get_text(url)
    if text is None:
        raise RuntimeError(f"Career detail fetch failed: {url}")
    parser = _JSONScripts()
    parser.feed(text)
    for script in parser.scripts:
        payload = json.loads(script)
        entries = payload if isinstance(payload, list) else [payload]
        for entry in entries:
            if isinstance(entry, dict):
                candidates = entry.get("@graph", [entry])
                for candidate in candidates:
                    if isinstance(candidate, dict) and candidate.get("@type") == "JobPosting":
                        return candidate
    raise ValueError(f"Career detail has no JobPosting: {url}")


def _advance(rows: list[dict], seen: set[str], id_field: str, context: str) -> None:
    ids = {str(row.get(id_field, "")) for row in rows}
    if "" in ids or (rows and ids.issubset(seen)):
        raise ValueError(f"{context}: missing IDs or repeated pagination")
    seen.update(ids)


def fetch_vodafone_egypt() -> list[Job]:
    """Eightfold's public PCSX endpoint; the older apply/v2 API is not used."""
    base = "https://jobs.vodafone.com"
    jobs: list[Job] = []
    seen: set[str] = set()
    offset = 0
    for _ in range(MAX_PAGES):
        payload = _object(get_json(base + "/api/pcsx/search", params={
            "domain": "vodafone.com", "query": "", "location": "Egypt", "start": offset,
            "filter_include_remote": "1", "filter_include_relocation": "0",
        }), "Vodafone")
        if payload.get("status") != 200:
            raise RuntimeError(f"Vodafone search failed: {payload.get('error')}")
        data = _object(payload.get("data"), "Vodafone data")
        rows = _rows(data.get("positions"), "Vodafone positions")
        total = int(data["count"])
        if not rows and offset < total:
            raise ValueError("Vodafone returned an empty page before the advertised total")
        _advance(rows, seen, "id", "Vodafone")
        for row in rows:
            location = ", ".join(row.get("locations") or [row.get("location", "")])
            if not _egypt(location):
                continue
            url = urljoin(base, row["positionUrl"])
            detail = _job_posting(url)
            jobs.append(Job(
                title=row["name"], company="Vodafone", location=location, url=url,
                source="ats_eightfold_vodafone_egypt", source_job_id=str(row["id"]),
                original_source="Vodafone / VOIS Careers",
                description=html_to_text(detail.get("description", "")),
                job_type=str(row.get("workLocationOption") or ""),
                is_remote=str(row.get("workLocationOption", "")).startswith("remote"),
                **_publication(datetime.fromtimestamp(row["postedTs"], UTC).isoformat()
                               if row.get("postedTs") else ""),
            ))
        offset += len(rows)
        if offset >= total:
            log.info("Vodafone: fetched %s Egypt postings.", len(jobs))
            return jobs
    raise RuntimeError("Vodafone search exceeded pagination safety limit")


def _phenom_ddo(text: str, key: str) -> dict:
    marker = "phApp.ddo = "
    if marker not in text:
        raise ValueError("Phenom page has no embedded search/detail data")
    payload, _ = json.JSONDecoder().raw_decode(text.split(marker, 1)[1])
    result = _object(payload.get(key), key)
    if result.get("status") != 200:
        raise RuntimeError(f"Phenom {key} failed: {result.get('status')}")
    return _object(result.get("data"), key)


def _fetch_phenom_egypt(*, base: str, ref_num: str, lang: str, country: str,
                        employer: str, source_key: str, country_facet: str,
                        site_path: str) -> list[Job]:
    jobs: list[Job] = []
    seen: set[str] = set()
    offset = 0
    for _ in range(MAX_PAGES):
        payload = _object(post_json(base + "/widgets", payload={
            "lang": lang, "deviceType": "desktop", "country": country,
            "pageName": "search-results", "ddoKey": "refineSearch", "refNum": ref_num,
            "from": offset, "size": 100, "jobs": True, "counts": True,
            "keywords": "", "selected_fields": {"country": [country_facet]},
        }), employer)
        search = _object(payload.get("refineSearch"), f"{employer} search")
        if search.get("status") != 200:
            raise RuntimeError(f"{employer} search failed: {search.get('status')}")
        rows = _rows(_object(search.get("data"), employer).get("jobs"), employer)
        total = int(search["totalHits"])
        if not rows and offset < total:
            raise ValueError(f"{employer} returned an empty page before the advertised total")
        _advance(rows, seen, "jobId", employer)
        for row in rows:
            if str(row.get("country", "")).upper() not in {"EGYPT", "EG"}:
                continue
            url = base + f"/{site_path}/job/" + row["jobId"]
            text = get_text(url)
            if text is None:
                raise RuntimeError(f"{employer} detail fetch failed: {url}")
            detail = _object(_phenom_ddo(text, "jobDetail").get("job"), f"{employer} job")
            description = detail.get("description") or detail.get("descriptionEn") or detail.get("descriptionFr")
            if not description:
                raise ValueError(f"{employer} detail has no description: {url}")
            jobs.append(Job(
                title=row["title"], company=str(row.get("company") or employer),
                location=str(row.get("location") or "Egypt"), url=url,
                source=source_key, source_job_id=row["jobId"],
                original_source=f"{employer} Careers", description=html_to_text(description),
                tags=row.get("ml_skills") or [],
                job_type=str(row.get("type") or ""),
                is_remote=str(row.get("workModel", "")).lower() == "remote",
            ))
        offset += len(rows)
        if offset >= total:
            log.info("%s: fetched %s Egypt postings.", employer, len(jobs))
            return jobs
    raise RuntimeError(f"{employer} search exceeded pagination safety limit")


def fetch_orange_egypt() -> list[Job]:
    return _fetch_phenom_egypt(
        base="https://orange.jobs", ref_num="OYVOCZGB", lang="en_gb", country="gb",
        employer="Orange", source_key="ats_phenom_orange_egypt", country_facet="EGYPT",
        site_path="gb/en",
    )


def fetch_cisco_egypt() -> list[Job]:
    return _fetch_phenom_egypt(
        base="https://careers.cisco.com", ref_num="CISCISGLOBAL", lang="en_us", country="us",
        employer="Cisco", source_key="ats_phenom_cisco_egypt", country_facet="Egypt",
        site_path="global/en",
    )


def fetch_amazon_egypt() -> list[Job]:
    jobs: list[Job] = []
    seen: set[str] = set()
    offset = 0
    for _ in range(MAX_PAGES):
        data = _object(get_json("https://www.amazon.jobs/en/search.json", params={
            "normalized_country_code[]": "EGY", "result_limit": 100, "sort": "recent",
            "offset": offset,
        }), "Amazon")
        rows = _rows(data.get("jobs"), "Amazon jobs")
        total = int(data["hits"])
        if not rows and offset < total:
            raise ValueError("Amazon returned an empty page before the advertised total")
        _advance(rows, seen, "id", "Amazon")
        for row in rows:
            if row.get("country_code") != "EGY":
                continue
            jobs.append(Job(
                title=row["title"], company="Amazon", location=str(row.get("location") or "Egypt"),
                url=urljoin("https://www.amazon.jobs", row["job_path"]),
                source="ats_amazon_egypt", source_job_id=str(row.get("id_icims") or row["id"]),
                original_source="Amazon / AWS Careers",
                description=html_to_text("\n".join(str(row.get(key) or "") for key in (
                    "description", "basic_qualifications", "preferred_qualifications",
                ))),
                published_at_raw=str(row.get("posted_date") or ""),
            ))
        offset += len(rows)
        if offset >= total:
            log.info("Amazon: fetched %s Egypt postings.", len(jobs))
            return jobs
    raise RuntimeError("Amazon search exceeded pagination safety limit")


def _fetch_oracle_cloud_egypt(*, host: str, site: str, employer: str, source_key: str) -> list[Job]:
    jobs: dict[str, Job] = {}
    # Country and city searches are combined; returned country is still checked.
    for term in ("Egypt", "Cairo"):
        offset = 0
        seen: set[str] = set()
        for _ in range(MAX_PAGES):
            data = _object(get_json(host + "/hcmRestApi/resources/latest/recruitingCEJobRequisitions",
                                   params={
                                       "expand": "requisitionList", "onlyData": "true",
                                       "finder": f"findReqs;siteNumber={site},limit=100,offset={offset},"
                                                 f"sortBy=POSTING_DATES_DESC,keyword={term}",
                                   }), employer)
            items = _rows(data.get("items"), employer)
            if len(items) != 1:
                raise ValueError(f"{employer}: expected one search result envelope")
            search = items[0]
            rows = _rows(search.get("requisitionList"), employer)
            total = int(search["TotalJobsCount"])
            if not rows and offset < total:
                raise ValueError(f"{employer} returned an empty page before the advertised total")
            _advance(rows, seen, "Id", employer)
            for row in rows:
                location = str(row.get("PrimaryLocation") or "")
                country = str(row.get("PrimaryLocationCountry") or "")
                if country.upper() not in {"EG", "EGY", "EGYPT"} and not _egypt(location):
                    continue
                job_id = str(row["Id"])
                jobs[job_id] = Job(
                    title=row["Title"], company=employer,
                    location=location if _egypt(location) else f"{location}, Egypt",
                    url=host + f"/hcmUI/CandidateExperience/en/sites/{site}/job/{job_id}",
                    source=source_key, source_job_id=job_id,
                    original_source=f"{employer} Careers",
                    description=html_to_text("\n".join(str(row.get(key) or "") for key in (
                        "ShortDescriptionStr", "ExternalQualificationsStr", "ExternalResponsibilitiesStr",
                    ))),
                    **_publication(str(row.get("PostedDate") or "")),
                )
            offset += len(rows)
            if offset >= total:
                break
        else:
            raise RuntimeError(f"{employer} search exceeded pagination safety limit")
    log.info("%s: fetched %s Egypt postings.", employer, len(jobs))
    return list(jobs.values())


def fetch_oracle_egypt() -> list[Job]:
    return _fetch_oracle_cloud_egypt(
        host="https://eeho.fa.us2.oraclecloud.com", site="CX_1",
        employer="Oracle", source_key="ats_oracle_egypt",
    )


def fetch_dell_egypt() -> list[Job]:
    return _fetch_oracle_cloud_egypt(
        host="https://enterpriseplatform.dell.com", site="CX_2001",
        employer="Dell Technologies", source_key="ats_dell_egypt",
    )


def fetch_capgemini_egypt() -> list[Job]:
    jobs: list[Job] = []
    seen: set[str] = set()
    offset = 0
    for page in range(1, MAX_PAGES + 1):
        data = _object(get_json("https://cg-jobstream-api.azurewebsites.net/api/job-search",
                               params={"country_code": "eg-en", "page": page, "size": 100}),
                       "Capgemini")
        if data.get("timed_out"):
            raise RuntimeError("Capgemini search timed out")
        rows = _rows(data.get("data"), "Capgemini")
        total = int(data["total"])
        if not rows and offset < total:
            raise ValueError("Capgemini returned an empty page before the advertised total")
        _advance(rows, seen, "id", "Capgemini")
        for row in rows:
            if str(row.get("country_code", "")).lower() not in {"en-eg", "eg-en"}:
                continue
            jobs.append(Job(
                title=row["title"], company=str(row.get("brand") or "Capgemini"),
                location=f"{row.get('location') or ''}, Egypt".strip(", "),
                url=row["apply_job_url"], source="ats_capgemini_egypt",
                source_job_id=str(row["id"]), original_source="Capgemini Careers",
                description=html_to_text(str(row.get("description") or row.get("description_stripped") or "")),
                job_type=str(row.get("contract_type") or ""),
            ))
        offset += len(rows)
        if offset >= total:
            log.info("Capgemini: fetched %s Egypt postings.", len(jobs))
            return jobs
    raise RuntimeError("Capgemini search exceeded pagination safety limit")
