# Operator-controlled release-day research

**Readiness: PARTIAL.** Nothing is scheduled or activated. Run manually only within a separately authorized observation window after rechecking source terms and dates. CNA use remains personal/non-commercial; do not publish its receipts or headlines.

## Current calendar evidence

| Release | Scheduled date/time | Evidence and limitation |
|---|---|---|
| BEA Q3 GDP advance; September Personal Income and Outlays/PCE | 2026-10-29 08:30 America/New_York = 12:30 UTC = 20:30 Taiwan | actual BEA schedule GET 200; both rows present; scheduled, not observed availability |
| BLS October Employment Situation | 2026-11-06 08:30 America/New_York = 13:30 UTC = 21:30 Taiwan | official BLS indexed schedule; direct annual schedule GET 403. Direct availability unverified; no retry/bypass |
| BLS October CPI | 2026-11-10 08:30 America/New_York = 13:30 UTC = 21:30 Taiwan | official BLS indexed next-release notice; direct calendar denied; original release access remains unverified |

The November UTC conversion differs because US daylight saving time has ended. Publisher schedule changes or shutdown delays override these preparations. Recheck on the day. Do not turn calendar time into publication or first-seen evidence.

Official references: [BEA](https://www.bea.gov/news/schedule), [BLS employment](https://www.bls.gov/schedule/news_release/empsit.htm), [BLS CPI](https://www.bls.gov/cpi/).

## Minimal local commands

Use Python 3.13 from the repository root. `$studyPath` is a **new local directory outside the Git checkout**. Do not point it at M3/M3.1 evidence or a production ledger. The example plan selects the exact CNA Business feed listed in its publisher directory. It does not assert that CNA necessarily covers US releases.

```powershell
$studyPath = Join-Path $env:TEMP 'MacroRadar-M32-release-day-NEW'
$pythonPath = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python313\python.exe'
# Default: zero HTTP and no root creation.
& $pythonPath -m research.m32_news --root (Join-Path $studyPath 'RUN_V2')
if ($LASTEXITCODE -ne 0) { throw 'Offline preflight failed' }
```

After explicit authorization for that release-day window:

```powershell
& $pythonPath -m research.m32_news --root (Join-Path $studyPath 'RUN_V2') --plan research/M32_PLAN.example.json --cycle cycle_001 --enable-network
if ($LASTEXITCODE -ne 0) { throw 'Stop; inspect receipts, do not retry unknown ACK' }
& $pythonPath -m research.m32_news --root (Join-Path $studyPath 'RUN_V2') --project
if ($LASTEXITCODE -ne 0) { throw 'Stop; projection integrity failed' }
```

This process exits after one bounded sequential cycle. It is not a daemon. Read every terminal status; CLI exit zero alone is not source success. Reusing the same cycle ID never issues a second GET for a reserved request. A later explicitly authorized cycle uses `cycle_002`, at least 1800 seconds after the last selected request. No tight polling, retry loop or scheduled workflow is installed. The example plan caps the entire local run at eight GETs and 8 MB, below the study caps.

## Detection and stop gates

1. Before release: one authorized health request and offline baseline projection; preserve first observations.
2. At/after release: only a later authorized cycle, respecting the 30-minute minimum. A healthy feed with no relevant article is a miss, not success.
3. Candidate criteria: relevant original headline, original URL, parseable time or explicit UNKNOWN, actual retrieval and successful durable receipt; predictions/polls stay expectations. Different article URLs are not forcibly merged.
4. Request a separate bounded official retrieval only for a concrete scoped proposition and a reviewed original endpoint. Never reuse inaccessible BLS paths through proxies, query tricks, search caches or privileged user agents.
5. Stop on denied/rate-limited/redirect/unknown transport results. Preserve reservation and last-good receipts. Do not relabel old articles as breaking after restart.
6. Compare publication → retrieval only as a **source-reported historical discovery interval**. A genuinely newly appearing release with defensible clocks is required before any measured detection claim; a configured interval is not latency.
7. Missing original release, source timestamp, revision availability, world-event identity and global first-seen remain UNKNOWN/PENDING. No formal freeze or trading action is provided.

## Next milestone

Clear a broadly useful news source for the intended public/commercial metadata use, or obtain explicit publisher permission. Then conduct a separately approved prospective release-window experiment. Do not deploy this private CNA projection to the public Radar or Gateway.
