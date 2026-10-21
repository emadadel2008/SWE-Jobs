"""Verified public DXC and Giza Systems/Pulse employer careers feeds."""
from __future__ import annotations

import logging
from html.parser import HTMLParser
from urllib.parse import urljoin

from eligibility import html_to_text
from models import Job
from sources.ats import _workday_public_url, _workday_source_job_id
from sources.egypt_careers import MAX_PAGES, _advance, _egypt, _object, _publication, _rows
from sources.http_utils import get_json, get_text, post_json

log = logging.getLogger(__name__)


def fetch_dxc_egypt() -> list[Job]:
    host = "dxctechnology.wd1.myworkdayjobs.com"
    root = f"https://{host}/wday/cxs/dxctechnology/DXCJobs"
    jobs: dict[str, Job] = {}
    for term in ("Egypt", "Cairo", "Giza"):
        offset = 0
        seen: set[str] = set()
        for _ in range(MAX_PAGES):
            payload = _object(post_json(root + "/jobs", payload={
                "appliedFacets": {}, "limit": 20, "offset": offset, "searchText": term,
            }), "DXC search")
            rows = _rows(payload.get("jobPostings"), "DXC jobs")
            total = int(payload["total"])
            if not rows and offset < total:
                raise ValueError("DXC returned an empty page before the advertised total")
            _advance(rows, seen, "externalPath", "DXC")
            for row in rows:
                path = str(row["externalPath"])
                if path in jobs:
                    continue
                detail = _object(get_json(root + path), "DXC detail")
                info = _object(detail.get("jobPostingInfo"), "DXC jobPostingInfo")
                country = _object(info.get("country"), "DXC country")
                location = str(info.get("location") or "")
                # A search match or a "2 Locations" label is not country evidence.
                if str(country.get("descriptor") or "").lower() != "egypt" and not _egypt(location):
                    continue
                if not info.get("jobDescription"):
                    raise ValueError(f"DXC detail has no description: {path}")
                jobs[path] = Job(
                    title=info["title"], company="DXC Technology",
                    location=location if _egypt(location) else f"{location}, Egypt",
                    url=_workday_public_url(host, "en-US", "DXCJobs", path),
                    source="ats_workday_dxc_egypt",
                    source_job_id=str(info.get("jobReqId") or _workday_source_job_id(row, path)),
                    original_source="DXC Technology Careers",
                    description=html_to_text(info["jobDescription"]),
                    job_type=str(info.get("timeType") or ""),
                    **_publication(str(info.get("startDate") or "")),
                )
            offset += len(rows)
            if offset >= total:
                break
        else:
            raise RuntimeError("DXC search exceeded pagination safety limit")
    log.info("DXC: fetched %s Egypt postings.", len(jobs))
    return list(jobs.values())


class _TalenteraDescription(HTMLParser):
    """Read the full visible description; this site's JSON-LD is malformed."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "div":
            classes = dict(attrs).get("class", "").split()
            if self.depth or "job-desc" in classes:
                self.depth += 1

    def handle_endtag(self, tag):
        if self.depth:
            self.parts.append("\n")
            if tag == "div":
                self.depth -= 1

    def handle_data(self, data):
        if self.depth:
            self.parts.append(data)


def fetch_giza_systems_egypt() -> list[Job]:
    # gizasystems.com/careers links to this employer-owned Talentera board.
    base = "https://www.pulse-careers.com"
    landing = get_text(base + "/en/job-search-results/")
    if landing is None or "var initJSON" not in landing:
        raise RuntimeError("Giza/Pulse career search page is unavailable")
    jobs: list[Job] = []
    seen: set[str] = set()
    offset = 0
    for page in range(1, MAX_PAGES + 1):
        payload = _object(get_json(base + "/app/control/byt_job_search_manager", params={
            "action": 1, "token": "", "query": f"jb_location_iso=eg&page={page}",
            "body": "search", "lan": "en",
        }), "Giza/Pulse")
        rows = _rows(payload.get("jobs"), "Giza/Pulse jobs")
        total = int(payload["totalJobs"])
        if int(payload["currentPage"]) != page:
            raise ValueError("Giza/Pulse returned an incorrect page")
        if not rows and offset < total:
            raise ValueError("Giza/Pulse returned an empty page before the advertised total")
        _advance(rows, seen, "id", "Giza/Pulse")
        for row in rows:
            location = str(row.get("loc") or "")
            if not _egypt(location):
                continue
            url = urljoin(base, row["url"])
            if not url.startswith(base + "/en/egypt/jobs/"):
                raise ValueError(f"Giza/Pulse returned an unexpected job URL: {url}")
            text = get_text(url)
            if text is None:
                raise RuntimeError(f"Giza/Pulse detail fetch failed: {url}")
            parser = _TalenteraDescription()
            parser.feed(text)
            description = " ".join("".join(parser.parts).split())
            if not description:
                raise ValueError(f"Giza/Pulse detail has no description: {url}")
            jobs.append(Job(
                title=row["title"], company=str(row.get("companyName") or "Giza Systems / Pulse"),
                location=location, url=url, source="ats_talentera_giza_egypt",
                source_job_id=str(row["id"]), original_source="Giza Systems / Pulse Careers",
                description=description, job_type=str(row.get("empType") or ""),
                tags=[str(row.get("role") or ""), str(row.get("division") or "")],
                # Preserve raw local date without inventing a timezone.
                published_at_raw=str(row.get("crtDate") or ""),
            ))
        offset += len(rows)
        if offset >= total:
            log.info("Giza Systems / Pulse: fetched %s Egypt postings.", len(jobs))
            return jobs
    raise RuntimeError("Giza/Pulse search exceeded pagination safety limit")
