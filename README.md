# Programming Jobs Telegram Bot

Quality-first Telegram bot for **fresh Microsoft Cloud jobs from any employer**, with LinkedIn as the current production feed. Relevant jobs go to one Microsoft Cloud forum topic (thread ID **279**), not per-role topics.

The product goal is a real-time job feed, not a historical job archive:

> discover jobs that are new to us, prove they are still fresh enough, and notify users once.

## Current Design

- **Sources:** production LinkedIn and Saudi LinkedIn V2, a low-rate shadow Jobzaty discovery feed, and an evidence-driven shadow ATS company registry (Greenhouse, Lever, Ashby, Workday). WUZZUF is temporarily paused after repeated production 403 responses.
- **Fresh-only gate:** old or uncertain jobs are stored for dedup/audit but are not posted late.
- **Source baselines:** the first successful fetch of a new source never sends its existing backlog.
- **Shadow-by-default sources:** any source not explicitly promoted to production is measured and stored but cannot send to Telegram. Shadow discovery cannot suppress a later fresh production discovery of the same job.
- **Per-source run history:** fetch counts, freshness outcomes, failures, duration, shadow yield, coverage gaps, and health status are stored for later source scoring.
- **Optional private admin monitoring:** health transitions and a compact 24-hour digest can be sent to a separate admin chat without adding public topics or messages.
- **Per-source scheduling:** GitHub is requested to run every two hours; individual sources persist `next_poll_at` and are fetched when due. Actual GitHub scheduled starts can be delayed.
- **SQLite state:** jobs, source postings, source state, freshness evidence, delivery state, and delivery attempts live in `jobs.db`.
- **Durable Telegram outbox:** delivery state is written before the network call.
- **Microsoft Cloud relevance:** explicit product evidence in the title, tags, or available description gates runtime filtering and delivery. Broad bilingual tech classification remains available for source discovery.
- **Market/source as metadata:** Egypt/Saudi/Remote and the source are shown in the message instead of creating duplicate topic posts.
- **Evidence-based Saudi eligibility:** explicit Saudi-only/open-to-non-Saudi text is extracted from available job descriptions; silence stays `NOT_SPECIFIED`.
- **Telegram backpressure:** rate limiting, `retry_after`, bounded transient retries, and ambiguous-timeout protection.
- **Runtime:** GitHub Actions is the **current active production runtime** with a requested `0 */2 * * *` schedule. GitHub cron is best-effort and has shown delayed runs in practice. VPS/systemd support is prepared in the repository as an optional future runtime, but it is **not active** unless an intentional cutover is performed with `VPS_PRODUCTION=true`.


## Current Production Status

The current live deployment intentionally stays on **GitHub Actions + the `data` branch SQLite snapshot**.

- Workflow schedule requested from GitHub: `0 */2 * * *` (every two hours).
- GitHub scheduled execution is **best-effort**, so an actual run can start later than the requested cadence.
- `VPS_PRODUCTION` should remain unset/`false` while GitHub owns production. The VPS files added in Update 19 are standby deployment tooling only.
- LinkedIn is the active send-capable production fetcher. WUZZUF is paused at runtime after repeated `403` responses.
- Jobzaty Discovery and all company ATS feeds remain shadow/discovery sources and cannot independently send Telegram jobs.
- The current deployment does **not** enable automatic gap catch-up/backfill. A long GitHub scheduling gap can still mean jobs were missed during the outage, but LinkedIn's next bounded `r7200` result set remains eligible on its own instead of being rejected merely because the previous poll was late.
- Topic renames inside Telegram are safe: renaming an existing forum topic does not change its `message_thread_id`, so the stored GitHub topic secret does not need to change unless the topic itself is deleted/recreated.

The ten former role topics are retired from routing. Only `TOPIC_MICROSOFT_CLOUD` is read for public job delivery; the configured Actions secret is `279`.

## Sources

Enabled sources are assembled in `sources/__init__.py` as `ALL_FETCHERS`. Core feeds are static, while Saudi ATS company feeds are generated from `companies/saudi_ats.json`.

| Source | Status | Notes |
|---|---|---|
| WUZZUF | Paused | Repeated 403 responses from GitHub-hosted runners; parser retained for future re-evaluation |
| LinkedIn | Production | 21 bounded Microsoft Cloud product searches across Egypt, Saudi Arabia, and global remote; no employer restriction |
| LinkedIn Saudi V2 | Production | Saudi `geoId=100459316`, broad country search + ERP/business-systems gap fillers |
| Jobzaty Discovery | Shadow · discovery-only | Public Saudi programming/cybersecurity/IT category cards · 60 min poll · never sends |
| HALA | Shadow ATS | Greenhouse public job board · 30 min poll |
| MinIO | Shadow ATS | Greenhouse public job board, Saudi rows only · 60 min poll |
| SOUM | Shadow ATS | Lever public postings API · 30 min poll |
| Sarj.ai | Shadow ATS | Ashby public job posting API · 60 min poll |
| Echelon | Shadow ATS | Ashby public job posting API · 60 min poll |
| Scale AI | Shadow ATS | Greenhouse; active Saudi engineering hiring · 30 min poll |
| Incorta | Shadow ATS | Lever; Riyadh data/BI roles · 60 min poll |
| UiPath | Shadow ATS | Ashby; Riyadh automation/solution engineering · 60 min poll |
| ElevenLabs | Shadow ATS | Ashby; Saudi AI/engineering/GTM roles · 60 min poll |
| Cognition | Shadow ATS | Ashby; Riyadh/MENA applied-AI roles · 60 min poll |
| Lean Technologies | Shadow ATS | Ashby; Riyadh fintech/platform roles · 30 min poll |
| Cisco | Shadow ATS | Workday CXS; Saudi technology/customer-delivery roles · 60 min poll |
| NTT DATA | Shadow ATS | Workday CXS; Riyadh platform/network/technology roles · 60 min poll |
| Infobip | Shadow ATS | Workday CXS; Riyadh solution engineering/cloud communications · 60 min poll |
| HPE | Shadow ATS | Workday CXS; Riyadh data/cloud/COOP roles · 60 min poll |
| Workday | Shadow ATS | Workday CXS; Riyadh Workday/solution roles · 60 min poll |
| Salesforce | Shadow ATS | Workday CXS; Saudi cloud/solution roles · 60 min poll |
| Legacy aggregators | Disabled | Not registered at runtime |

All ATS feeds are shadow by default because their generated source keys are not in `PRODUCTION_SOURCE_KEYS`. Their first successful fetch establishes a no-send baseline, then later newly observed jobs can be measured without Telegram delivery.

### Saudi job-board discovery

`Jobzaty Discovery` is intentionally **not** a production job source. It reads only three narrow public Saudi category pages (`programming-web-development`, `cybersecurity-jobs`, and `information-technology`) once per hour, deduplicates by Jobzaty listing ID, and records the cards for coverage/source-overlap measurement. The category label is retained as a classifier tag.

Jobzaty cards do not prove minute-level publication time and some listings are multi-role announcements rather than one requisition. The source key therefore also lives in `DISCOVERY_ONLY_SOURCE_KEYS`: even an apparently fresh timestamp in a future parser cannot create a Telegram delivery until that guard is deliberately removed. This lets us measure Saudi coverage without weakening the bot's **freshness > quantity** rule.

This integration does not log in, submit forms, bypass access controls, or crawl the archive. It is deliberately low-rate and shadow-only.

### Saudi ATS company registry

The registry grows in measured batches rather than hundreds of employers at once. The current shadow set is:

```text
companies/saudi_ats.json
├── HALA             → Greenhouse
├── MinIO            → Greenhouse
├── SOUM             → Lever
├── Sarj.ai          → Ashby
├── Echelon          → Ashby
├── Scale AI         → Greenhouse
├── Incorta          → Lever
├── UiPath           → Ashby
├── ElevenLabs       → Ashby
├── Cognition        → Ashby
├── Lean Technologies→ Ashby
├── Cisco            → Workday
├── NTT DATA         → Workday
├── Infobip          → Workday
├── HPE              → Workday
├── Workday          → Workday
└── Salesforce       → Workday
```

`company_registry.py` validates the registry and builds one source fetcher per employer. This gives each company its own source health/freshness/observation metrics instead of hiding all ATS traffic behind one aggregate source.

The adapters live in `sources/ats.py` and use public career-site read endpoints only. Greenhouse preserves `first_published` when the public feed provides it, falling back to snapshot observation when it does not. For Saudi rows only, Greenhouse may make a public single-job detail request to retain the description for internal eligibility evidence; it does not download full descriptions for the entire global board. Lever and Ashby preserve description text already present in their public payloads. Lever remains snapshot-based because its public v0 posting timestamp is not reliable enough for our freshness gate. Ashby preserves `publishedAt`. Workday uses the public CXS endpoint (`POST /wday/cxs/{tenant}/{site}/jobs`) with the platform's hard page size of 20. To avoid crawling thousands of global postings, each Workday registry entry searches only Saudi-oriented terms such as `Riyadh`, `Saudi Arabia`, and `KSA`, then validates the returned location locally. If a Workday search exceeds the configured page cap, the adapter fails closed instead of treating a truncated/re-ranked result set as a trustworthy freshness snapshot. Lever `allLocations` and Ashby secondary locations are inspected so a Saudi location is not lost when it is not the primary display location. Global company boards are always filtered to explicit Saudi locations before the tech classifier runs.

### ATS discovery helper

`ats_detector.py` recognizes Greenhouse, Lever, Ashby, and Workday job/board URLs and extracts the tenant/board identifiers without making a network request. `discover_ats_candidates()` deduplicates a batch of observed URLs into review candidates, but discovery is deliberately side-effect free: it never edits `companies/saudi_ats.json` and can never activate a source automatically. This is the foundation for bootstrapping future registry candidates from off-site apply URLs observed in trusted feeds. Unknown/custom career sites return no guess and remain manual-review candidates.

### Source scheduling and health

GitHub Actions is configured for a two-hour schedule, but scheduled workflow execution is best-effort and can be delayed. `source_runs` persists `poll_interval_minutes`, `next_poll_at`, `health_status`, and `last_nonempty_at`. Source intervals are minimum polling intervals, not independent timers: sources due since the last Actions run are fetched on the next run. Jobzaty and ATS intervals remain unchanged.

A successful source schedules its next normal poll at its configured interval. A failed source retries on the next workflow run even when its normal cadence is slower. Sources that are not due are skipped without blocking the Telegram delivery queue.

Telegram job posts and admin notifications are paused daily from 22:00 to 09:00 in the `Africa/Cairo` timezone. Jobs discovered during that window remain queued for delivery after 09:00. Manual Actions runs can use `test_mode=true` to force a fresh fetch without Telegram delivery or database restore/persistence.

Health intentionally distinguishes a quiet ATS tenant from a broken integration:

- `HEALTHY` — successful fetch with results.
- `IDLE` — successful ATS fetch with zero Saudi postings; this is not treated as a failure.
- `QUIET` — a non-ATS source has a short run of successful empty results.
- `DEGRADED` — transport/schema failure, or repeated empty runs on a core/search source.
- `UNHEALTHY` — three consecutive fetch failures.

If two or more tenants on the same ATS adapter all fail in the same bot run, an adapter-level outage warning is logged so a Greenhouse/Ashby/Workday parser or platform change is not mistaken for multiple unrelated employer failures.

### Saudi LinkedIn V2 production feed

The V2 strategy uses Saudi Arabia's LinkedIn `geoId` and a broad country-level search, then lets the local classifier decide which cards are tech. A small ERP/business-systems gap-filler layer covers SAP/ERP, Oracle/Odoo, and Dynamics/Salesforce. It intentionally does **not** hard-code undocumented LinkedIn job-function IDs yet; those can be A/B tested later in shadow if the broad strategy is too noisy or request-heavy.

Fresh, relevant jobs discovered by V2 can now be sent through the same Microsoft Cloud, geography, and freshness gates as the primary LinkedIn feed. Previously stored shadow discoveries remain suppressed and are not backfilled.

## Classifier and Saudi Location Normalization

`classifier.py` retains deterministic broad English/Arabic tech classification for discovery compatibility. Telegram relevance is separate: `is_microsoft_cloud_job()` requires word-bounded product evidence in the title, tags (including nested tags), or available description. It covers Azure, Microsoft/Office 365, Entra ID, Dynamics 365, Power Platform/Apps/Automate/BI, Dataverse, Business Central, Intune, and related Microsoft Cloud services.

Employer is not evidence: a Microsoft job without a cloud product signal is excluded, while an Azure role at any other company is included. Generic cloud, AWS/GCP-only, standalone .NET, Windows Server, and generic Active Directory roles are excluded. Descriptions are inspected only when already supplied by the source; no new detail-page crawling is added. Existing geography, freshness, source baselines, shadow/discovery-only rules, and duplicate protection remain unchanged.

`locations.py` normalizes common Saudi Arabic/English city variants (for example Riyadh/الرياض, Jeddah/Jiddah/جدة, Khobar/الخبر, Dammam/الدمام, NEOM/نيوم). Location remains metadata, not a routing dimension. Messages can include city hashtags such as `#Riyadh` without creating extra Telegram topics.

## Saudi Eligibility Metadata

`eligibility.py` is deliberately evidence-based. It never infers nationality eligibility from the employer, sector, or the absence of a restriction. Each Saudi job is classified as exactly one of:

```text
SAUDI_ONLY
EXPLICITLY_OPEN
NOT_SPECIFIED
```

Examples of strong evidence include `Saudi nationals only`, `must be Saudi`, `للسعوديين فقط`, and Tamheer for `SAUDI_ONLY`; and `all nationalities`, `non-Saudis welcome`, `visa sponsorship is provided`, or `جميع الجنسيات` for `EXPLICITLY_OPEN`. Phrases such as `Saudi nationals preferred` do **not** become Saudi-only.

The matched evidence sentence and source key are stored in SQLite for audit, while Telegram stays compact. Saudi messages show one eligibility line and optional hashtags such as `#SaudiOnly` or `#OpenEligibility`; eligibility is metadata and never creates another Telegram topic. Full descriptions remain internal and are not posted to the group.

## Shadow Mode and Source Metrics

New sources are **shadowed by default**. The production allowlist currently contains only:

```python
PRODUCTION_SOURCE_KEYS = {"linkedin", "wuzzuf"}  # WUZZUF fetcher is currently paused in the runtime registry
```

A source that is not in this set still runs the complete discovery pipeline:

```text
fetch
→ filter
→ freshness evaluation
→ SQLite persistence
→ metrics/history
→ NO Telegram delivery
```

Fresh jobs discovered by a shadow source are stored with `send_status = shadow`. When that same source is later promoted, historical shadow rows remain suppressed; only jobs discovered **after** promotion can create Telegram deliveries. If a **different production source** independently discovers the same still-fresh job, the row is promoted into the delivery queue so shadow mode cannot hide a legitimate production discovery.

Each source run appends one row to `source_run_history` with fields such as:

```text
status / error / duration_ms
raw_count / filtered_count
inserted_count / refreshed_count
fresh_count / expired_count / uncertain_count
baseline_skipped_count / shadow_eligible_count
coverage_gap / shadow_mode
```

`source_runs` also keeps the latest health snapshot and consecutive failure/empty-run counters. A warning is logged after repeated successful zero-result fetches.

This supports measured source promotion rather than enabling a new feed on intuition alone. `source_observations` and `source_analytics.py` now provide first-discovery, lead-time, and mature 24-hour exclusive metrics for sources that observe the same clustered real-world opening.

## Optional Admin Monitoring

Operational alerts should not become another public topic. If `TELEGRAM_ADMIN_CHAT_ID` is configured, the bot can send a private/admin-chat notification only when a source crosses into `DEGRADED`/`UNHEALTHY`, recovers, starts/clears a freshness coverage gap, or a shared ATS adapter outage appears/recovers. Repeated runs in the same state are suppressed.

A digest is sent at most once per `ADMIN_DIGEST_INTERVAL_HOURS` (default `24`) and summarizes source health, 24-hour fetch/relevance/fresh/shadow counts, Telegram delivery outcomes, Saudi LinkedIn-vs-V2 discovery metrics, and the top shadow candidates. The last successful digest timestamp and active alert states are persisted in SQLite metadata, so GitHub Actions restarts do not reset alert suppression.

## Telegram Topics

The bot uses **one primary topic per job**, exclusively for Microsoft Cloud roles. There is no general-tech fallback.

Current Telegram group layout:

| Topic key | Visible Telegram topic | GitHub secret | Purpose |
|---|---|---|---|
| `microsoft_cloud` | **Microsoft Cloud** | `TOPIC_MICROSOFT_CLOUD` | Microsoft Cloud jobs from any employer; thread ID `279` |

Routing is deterministic: product evidence means `microsoft_cloud`; otherwise no topic. Cloud internships, support, development, administration, and consulting roles share the same topic.

Country and source are metadata, not routing dimensions. `LinkedIn Fresh`, `Egypt`, and `Saudi` are no longer active topics. Country is represented in the card and with lightweight hashtags such as:

```text
#SaudiArabia #Riyadh
#Egypt
#Remote
```

### Telegram group cleanup

The ten previous role topics (Other Tech, Backend, Frontend, Mobile, DevOps, QA, Data & AI, Cybersecurity, Internships, ERP / Business Apps), plus earlier retired topics below, are no longer used. They can be **closed/archived rather than deleted** so their history stays visible:

```text
Jobs in Egypt
Linkedin Jobs
Marketing Jobs
Business & Product Jobs
Jobs in SaudiArabia
UI/UX & Graphic Design
Data Engineering Jobs
Application Support Jobs
GameDev Jobs
Blockchain Jobs
```

Only the Microsoft Cloud topic receives new job posts. Existing Telegram topics are not deleted automatically.

If an existing Telegram topic is only **renamed**, keep its current GitHub secret/thread ID. Update the secret only when a topic is actually deleted and recreated with a new `message_thread_id`.

### Routing transition safety

Pending jobs are rechecked for Microsoft Cloud relevance and geography before sending, so unrelated legacy backlog is skipped. If a relevant pending job was already successfully posted to a retired topic, the bot marks it delivered instead of creating a new primary-topic duplicate.

## Required GitHub Secrets

Go to **GitHub repository → Settings → Secrets and variables → Actions**.

Core secrets:

```text
TELEGRAM_BOT_TOKEN
TELEGRAM_GROUP_ID
```

Optional private monitoring secret:

```text
TELEGRAM_ADMIN_CHAT_ID
```

When set, the bot sends health transitions and one compact digest roughly every 24 hours to that separate chat. If it is absent, monitoring stays in GitHub Actions logs only and public Telegram behaviour is unchanged.

The single active topic secret (already configured to `279`):

```text
TOPIC_MICROSOFT_CLOUD
```

The ten former role secrets and all older retired topic secrets are no longer read by the workflow or runtime. They may be removed from GitHub without changing `TELEGRAM_BOT_TOKEN`, `TELEGRAM_GROUP_ID`, or `TOPIC_MICROSOFT_CLOUD`.

## Getting a Telegram Topic ID

1. Create or open the Telegram supergroup.
2. Enable Topics.
3. Create or open the Microsoft Cloud topic.
4. Copy/open its topic link.
5. Use the topic thread ID as the matching GitHub secret.

The bot sends using Telegram's `message_thread_id`.

## Freshness Model

The bot does **not** use `published_at > last_run` as its notification rule because search indexing can be delayed.

Instead:

```text
new to us
+
source already baselined
+
fresh enough for that source
=
send eligible
```

Publication evidence is stored with its precision:

```text
published_at_raw
published_at_earliest
published_at_latest
published_at_est
published_precision = EXACT | MINUTE | HOUR | DAY | NONE
first_seen_at
last_seen_at
```

Examples:

- exact ISO timestamp → exact evidence;
- `12 minutes ago` → narrow time interval;
- `1 hour ago` → wider uncertain interval;
- missing/coarse time → source-specific fallback only when safe.

A source's first successful fetch is a **baseline** and never floods Telegram with its existing inventory.

### Current freshness configuration

```text
LINKEDIN_FRESHNESS_SECONDS=7200
WUZZUF_OBSERVATION_MAX_AGE_MINUTES=60
ATS_OBSERVATION_MAX_AGE_MINUTES=120
PENDING_SEND_MAX_AGE_MINUTES=60
```

LinkedIn currently requests a rolling recent two-hour window with newest-first ordering, matching the requested two-hour GitHub Actions cadence. That upstream `f_TPR=r7200` window is treated as freshness evidence for the *current* result set, so a delayed previous GitHub run does not invalidate cards LinkedIn is returning now. Observation-only fallbacks (for snapshot-style sources such as WUZZUF/ATS) still fail closed after a long coverage gap. WUZZUF's fallback configuration remains in code even though the fetcher is currently paused.

If an unsent production job was previously expired only because evidence was uncertain (`coverage_gap_too_large` or `insufficient_time_evidence`) and the same source later supplies trustworthy fresh publication evidence, the job may be recovered into the delivery queue. Jobs proven `TOO_OLD`, jobs expired by the send deadline, and any sent/retry/partial delivery state are never revived by this rule.

**Important current limitation:** there is no automatic gap catch-up/backfill mode. If GitHub delays a scheduled run for several hours, the next run does not deliberately widen LinkedIn's search window to cover the entire outage. Jobs that were posted and disappeared outside the current two-hour LinkedIn window can therefore still be missed. Coverage gaps are logged and measured without replaying uncertain old results.

## Telegram Delivery State

Telegram delivery is decoupled from discovery through SQLite delivery rows.

Simplified states:

```text
queued
  ↓
sending
  ├─ sent
  ├─ retry_wait
  ├─ unknown
  ├─ config_error
  └─ failed_permanent
```

Important behavior:

- a delivery is claimed and committed before calling Telegram;
- 429 pauses the supergroup queue and persists `retry_after`;
- transient 5xx/network failures use bounded retries;
- ambiguous read timeouts become `UNKNOWN` instead of being blindly retried;
- formatting errors get one safe plain-text fallback;
- missing/broken topic configuration is treated as `CONFIG_ERROR`;
- deliveries expire after the live-send deadline so stale jobs do not appear later.

Each attempt is recorded in `delivery_attempts` with useful debugging fields such as HTTP status, Telegram error code, description, retry delay, and message ID when available.

## SQLite

`jobs.db` stores:

- normalized job/posting data;
- source job IDs and canonical URLs;
- freshness evidence and decision reason;
- internal description text when a public source provides it, plus eligibility classification/evidence;
- first/last seen times;
- source baseline, shadow/production state, and latest health counters;
- append-only per-source run history and metrics;
- job send status;
- durable topic delivery rows;
- append-only delivery attempt audit rows;
- runtime metadata.

Legacy pending/retry work that is too old is expired instead of replayed.

### SQLite retention and Git data branch

`jobs` rows remain long-term as dedup memory, but operational/audit tables are bounded to 30 days. `db_maintenance.py` prunes terminal delivery rows, delivery attempts, source run history, source observations, old posting mirrors, and old description/evidence text. VACUUM runs weekly or immediately when the database reaches 70 MB. This keeps the live SQLite snapshot below GitHub's large-file danger zone without deleting historical job clusters.

The Actions workflow now fetches only the current `data`-branch tip (`--depth=1`) instead of downloading the branch's full binary history on every run. The raw SQLite file remains the persisted snapshot so Git can continue delta-compressing page-level changes between commits.

## Runtime Flow

Current production path:

```text
GitHub Actions (requested every 15 min; actual start time is best-effort)
    ↓
restore jobs.db from data branch
    ↓
fetch LinkedIn + shadow Saudi ATS/discovery feeds
    ↓
quality + geography filtering
    ↓
Saudi eligibility enrichment from explicit evidence
    ↓
freshness gate
    ├─ baseline → store, no send
    ├─ fresh + production source → queue
    ├─ fresh + shadow source → store as shadow, no send
    └─ stale/unsafe → expire
    ↓
SQLite upsert
    ↓
choose ONE primary Telegram topic
    ↓
create durable delivery
    ↓
rate-limited Telegram sender
    ↓
persist delivery result/audit
    ↓
save jobs.db to data branch
```

## Source Analytics (Shadow Evaluation)

Schema v6 introduced source observations, v7 added persisted source scheduling/health state, v8 added posting-level identity plus conservative cross-source job clustering, v9 added internal description/eligibility evidence fields, and the current schema is v10 with an explicit `preferred_source_key` for canonical apply-link ownership.
This lets the bot compare production LinkedIn with `linkedin_saudi_v2` without
credit depending on which source happened to be processed first. No historical
source-discovery order is fabricated; observation analytics starts when v6 is deployed.

Every run logs a compact Saudi 24-hour comparison for:

- source-wide raw/relevant/fresh counts,
- Saudi job discoveries recorded since observation tracking started,
- first-discovery count/share,
- mature 24-hour exclusive discoveries,
- median lead time before another source sees the same job,
- reliability and coverage gaps.

`exclusive24h` is intentionally delayed: a first discovery is only scored after
it has had a full 24 hours to appear on another source. This avoids declaring a
source "exclusive" too early.

For an on-demand report:

```powershell
python source_analytics.py --db jobs.db --hours 168 --saudi-only linkedin linkedin_saudi_v2
```

The raw/relevant run counters are source-wide. The discovery/first/exclusive
metrics honor `--saudi-only`, so they are the fair part of the Saudi V2 comparison.


### Cross-source deduplication (introduced in schema v8)

`jobs` now represents a real-world opening/cluster while `job_postings` keeps every source-specific posting that points to it. Source identity is checked first using `(source, source_job_id)` or the canonical URL. Only previously unseen postings are considered for conservative cross-source clustering.

Automatic clustering intentionally prefers false splits over false merges. A fuzzy merge requires:

- a confirmed normalized company match (with only curated aliases from `companies/company_aliases.json`),
- a compatible location (Saudi city normalization is supported),
- at least three informative title tokens with strong Jaccard similarity,
- no seniority, technology-stack, or internship/program conflict,
- and a different source that is not already represented in the cluster.

Short generic titles such as `QA Engineer` are not fuzzy-merged automatically. Reposts/new requisitions from the same source are also kept separate unless source identity or the canonical URL proves they are the same posting.

When an official ATS posting and a LinkedIn posting cluster together, the delivery/discovery source remains unchanged, but `preferred_url`, `preferred_source`, and `preferred_source_key` can upgrade to the higher-trust ATS link. Trust is centralized in `source_trust.py`: employer ATS feeds outrank LinkedIn, LinkedIn outranks WUZZUF, and discovery-only sources rank below send-capable boards. A lower-trust observation can never downgrade an official apply link. Telegram keeps both facts visible: for example, a role discovered on LinkedIn can show `Apply on official careers` with `Discovered via: LinkedIn · Apply: HALA Careers (official)`. This preserves honest discovery analytics while preferring the safest canonical application link.

The v8 migration backfills exactly one `job_postings` row for every existing job without guessing historical merges; clustering only starts for observations after deployment.

## GitHub Actions

Workflow:

```text
.github/workflows/job_bot.yml
```

Requested schedule:

```cron
0 */2 * * *
```

This requests a run every two hours. **GitHub Actions is the current production runtime.** The workflow has a `concurrency` group with `cancel-in-progress: false`, restores SQLite from the `data` branch, runs `main.py`, and writes the updated database back.

GitHub's scheduled-event timing is best-effort. The two-hour cadence does not widen source freshness windows or add backfill; jobs can be missed between polls. Manual `workflow_dispatch` runs are useful for verification and, while `VPS_PRODUCTION` is unset/false, can perform normal production sends when `seed_mode=false`.

Do **not** set `VPS_PRODUCTION=true` in the current deployment. That variable is reserved for an intentional future VPS cutover. Once set, scheduled Actions jobs skip production and manual Actions runs are forced into seed mode so two independent SQLite copies cannot both send Telegram jobs.

## VPS Production Runtime (Optional, Not Active)

The repository includes a persistent-host deployment under `deploy/`, but this runtime is currently **prepared only and not activated**:

```text
deploy/
├── install_systemd.sh
├── swe-jobs.env.example
└── systemd/
    ├── swe-jobs.service
    ├── swe-jobs.timer
    ├── swe-jobs-backup.service
    └── swe-jobs-backup.timer
```

The recommended Linux layout is:

- code: `/opt/swe-jobs/current`
- virtualenv: `/opt/swe-jobs/venv`
- configuration/secrets: `/etc/swe-jobs/swe-jobs.env`
- persistent SQLite state: `/var/lib/swe-jobs/jobs.db`
- runtime lock: `/run/swe-jobs/run.lock`
- compressed backups: `/var/backups/swe-jobs/`

`JOBS_DB_PATH` makes SQLite independent from the code checkout. `SQLITE_JOURNAL_MODE=WAL` enables WAL only on the persistent host; GitHub Actions continues to use the default `DELETE` journal mode so its data branch remains a single-file snapshot. The VPS connection also uses `synchronous=NORMAL`, `busy_timeout=5000`, and WAL auto-checkpointing.

`vps_runner.py` takes a non-blocking process lock before calling the normal `run_bot()` path. If another run is still active, the next timer tick exits successfully instead of overlapping it. The systemd timer uses `OnCalendar=*:0/15`, `Persistent=true`, and `AccuracySec=5s`.

Daily backups use SQLite's online backup API rather than copying a live WAL database. `ops/backup_sqlite.py` creates a consistent snapshot, runs `PRAGMA integrity_check`, gzip-compresses it, writes it atomically, and removes backups older than `BACKUP_RETENTION_DAYS` (default 14).

### VPS bootstrap and cutover

No VPS cutover is active today. These steps are kept as a ready rollback-safe deployment path for the future.

If a cutover is intentionally chosen later, clone the repository to `/opt/swe-jobs/current`, then run `sudo bash deploy/install_systemd.sh`. The installer creates the `swejobs` system user, persistent directories, virtualenv, environment file, and systemd units. On a fresh host it also attempts a one-time import of the current `origin/data:jobs.db`, preserving the existing dedup/history state.

Before cutover, fill `/etc/swe-jobs/swe-jobs.env` with the same Telegram token/group/topic IDs used by GitHub. Set `VPS_PRODUCTION=true` in GitHub immediately before the first non-seed VPS run so scheduled Actions stop first. Test with `systemctl start swe-jobs.service` and inspect `journalctl -u swe-jobs.service`. If it fails, set `VPS_PRODUCTION=false` to roll back to GitHub. If it succeeds, enable `swe-jobs.timer` and `swe-jobs-backup.timer`.

The deployment templates intentionally do not contain real secrets. Until that explicit cutover happens, GitHub Actions remains the single production owner.

## Seed Mode

Manual GitHub runs support `seed_mode=true`.

Seed mode stores/baselines jobs without sending them. New source integrations should normally remain in shadow mode across multiple runs before promotion; seed mode is still useful for manual one-time baselining.

## Local Testing

Install dependencies:

```powershell
pip install -r requirements.txt
```

Run tests:

```powershell
python -m unittest discover -s tests -v
```

Run locally from PowerShell:

```powershell
$env:TELEGRAM_BOT_TOKEN="your_bot_token"
$env:TELEGRAM_GROUP_ID="-100xxxxxxxxxx"
$env:TOPIC_MICROSOFT_CLOUD="279"
python main.py
```

Seed locally:

```powershell
$env:SEED_MODE="true"
python main.py
```

## Project Structure

```text
├── main.py
├── config.py
├── models.py
├── db.py
├── db_maintenance.py
├── runtime_lock.py
├── vps_runner.py
├── ops/
│   └── backup_sqlite.py
├── deploy/
│   ├── install_systemd.sh
│   ├── swe-jobs.env.example
│   └── systemd/
├── freshness.py
├── eligibility.py
├── dedup.py
├── source_analytics.py
├── source_runtime.py
├── admin_monitoring.py
├── company_registry.py
├── ats_detector.py
├── telegram_sender.py
├── cleanup.py
├── requirements.txt
├── README.md
├── companies/
│   ├── saudi_ats.json
│   └── company_aliases.json
├── sources/
│   ├── __init__.py
│   ├── ats.py
│   ├── http_utils.py
│   ├── wuzzuf.py
│   ├── linkedin.py
│   ├── linkedin_saudi_v2.py
│   └── jobzaty.py
├── tests/
│   ├── test_admin_monitoring.py
│   ├── test_ats.py
│   ├── test_ats_detector.py
│   ├── test_company_registry.py
│   ├── test_db.py
│   ├── test_db_maintenance.py
│   ├── test_dedup.py
│   ├── test_eligibility.py
│   ├── test_freshness.py
│   ├── test_linkedin.py
│   ├── test_jobzaty.py
│   ├── test_main_sqlite.py
│   ├── test_readme.py
│   ├── test_routing.py
│   ├── test_source_analytics.py
│   ├── test_source_runtime.py
│   ├── test_sources_registry.py
│   ├── test_telegram_sender.py
│   ├── test_workflow.py
│   ├── test_wuzzuf.py
│   ├── test_vps_runtime.py
│   ├── test_backup_sqlite.py
│   └── test_vps_deploy.py
└── .github/workflows/
    └── job_bot.yml
```

## Operational Notes

- **Current production owner:** GitHub Actions. `VPS_PRODUCTION` should stay unset/false unless a deliberate VPS cutover is being performed.
- The workflow cron is `0 */2 * * *` (every two hours). Delayed starts can still occur because GitHub scheduling is best-effort.
- There is currently no automatic long-gap catch-up/backfill mode. Coverage gaps are logged, but a job can be missed if it falls outside a source's later search window.
- Keep the bot as an admin in the Telegram supergroup.
- Configure `TOPIC_MICROSOFT_CLOUD=279` before enabling production sends; no role topic secrets are needed.
- A missing active topic secret causes `CONFIG_ERROR` for jobs assigned to that topic.
- Renaming an existing Telegram topic is safe and does not require changing its secret/thread ID. Only a delete/recreate operation produces a new topic ID.
- Retired Telegram topics can be closed instead of deleted so their historical posts remain accessible.
- Do not publish full job descriptions in the group; cards intentionally stay compact.
- WUZZUF is paused at runtime after repeated 403 responses; keep its parser/tests until a safe re-evaluation is useful.
- LinkedIn and Saudi LinkedIn V2 are send-capable production fetchers. Saudi ATS/company feeds remain the diversification/measurement layer in shadow mode.
- New Saudi sources should be added to the registry/fetch layer first, observed in shadow mode, and promoted only after their freshness/relevance/reliability/lead-time metrics look healthy. Discovery-only feeds must additionally prove safe publication-time semantics before they can ever be promoted.
- Keep the ATS registry small and evidence-driven. Add employers because current data shows useful Saudi tech hiring, not simply to maximize company count.
