# V4.9 persistent news capture readiness

This candidate is deployment code, not an activated service. Capture defaults OFF.
No import, public HTTP request, or Research Workspace action starts a collector.

## One lifecycle and one writer

The existing radar_web_server starts at most one dedicated capture child only when
RADAR_NEWS_CAPTURE=1 and RADAR_NEWS_CAPTURE_CONFIG explicitly names a valid private
configuration file. The child reuses ProspectiveRunner, source adapters,
IntelligenceStore, append-only identities and the existing namespace OS lock.
HTTP threads only project evidence. The legacy visitor-driven News acquisition
and IntelligenceRecorder are excluded while dedicated capture is requested.
Missing configuration/storage or a failed child does not stop safe HTTP serving.
There is no automatic child restart loop, alternate ledger or protected Owner use.

## Configuration and storage contract

The config is strict NEWS_CAPTURE_SERVICE_V49 JSON with these required fields:
scope, root, durable_root, volume_id, ledger_id, providers, daily_quota,
per_source_quota, interval, max_backoff, max_storage_bytes, warning_bytes,
min_free_bytes, initialize, activation_approved, fixture_path, contract.

Production scope PRODUCTION_DURABLE_CAPTURE requires activation_approved=true,
fixture_path=null, an explicitly approved volume marker and a kernel-verified
mount point at durable_root. A read/write/fsync probe must pass. Path links,
temporary storage, source-tree storage and legacy pilot adoption are rejected.
The marker is an operator attestation, not proof a cloud subscription was bought.
Production activation still requires a separately reviewed mounted Render disk.
ISOLATED_LOCAL_PILOT uses a distinct test-volume role and cannot be promoted.

The private marker RADAR_DURABLE_VOLUME_V1.json binds volume_id and volume role.
CAPTURE_SERVICE_V49.json pins policy identity. Paths can change in a verified
restore, while scope, logical identity and quota policy remain fixed. An existing
pilot or a policy mismatch never triggers automatic migration/reset.

## Quota, cadence and backoff

UTC daily total/per-source quotas are append-only SOURCE_STATE observations in
the SAME IntelligenceStore. Reservation and quota increment commit atomically
before transport. A crash leaves the reservation spent and uncertain. Restart
does not reset quota. The next UTC day creates a new account without deleting old
days. Clock rollback fails closed. Quota exhaustion makes no request.

Only ECB Press, Global Voices and EIA Today in Energy adapters are accepted.
Polling is sequential; minimum cadence1800sec. Failures use exponential backoff
up to the configured cap; HTTP403/406 opens a persistent circuit immediately and
five consecutive other failures also pause the source. Explicit offline operator
acknowledgement is required, after capture has stopped; quota/cadence/history are
retained and HTTP has no acknowledgement endpoint. There are no retries
within an attempt and no restriction bypass. Transport retains its22sec wall
deadline. Poll cadence is not measured event detection latency.

## History, checkpoints, retention and capacity

The old finite pilot retains its60-lifetime-request and20000-row safeguards.
The authorized persistent mode streams integrity recovery in2000-row pages and
queries bounded latest working state; it does not load or truncate full history.
Per-event/history and active-article limits remain explicit fail-closed bounds.
Checkpoint compaction means only rebuilding derived current state, never deleting
ledger rows, receipts or as-of evidence. Corrupt derived checkpoints are preserved
and rebuilt. A torn receipt can be recovered only from committed ledger metadata;
conflicting receipt bytes stop capture. All original source-body hashes remain.

Retention policy: APPEND_ONLY_NO_AUTOMATIC_DELETION. Capacity warnings are visible
in capture status; configured capacity/free-space exhaustion stops capture before
another reservation. No retention purge, automatic quota increase or forced
history rewrite occurs. Capacity must be reviewed before any limit is reached.

## Backup and restore

backup_capture uses SQLite's backup API and produces a hash-bound receipt
inventory from the database snapshot. verify_backup verifies policy, database
SHA256, complete inventory, receipt hashes, SQLite integrity and every evidence
identity. restore_capture requires a new destination and does NOT start capture.
Restoring a backup appends a recovery fence until the next UTC day because
post-backup request usage may be unknown. Raw backup images cannot be started as
live capture namespaces. Operator restore preserves the old directory and never
backfills knowledge across a downtime gap.

## Public interface and authority

The public projection reads an approved namespace, verifies derived News against
ledger state and exposes safe status/clock/version summaries only. It excludes
database files, raw checkpoints, private paths, control files and volume IDs.
Capture OFF reports NOT_RECORDED; unproven first-seen/latency stays UNKNOWN.
Local evidence remains explicitly local. The UI distinguishes a future authorized
durable scope without changing official proposition authority or freeze rules.
As-of queries preserve related evidence identity versions and exclude later data.
Historical ECB remains DATE_ONLY/EX_POST/NOT_ESTABLISHED; no synthetic prices,
trading signals, retroactive PIT or verified Polymarket link is manufactured.

## Deployment decision

Preferred topology: one paid Render web instance, one persistent disk mounted at
/var/data/radar-evidence, one application and one owned child. No cross-service
SQLite sharing or horizontal workers. Activation, payment, published revision,
backups, retention and native disk/redeploy acceptance require separate approval.
This repository contains no command to purchase, upgrade or configure cloud resources.
