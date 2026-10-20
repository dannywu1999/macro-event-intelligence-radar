# M3.4 BEA source contract — official-origin research only

Version: `M3.4_BEA_READINESS_V1`. Parent: `e5157d8992385491c77441272a6dea0f9d9515ae`.

## Directly verified endpoints

| Endpoint | Purpose | Clocks / limitation |
|---|---|---|
| https://www.bea.gov/news/schedule | Planned release identity | Calendar only, never observed announcement |
| https://www.bea.gov/news/current-releases | Official release metadata, preferred primary | Source-reported zoned datetime, not first online availability; current list replaces prior entries |
| https://www.bea.gov/resources/for-developers | Original publisher advertises exact RSS URL | Documentation only |
| https://apps.bea.gov/rss/rss.xml | Secondary official announcement list | Source-reported RSS publication clock; incomplete: missing August 2026 PIO found in current list |
| https://www.bea.gov/help/faq/147 | Rights evidence | BEA information generally public domain unless otherwise stated; cite BEA; no blanket rights to third-party works, logos or external linked tables |
| Original release URL | Concrete statistical document | Only exact HTTPS BEA release links actually extracted from verified current list or RSS; never guessed future slug |

Eight direct requests on 2026-10-20 succeeded; actual total payload 479,477 bytes. Raw responses remain outside Git. `M34_CURRENT_PREFLIGHT.json` binds each URL, request/response/recording clock, Content-Type and SHA256. HTML decoded strictly UTF-8; response declared Content-Type retained. No authentication, paid API, alternate identity, redirect following or retry used. The separate web research tool also read the three official documentation pages; those are not direct collector receipts or part of the eight measured GETs.

BEA's current policy permits use/reproduction of its own information unless otherwise indicated. Public summaries here contain metadata, numeric facts and brief attributed extracts, not logos, charts or linked third-party material. Publication of a future summary still requires exact-item review. No periodic/commercial news licence inferred for another publisher.

No specific BEA RSS polling-rate entitlement or availability SLA was found. **1800 seconds per resource is this experiment's conservative manual minimum, not a BEA-published quota or permission guarantee.** Recheck terms/rate notices on release day; stop if incompatible. Honour denial, redirect and Retry-After by stopping, never bypassing them. No periodic scheduler is installed.

## Identities and clocks

Target families remain separate: `GDP_Q3_2026_ADVANCE` and `PIO_SEPTEMBER_2026`. PCE is not CPI; regional/state PCE is not monthly national PIO. Same scheduled time does not merge events. Source URL identity and family identity are both retained. Known RSS `GDP, (` versus HTML `GDP (` renderer punctuation is normalized only for comparison; original titles remain intact.

October 29 08:30 America/New_York is 12:30 UTC / 20:30 Asia/Taipei, with `zoneinfo` validation. The schedule was read directly on October 20; recheck it before pinning a new release-day plan. A scheduled time and an embargo instruction are not actual online publication receipts.

`request_started_at`: before GET. `response_observed_at` / `retrieved_at`: complete body-read boundary, **not header arrival**. Raw M3.1 ACK `recorded_at` is sampled before ACK fsync; it is preserved as `ack_prewrite_recorded_at`. M3.4 derived `recorded_at` uses terminal completion sampled after body/ACK/parsed fsync, a conservative durable-availability boundary. `receipt_sha256` binds the unchanged raw ACK; body and parsed content have separate hashes. These are local research provenance, not signatures issued by BEA.

Publication time is source-reported, with EXACT_SOURCE_REPORTED / DATE_ONLY / UNKNOWN. Missing remains null; invalid, timezone-less, repeated/conflicting publication clocks or publication after observation fail closed. Revisions retain old observations. Retrieval-only clock changes are DUPLICATE. Announcements and original-document body revisions are separate evidence layers; metadata change alone does not prove a statistical revision. Revision's actual publication time remains unknown absent source evidence.

## Safety and scope

Default CLI: offline, zero network, no root creation. Only explicit `--enable-network` acquires. All audit/list/original resources in one root share **15 GET / 5,000,000 bytes**, including failed/unknown reservations. Unknown ACK reserves maximum body bytes; worst-case next-body capacity must fit. Per response max 2 MiB, inherited timeout/deadline and no redirects. Any failed/interrupted request pauses further acquisition. Spent request IDs cannot be replayed. Do not reset a root to renew budget.

Immutable plan binds actual schedule/terms/RSS-discovery ACKs and body hashes. One OS budget lock and one cycle lock; no production ownership or persistent background process. Original-document namespace binds exact URL and original discovery receipt. Data is append-only/exclusive-write; snapshots cannot overwrite. As-of uses durable recording, excludes future revisions, and reports UNAVAILABLE before plan availability.

No Production, runtime, source registry, old M3/M31/M32/M33 receipts, collector, Owner/Claim, D1, H2, trading or frozen-PIT authority changed. Official-origin discovery is not independent news. Official document origin does not automatically verify every proposition. MacroView remains research PREVIEW; Frozen, expectations, market reaction and trading authorization remain unavailable/unknown.
