"""Source registry for enabled job feeds.

All registered feeds may send jobs that pass relevance, freshness, and
deduplication checks. WUZZUF remains paused after repeated 403 responses.
"""

try:  # final project layout: sources/__init__.py
    from sources.wuzzuf import fetch_wuzzuf
    from sources.linkedin import fetch_linkedin
    from sources.linkedin_saudi_v2 import fetch_linkedin_saudi_v2
    from sources.jobzaty import fetch_jobzaty
except ModuleNotFoundError:  # local flat-file test layout
    from wuzzuf import fetch_wuzzuf
    from linkedin import fetch_linkedin
    from linkedin_saudi_v2 import fetch_linkedin_saudi_v2
    from jobzaty import fetch_jobzaty

from company_registry import build_ats_fetchers, build_ats_poll_intervals
from sources.egypt_careers import (
    fetch_amazon_egypt,
    fetch_capgemini_egypt,
    fetch_cisco_egypt,
    fetch_dell_egypt,
    fetch_nttdata_egypt,
    fetch_oracle_egypt,
    fetch_orange_egypt,
    fetch_raya_egypt,
    fetch_vodafone_egypt,
)
from sources.egypt_enterprise import fetch_dxc_egypt, fetch_giza_systems_egypt

CORE_FETCHERS = [
    ("LinkedIn", fetch_linkedin),
    ("LinkedIn Saudi V2", fetch_linkedin_saudi_v2),
]

BOARD_FETCHERS = [("Jobzaty", fetch_jobzaty)]
ATS_FETCHERS = build_ats_fetchers()
EGYPT_FETCHERS = [
    ("ATS Eightfold Vodafone Egypt", fetch_vodafone_egypt),
    ("ATS Phenom Orange Egypt", fetch_orange_egypt),
    ("ATS Amazon Egypt", fetch_amazon_egypt),
    ("ATS Oracle Egypt", fetch_oracle_egypt),
    ("ATS Dell Egypt", fetch_dell_egypt),
    ("ATS Capgemini Egypt", fetch_capgemini_egypt),
    ("ATS Phenom Cisco Egypt", fetch_cisco_egypt),
    ("ATS Phenom NTTDATA Egypt", fetch_nttdata_egypt),
    ("ATS Workday DXC Egypt", fetch_dxc_egypt),
    ("ATS Oracle Raya Egypt", fetch_raya_egypt),
    ("ATS Talentera Giza Egypt", fetch_giza_systems_egypt),
]
ALL_FETCHERS = CORE_FETCHERS + BOARD_FETCHERS + ATS_FETCHERS + EGYPT_FETCHERS

SOURCE_POLL_INTERVAL_MINUTES = {
    "linkedin": 15,
    "linkedin_saudi_v2": 15,
    "jobzaty": 60,
    **build_ats_poll_intervals(),
    **{name.lower().replace(" ", "_"): 120 for name, _ in EGYPT_FETCHERS},
}
ENABLED_SOURCE_NAMES = tuple(name for name, _ in ALL_FETCHERS)
