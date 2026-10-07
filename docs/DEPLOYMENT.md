# Standalone demo deployment

This repository contains only the read-only Radar product and bundled EIA
snapshot. Live EIA refresh is opt-in; no persistent disk or account secret is required
by the application. Actual Linux/cloud execution must be verified at deployment;
offline package verification is not a claim of a deployed public service.

## Render Dashboard

After publishing this clean standalone repository to the user's GitHub account:

| Setting | Value |
| --- | --- |
| Service | New **Web Service**, select the published GitHub repository |
| Language | **Docker** |
| Root Directory | Blank (repository root) |
| Dockerfile Path | **`./Dockerfile`** |
| Docker Command | Blank; image entrypoint starts the Radar-only server |
| Health Check Path | **`/healthz`** |
| Persistent Disk | None |

Set these environment variables:

```text
HOST=0.0.0.0
PORT=<platform-provided; do not enter a literal placeholder or pin a port>
RADAR_DATA_ROOT=/app/demo/radar_public
GLOBAL_EVENT_RADAR_NEWS_PATH=/app/demo/radar_public/news
GLOBAL_EVENT_RADAR_OFFICIAL_PATH=/app/demo/radar_public/official-packet.json
RADAR_DEMO_MODE=1
```

Do not configure the optional Polymarket, source-health or MacroView paths.
With an explicit data root the development MacroView fallback is isolated.
There is no browser auto-open. Render provides the external HTTPS endpoint.

References: [Docker on Render](https://render.com/docs/docker),
[Web Services](https://render.com/docs/web-services),
[HTTP health checks](https://render.com/docs/health-checks).

## Local headless run from this exported tree

Using Python 3.12.14, no package installation is needed:

```sh
RADAR_DATA_ROOT=demo/radar_public \
GLOBAL_EVENT_RADAR_NEWS_PATH=news \
GLOBAL_EVENT_RADAR_OFFICIAL_PATH=official-packet.json RADAR_DEMO_MODE=1 \
python -B -m tools.stage1b_historical_campaign.radar_web_server --serve --radar-only
```

Local defaults stay `127.0.0.1:8765`. The web application does not rewrite bundled evidence. Live mode writes only a separate temporary CSV.
For a local Docker test use a temporary port bound only to loopback:

```sh
docker build -t macro-radar-public .
docker run --rm -p 127.0.0.1::8080 -e PORT=8080 -e RADAR_DEMO_MODE=1 \
  -e RADAR_DATA_ROOT=/app/demo/radar_public \
  -e GLOBAL_EVENT_RADAR_NEWS_PATH=/app/demo/radar_public/news \
  -e GLOBAL_EVENT_RADAR_OFFICIAL_PATH=/app/demo/radar_public/official-packet.json \
  macro-radar-public
```

## Acceptance after deployment

Expect 5 Articles / 5 Events / 1 Official Evidence and a visible snapshot notice.
The oil-price event remains `UNVERIFIED_NEWS`; only its linked fact proposition
is `OFFICIAL_CONFIRMED`, with Published shown as Unknown. Other four events have
zero linked evidence. `/healthz` returns only status/service, not source health.
POST/PUT/PATCH/DELETE to the Radar API return 405; other application APIs return 404.

## Git publication, later by the user

Work only from this standalone export, whose own Git root must equal this
directory. Do not publish from the original project or an ancestor repository.
Git author identity must be configured by the user before committing; no author
identity, remote, account or push is configured by the exporter.

After creating an empty GitHub repository, review the files and run:

```sh
git init -b main
git add .
git status
git commit -m "Publish read-only EIA Radar demo"
git branch -M main
git remote add origin <GITHUB_REPO_URL>
git push -u origin main
```

Do not proceed if any command fails. Do not force-add ignored runtime/generated
files. A passing offline export check does not automatically authorize deployment.

## Enable A5.1 after publishing

Keep the existing data/Official/demo configuration and add:

```text
RADAR_LIVE_EIA=1
RADAR_EIA_REFRESH_SECONDS=1800
RADAR_EIA_MAX_ARTICLES=100
```

`RADAR_RUNTIME_ROOT` is optional; leave it unset to use a unique writable OS
temporary session. Never point it inside the bundled demo. No persistent disk
is needed. Runtime refresh state is ephemeral; the validated bundle is always
the restart fallback. EIA acquisition uses HTTPS with normal certificate checking,
one request per cycle, a 10-second transport timeout and no redirects/retries.

Free hosting sleep pauses process-owned refresh. This is not guaranteed 24/7
ingestion. Verify cloud acquisition status after deployment; a local test does
not prove Render can reach EIA. A fetch failure degrades safely without affecting
`/healthz`. The default without `RADAR_LIVE_EIA=1` remains the fixed snapshot.

A5.1 public UI source is `ui/radar_public_showcase_v1.html` in the MAIN repository;
export copies it unchanged. The legacy unified local pages are preserved separately.

## Optional Geography V1 input

Leave `GLOBAL_EVENT_RADAR_GEOGRAPHY_PATH` unset or empty for no geography input.
The bundled snapshot then has 0 mapped events / 5 unknown locations. New live
events without an exact event-ID mapping also stay UNKNOWN, with no map pin.
This does not make the feed unavailable. Missing/malformed optional metadata
likewise keeps the feed and map empty, with `geography_metadata_status=UNAVAILABLE`.

If supported locations have been manually reviewed, set that variable to a
separate JSON file. Relative paths resolve under `RADAR_DATA_ROOT`; absolute
paths are also accepted. This read-only input is not modified or generated by
the web app. Do not rewrite News or Official evidence to add presentation data.
The minimal empty document is:

```json
{"schema":"EVENT_GEOGRAPHY_METADATA_V1","presentation_only":true,"events":{}}
```

`events` maps an **exact existing event_id** to an array of at most 16 points.
Each point requires `place_name` (nonempty text), `country_code` (null or two
uppercase letters), numeric `latitude` (-90..90), numeric `longitude` (-180..180),
`evidence_type="CURATED_PRESENTATION"`, and `evidence_reference` (an HTTP/HTTPS
reference supporting the curator's declared location). Unknown country stays null.
Validation checks shape/ranges, not geographical truth or ISO-country membership.
There is no inference, fuzzy matching, default coordinate or automatic geocoding.
Invalid points are omitted; an event without valid points has null geography.

The API adds `geography_contract=EVENT_GEOGRAPHY_V1`, `geography_metadata_status`,
`mapped_event_count`, `unmapped_event_count` and event-level `geography_status`
and `geography`. Geography IDs deterministically bind event ID and point values.
The map uses the same events; its list supports keyboard navigation to Event
cards/Timelines. All labels disclose **presentation geography**, which never
verifies an event or upgrades proposition-level evidence. Nothing new must be
configured on Render to preserve current snapshot/live behavior.

## Future A5.4 ECB opt-in

After separately publishing/reviewing A5.4, ECB can be explicitly enabled:

```text
RADAR_LIVE_ECB=1
RADAR_ECB_REFRESH_SECONDS=1800
RADAR_ECB_MAX_ARTICLES=100
```

Do not enable these automatically. `RADAR_LIVE_ECB` defaults to disabled and
requires the exact value `1`. Interval range is 300..86400 seconds; retention
range is 1..1000 articles. Existing `RADAR_LIVE_EIA`, EIA interval/retention and
`RADAR_RUNTIME_ROOT` configuration stay supported. When both sources are off,
the original explicitly configured static Radar inputs remain unchanged.

The exact ECB endpoint is `https://www.ecb.europa.eu/rss/press.html`, named
`ECB Press`, from the existing A1 profile. The transport uses normal TLS,
one request per source cycle, a 10-second timeout, a 2 MiB response cap and
no redirects/retries. Only HTTPS article links on `www.ecb.europa.eu` are
accepted. Missing/timezone-less source dates do not become publication dates.

When ECB is enabled, a single owned worker schedules enabled sources separately.
Each source has a separate temporary state directory and article limit; the
combined CSV is atomically published under another unique temporary directory.
Only ingestion writes ephemeral CSVs. API reads never fetch or write. Shut down
the web process normally to stop its owned worker; no external scheduler is needed.
Do not point runtime storage inside the bundled snapshot.

`live_ingestion` remains the EIA acquisition object (its article count is not the
combined total). `discovery_sources` adds EIA and ECB entries with enabled,
status, last attempt/success, interval, article/new counts and a sanitized reason.
No paths/secrets/tracebacks are exposed. ECB states include DISABLED, STARTING,
LIVE, UNAVAILABLE and LAST_VALID_FALLBACK. EIA retains SNAPSHOT_FALLBACK.
The Radar article/event counters reflect the combined data; all missing health
remains Unknown. A source failure retains its own previous valid data and never
erases another source's success. All five pinned EIA rows remain restart fallback.

ECB discovery does not create Official Evidence or verified events and does not
place Frankfurt map pins. Existing EIA proposition evidence remains scoped to
its exact event. `/healthz` stays process-only; write routes remain rejected.
The offline package passes deterministic fixture tests, but future deployment
must verify Render's access to ECB independently of local fetch results.

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
SQLite. See [RADAR_INTELLIGENCE_STORE.md](RADAR_INTELLIGENCE_STORE.md) for time semantics, read-only replay and storage configuration. Do not
enable public persistence before durable cloud storage is separately reviewed.

## A7 context intelligence

See [RADAR_CONTEXT_INTELLIGENCE.md](RADAR_CONTEXT_INTELLIGENCE.md) for event/context/institution separation and map semantics. Public persistence remains disabled.

The public Git release manifest separates `files` (reviewed working-tree bytes)
from `git_clean_files` (expected committed bytes after Git line-ending filtering).
The prepared publication guard verifies both; source snapshots are not rewritten
and no Git/system configuration is changed.
