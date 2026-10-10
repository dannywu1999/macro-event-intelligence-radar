# Macro Event Intelligence Radar

A read-only event intelligence demo that keeps **news discovery** separate from
**proposition-level official evidence**.

**News Discovery → Canonical Event → Official Evidence**

The bundled public snapshot contains **5 EIA news articles, 5 conservative
Canonical Events and 1 linked Official Evidence record**. It demonstrates source
provenance, chronological article presentation, deterministic event/evidence
identities and transparent missing-data handling.

## What the demo shows

- News remains `UNVERIFIED_NEWS`, including reports from an official agency's feed.
- Official evidence confirms **a specific proposition**, not the entire event.
- The selected oil-price event has one linked `OFFICIAL_CONFIRMED` proposition;
  the other four events have none. Publication time remains null/Unknown.
- The Showcase UI presents article/event/evidence counts, original source links,
  observed/source timestamps and UNKNOWN source health when no health evidence exists.
- `PUBLIC DEMO · READ-ONLY SNAPSHOT` identifies the immutable dataset.

With live ingestion disabled, this public snapshot has **no automated live ingestion**. It is not exhaustive
global coverage and does not promise production uptime. This repository/demo
**does not perform live trading**, price prediction or order execution.

## Bilingual visual experience

Choose **中文 / EN** in the header. Browser language selects the initial display;
localStorage remembers the choice. The visual flow shows real 5 / 5 / 1 counts.
The evidence-linked event is prioritized for display only, with its proposition
expanded. News remains unverified. Details preserve original source text and IDs.

`ui/radar_demo_translations.js` contains manually written presentation-only
Traditional Chinese summaries for the fixed demo, keyed by event/evidence IDs.
They are not official EIA translations and never enter the adapter or API.
Original English remains the evidence of record.

Focused offline tests: `python -B -m unittest discover -s tests -v`. Frontend
behavior tests use Node.js without third-party packages; Node is test-only and
is not a runtime/container dependency. The optional browser preview harness
uses an already-installed Playwright/browser and only a temporary localhost server.

## Implementation

Python 3.12.14 standard-library HTTP backend, one read-only Radar adapter,
HTML/CSS/JavaScript Showcase UI, Docker-ready deployment and SHA256 release
provenance. No database, frontend build or third-party Python package is required.
The existing Python package paths are preserved for import compatibility.

The container is non-root, and the application only serves its UI, Radar API
and minimal `GET /healthz`. Mutation methods are rejected; no legacy collectors or
administrative runtime are included. Opt-in News sources use single-flight, request-triggered TTL refresh in the web process.

## Run and deploy

Use the root `Dockerfile` with a Render **Docker Web Service**. Environment
configuration selects the bundled snapshot, headless startup and platform port.
See [Deployment](docs/DEPLOYMENT.md) for exact settings and local commands.

Public route after deployment: `https://<service-name>.onrender.com/#/feed`.
No public URL is claimed before the service is actually deployed.

`PUBLIC_RELEASE_MANIFEST.json` records each other package file's relative path
and SHA256. `demo/radar_public/metadata.json` records immutable data hashes and IDs.

## Attribution

Source: **[U.S. Energy Information Administration](https://www.eia.gov/todayinenergy/)**.
Original EIA article/evidence links are preserved. No EIA logo is reproduced.
This independent demonstration is **not endorsed by EIA**.

## Cloud Live EIA Ingestion V1

Enable `RADAR_LIVE_EIA=1` for one EIA Today in Energy RSS fetch on the first due
Radar read; later reads refresh only after the source TTL. `RADAR_EIA_REFRESH_SECONDS=1800`
(default; minimum 300, maximum 86400) controls the interval.
`RADAR_EIA_MAX_ARTICLES=100` controls total retention (5 to 1000). All five
validated bundled articles are pinned; additional articles are retained newest
first by reported time, or observation time when publication is unknown.
Unchanged source URLs keep their original observations/content and event IDs.
No automatic retry occurs inside a cycle, and no new source is enabled.

`RADAR_RUNTIME_ROOT` optionally selects a writable temporary runtime directory.
The default uses the OS temporary directory with a unique session subdirectory.
State is ephemeral: each restart begins with the unchanged bundled snapshot.
A persistent disk is not required. Free hosting may sleep, so this is **not
guaranteed 24/7 ingestion** or real-time breaking-news monitoring.

The API adds `live_ingestion` acquisition status (DISABLED / STARTING / LIVE /
SNAPSHOT_FALLBACK), last attempt/success, interval and counts, with no paths or
secrets. A failed refresh keeps the last valid runtime feed or bundled snapshot.
The bilingual UI states that fallback explicitly. Source factual health remains
separate. New EIA RSS articles are always UNVERIFIED_NEWS, and never gain
Official Evidence merely because EIA published them. Existing proposition evidence
remains linked only to its original event. Original English is shown when a live
article has no manually defined Chinese presentation summary.

## Event Timeline V1

Each event has an expandable, deterministic Timeline derived solely from its
existing article references and explicitly linked Official Evidence IDs. News
entries prefer valid reported times, otherwise label stored detection time;
proxy source dates never become publication times. Official entries prefer
publication when known, otherwise clearly label first observation or retrieval.
Missing times stay null in the API and appear in a separate Time unknown section.
Readable UI dates show UTC explicitly with exact ISO values retained in tooltips.

`timeline`, `timeline_count`, `timeline_contract` and `status_summary` are additive
event fields. Stable entry IDs bind event/type/source identity, not display order.
Current status is undated: the event remains UNVERIFIED_NEWS, and Official
Evidence confirms specific propositions only. The evidenced demo Timeline opens
by default; other events stay compact. No timeline database, new links, inferred
event creation/occurrence times, AI summaries or mutation endpoints are added.

Timeline works with live refresh and snapshot fallback alike. V0 often produces
singletons; multi-article events show all explicit members, without expanding
clustering rules. This is a current evidence projection, not an append-only
historical change log; articles removed by retention are no longer in the view.

## Geography and World Map V1

The bilingual Showcase adds an inline SVG longitude/latitude grid, mapped-event
count, location-unknown count and an accessible event list. This is a simple
equirectangular coordinate background, not a detailed geographic basemap.
Keyboard/click activation focuses the same Event card and opens its Timeline.
Events at identical coordinates share a marker but retain separate event controls.

The bundled EIA data has **no explicit supported event coordinates**. Its default
result is **0 mapped / 5 location unknown**, without fabricated pins. Live articles
remain unmapped unless explicit metadata for their exact stable event ID exists.
Headline mentions, publisher location, company/instrument associations and source
country never determine coordinates. Missing geography stays null/UNKNOWN.

Optional `GLOBAL_EVENT_RADAR_GEOGRAPHY_PATH` reads a separate curator-supplied
`EVENT_GEOGRAPHY_METADATA_V1` JSON document. V1 accepts only explicitly labeled
`CURATED_PRESENTATION` points; it does not extract or officially verify geography.
Known here means valid declared presentation metadata, not a confirmed world-event
location. The UI discloses this distinction. No default coordinate metadata is
shipped. See [Deployment](docs/DEPLOYMENT.md) for the input contract.

Geography adds fields without changing event identity, article membership,
verification, Official Evidence or Timeline. No external map assets, geocoder,
AI extraction, location network requests or new package dependencies are used.

## Multi-Source Discovery V1 (ECB opt-in)

`RADAR_LIVE_ECB=1` adds **ECB Press** as a second independently refreshed News
discovery source. It is **disabled by default**. Name and endpoint reuse the
existing A1 source profile: `https://www.ecb.europa.eu/rss/press.html`.
This is headline discovery, not an expansion of the Official Evidence contract.
Every ECB article/event remains UNVERIFIED_NEWS with no automatic official fact
record. ECB headquarters never supplies an event location.

Both providers use the same five-column CSV/article pipeline, exact source/URL
identity and separate retention, status and last-valid state. Similar headlines
across sources are not merged by ingestion. EIA's five pinned snapshot articles
and its specific proposition evidence remain protected from ECB retention.
Missing source publication stays blank/null, independent of observation time.
Timeline and Geography use the same existing event projections.

When ECB is enabled, one process-owned worker coordinates both enabled sources
with separate intervals and bounded sequential fetches. There are no per-item
threads, retries inside a cycle, collector lifecycle dependencies or new APIs.
ECB failure cannot revert a successful EIA acquisition; EIA failure cannot erase
valid ECB articles. ECB starts empty, reports UNAVAILABLE on initial failure,
and LAST_VALID_FALLBACK after a failure with retained data. The existing EIA
environment flags and `live_ingestion` response retain their EIA-only meaning.

The API adds `discovery_sources`; the compact bilingual **Live Discovery Sources**
section shows enablement, acquisition status, last success and per-source article
counts. Acquisition is separate from source health and factual confirmation.
EIA snapshot fallback is retained even in ECB-only mode. No real ECB data is
bundled: offline fixture URLs/titles are explicitly synthetic test data.
See [Deployment](docs/DEPLOYMENT.md) for future opt-in settings. Free hosting
may sleep; these sources do not provide guaranteed continuous/global monitoring.

## Market expectations (pending release, disabled by default)

`RADAR_LIVE_POLYMARKET=1` explicitly enables one process-owned public Gamma
request per bounded refresh interval (`RADAR_POLYMARKET_REFRESH_SECONDS`, default
1800, minimum 300). No credentials, retry, persistent state or factual authority.
Keep it disabled until a separately authorized release. API reads never fetch.
`GLOBAL_EVENT_RADAR_POLYMARKET_PATH` may supply recorded Gamma rows with explicit
`observed_at`; absent time remains unavailable, never filled with current time.
`GLOBAL_EVENT_RADAR_EXPECTATION_LINKS_PATH` optionally reads a JSON object with
`schema: EXACT_MARKET_LINKS_V1` and `event_to_market` mapping exact existing event
IDs to exact market IDs. Missing, wrong or ambiguous mapping leaves markets
unlinked. No example mapping is enabled. `outcomePrices` values retain provider
precision/type, labeled provider outcome prices (0–1), without recalibration.
Market URLs require a unique provider-supplied event slug, never title matching.

## MacroView V0 (pending release)

The API includes bounded `MACROVIEW_PREVIEW_V0` projections of existing evidence;
these are explicitly **not persisted frozen snapshots**. Internal pure
`freeze_macroview` requires an explicit key and optional timezone-bearing time.
It copies complete selected News, proposition and linked expectation contents
with deterministic IDs/hashes. Later source changes cannot mutate old values.
Facts are `NEWS_ONLY` or `PARTIAL_OFFICIAL_EVIDENCE`; expectation snapshots remain
independent. Unknowns stay explicit. There is no write endpoint, archive, decision,
market direction or trade authorization. The deployment remains read-only.

## A6 local replay foundation (not deployed)

Persistence is opt-in and disabled by default. Current Radar does not depend on
SQLite. See [docs/RADAR_INTELLIGENCE_STORE.md](docs/RADAR_INTELLIGENCE_STORE.md) for time semantics, read-only replay and storage configuration. Do not
enable public persistence before durable cloud storage is separately reviewed.

## A7 context intelligence

See [docs/RADAR_CONTEXT_INTELLIGENCE.md](docs/RADAR_CONTEXT_INTELLIGENCE.md) for event/context/institution separation and map semantics. Public persistence remains disabled.

The public Git release manifest separates `files` (reviewed working-tree bytes)
from `git_clean_files` (expected committed bytes after Git line-ending filtering).
The prepared publication guard verifies both; source snapshots are not rewritten
and no Git/system configuration is changed.


Current News discovery flags, optional UN News obligations, failure diagnostics and
Render cold-start semantics: [RADAR_V4_FRESHNESS.md](docs/RADAR_V4_FRESHNESS.md). Broad discovery is not enabled by EIA/ECB flags alone.
