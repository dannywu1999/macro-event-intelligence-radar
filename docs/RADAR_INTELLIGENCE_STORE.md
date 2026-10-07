# Radar intelligence store and reality replay (A6, not deployed)

## Four distinct layers

- Current projection: the existing CSV/packet/provider view. It works without a DB.
- Observation ledger: append-only versions recorded in SQLite, with system time.
- Persisted MacroView: the existing `MACROVIEW_FREEZE_V0`, built from visible ledger
  records and stored by value with hashes; no new fact or decision contract.
- Replay: `POINT_IN_TIME_REPLAY_V0`, SQL-filtered by system observation time.
  Historical versions and latest active versions are distinguished explicitly.

**Invariant:** only `observed_at <= as_of` is visible. Imported CSV observation
fields, publication dates, market close times and later curated links cannot
backdate ledger knowledge. No pre-ledger history is reconstructed or claimed.
A reconstruction is labeled non-persisted; it does not pretend a freeze was
created at the historical time. Stored freezes retain separate creation time.

## Configuration

Persistence is disabled by default. `RADAR_PERSIST_INTELLIGENCE=1` explicitly
starts one process-owned recorder, which reads existing projections only.
It performs no provider request and provides no public write API.

`RADAR_INTELLIGENCE_DB` selects an absolute/portable DB path. Otherwise use
`RADAR_RUNTIME_ROOT/intelligence/radar_intelligence.sqlite3`; for opted-in local
use without either variable, the user's `.global-event-radar/intelligence`
directory is used. Paths inside the application source tree are rejected.
`RADAR_INTELLIGENCE_RECORD_SECONDS` defaults to 60, range 5–86400 seconds.
Identical snapshots do not duplicate observations or freezes. A recorder error
stops that recorder; there is no automatic repair or failure retry loop.

For local validation, choose a temporary runtime directory. For future server
operation, explicitly choose a persistent writable directory owned by the app.
Do not enable persistence on the current public deployment in this release.

## Database and failure behavior

SQLite standard library; schema `RADAR_INTELLIGENCE_DB_V1`:
`observations`, `macroview_freezes`, `schema_metadata`.
Canonical UTF-8 JSON and SHA256 bind contents/identities. Changed observations
append new rows. UPDATE/DELETE triggers protect historical tables.
WAL lets a writer and readers coexist; transactions and a 3000ms busy timeout
bound contention. Connections close after every operation. No SQL extensions,
external SQL, migration framework or automatic migration. Newer/unknown schemas
fail closed for storage/replay. The current Radar and health endpoint stay usable.
The database is not cryptographically anchored against an administrator rewriting
its physical files. Protect the storage volume and backups separately.

## Read-only replay API

`GET /api/app/replay?event_id=<canonical-event-v0-ID>&as_of=<timezone-bearing-ISO>`

400: invalid/duplicate/excessive parameters or invalid time.
200 + `NO_OBSERVATIONS`: no event knowledge at that time, including unknown IDs.
503 + bounded error: unconfigured, missing, corrupt or inaccessible store.
Responses disclose no DB path, SQL or traceback. Requests never initialize a
store, record observations, create freezes, read current evidence or fetch sources.
All write methods remain 405. UI uses system observed time, not publication order.

## Limitations and deployment gate

This is a local durability foundation, not cloud durability approval. A free
Render deployment may have an ephemeral filesystem. Durable operation requires
an attached durable volume or an external managed store (not implemented here).
No account/resource purchase or cloud change is part of A6. Backup/export,
retention/pagination, external integrity anchoring and distributed writers are
future work. Omission from a retained feed is not inferred as factual retraction.
No interpretation, market direction or trading authority is introduced.
