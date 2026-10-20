# M3.3 manual release-window plan — PARTIAL

No future automation or capture is enabled. A future release-window experiment requires its own explicit authorization. Current source selection does not demonstrate timely independent coverage of US CPI, employment or PCE.

## Revalidated schedule

| Release | Scheduled publisher time | UTC / Taiwan | Evidence |
|---|---|---|---|
| BEA Q3 GDP advance and September Personal Income and Outlays/PCE | October 29, 2026 08:30 America/New_York | 12:30 UTC / 20:30 Taiwan | Actual BEA schedule HTTPS 200 in M3.3; both rows present |
| BLS October Employment Situation | November 6, 2026 08:30 America/New_York | 13:30 UTC / 21:30 Taiwan | Official schedule read through web tool; not proof of direct collector availability |
| BLS October CPI | November 10, 2026 08:30 America/New_York | 13:30 UTC / 21:30 Taiwan | Official CPI next-release notice through web tool; original collector access not recovered |

Sources: [BEA schedule](https://www.bea.gov/news/schedule), [BLS employment schedule](https://www.bls.gov/schedule/news_release/empsit.htm), [BLS employment next-release/time-zone notice](https://www.bls.gov/cps/), [BLS CPI](https://www.bls.gov/cpi/). BLS denied direct access in preceding evidence; this task did not retry or evade it. US daylight saving time ends before the November releases, hence the different UTC offset. Scheduled time is not measured HTTP availability. Recheck publisher changes on the day.

## One repeatable bounded research procedure

Prerequisites: explicitly authorize the window, verify source terms, retain one experiment identity, and ensure the original reviewed item/terms proof bundle is present. The M3.3 proof-bound context projection is not a universal auto-licensing engine: new items require separate item review. It cannot turn an unrelated analysis or a Fed calendar into CPI/Employment detection.

From the isolated M3.3 checkout, with `$studyPath` pointing to this experiment's existing local evidence directory outside Git:

```powershell
$pythonPath = Join-Path $env:USERPROFILE 'AppData\Local\Programs\Python\Python313\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Canonical Python not found; stop and locate the approved executable' }
# Offline and read-only. No network is implied by previewing retained evidence.
& $pythonPath -m research.m33_public --study $studyPath
if ($LASTEXITCODE -ne 0) { throw 'Offline preflight failed' }
& $pythonPath -m research.m33_public --study $studyPath --public
if ($LASTEXITCODE -ne 0) { throw 'Stop: rights/receipt gate failed' }
```

Only after separate authorization for a later observation and after >=1800 seconds from the last selected-source reservation:

```powershell
& $pythonPath -m research.m33_public --study $studyPath --plan research/M33_PLAN.example.json --cycle cycle_003 --enable-network
if ($LASTEXITCODE -ne 0) { throw 'Stop; inspect terminal status. Do not retry uncertain ACK' }
& $pythonPath -m research.m33_public --study $studyPath --public
if ($LASTEXITCODE -ne 0) { throw 'Stop: do not publish the output' }
```

This command makes at most one sequential GET per selected source and exits. No service persists. A spent cycle ID is never replayed as a new request; original failure remains failure. The selected plan caps all DATA requests, including five qualification requests, at nine. It is a bounded research plan, not a renewable production budget. Do not remove reservations or increase a frozen budget to continue.

## Event and evidence gates

1. One authorized pre-release health observation; retain the baseline and actual clocks.
2. One later authorized observation after the scheduled release and the >=30-minute cadence. A healthy feed with no relevant announcement remains a miss.
3. A genuine news report requires a relevant original claim, valid attribution, item-level public/commercial rights and real publication/observation receipts. Commentary/polls/analysis stay their own types.
4. Retrieve a reviewed original official source only for a concrete proposition. Keep unavailable original evidence PENDING. No cache or calendar substitutes for direct source availability.
5. Calculate publication-to-retrieval interval only when source timestamps justify it; label historical discovery delay separately. First observed in this study is not global first-seen. Unknown publication, uncertainty about revision timing or missing original release means detection latency UNKNOWN.
6. Stop on denial, redirect, rate limit, timeout/unknown ACK, exhausted budget, integrity mismatch or unclear rights. Preserve last-good receipts and inspect offline; no automatic retry.

## Missing capability and fallback decision

The selected feeds support an official monetary-release fallback and licensed analysis context. They do not establish a successful upcoming CPI/Employment/PCE discovery test. BEA original information is rights-cleared and its current-releases HTML/API machinery already exists in M3.1; a separately versioned and authorized BEA-only official-origin window is the practical fallback for October 29. Do not silently add a third source to this frozen M3.3 plan or claim independent reporting.

Before public independent-news activation, obtain suitable publisher metadata permission and demonstrate a genuinely relevant current feed. The publisher request packet is prepared separately; no message has been sent.
