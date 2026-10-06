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
administrative runtime are included. The opt-in EIA refresh thread belongs to the web process.

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

Enable `RADAR_LIVE_EIA=1` for one EIA Today in Energy RSS fetch on startup and
periodic refresh while the service is active. `RADAR_EIA_REFRESH_SECONDS=1800`
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
