# V4.2 News Intelligence Feed

The existing read-only Radar API adds `news_intelligence` (NEWS_INTELLIGENCE_V1).
No collectors, permissions, storage, canonical identities or source flags change.

## Brief selection

- At most five items published in the last **48 hours**. The visible “Today” brief
  explicitly says 48 hours; it is not a calendar-day or exhaustive global bulletin.
- A genuine source publication timestamp, original HTTP/HTTPS provenance and the
  existing macro title relevance rule / curated EIA or ECB context are required.
- Newest first. Specific linked official evidence breaks identical-time ties only.
- Missing, proxy, naive or future dates never qualify. Never fill with old reports.
- Only the adapter's existing same-day explicit rate-decision primitive can join
  a multi-article brief/developing group. No country/topic deduplication. Every
  article remains in the complete chronological feed.
- Novelty is NOT_ESTABLISHED: first observation does not prove a new world event.

## Cards and truth boundaries

Original headline, author/publisher, original link, reported/proxy and observed
clocks remain visible. Chinese category hints are **not full translations**.
Potential mechanisms are deterministic terminology hints, not demonstrated
market effects. Existing institutional context is reused where available.
Unsupported explanation stays Unknown. Only exact event-linked, nonempty,
OFFICIAL_CONFIRMED propositions count; news/event status stays UNVERIFIED_NEWS.
One button opens the existing event detail, timeline, evidence and context.
No news body, images, paid translation API or investment recommendation is added.

The map remains before Watch. PREVIEW/FROZEN, replay knowledge time, geography
and expectation-linking contracts are unchanged. Source acquisition/cache clocks
remain separate from health. Timeout preserves existing valid data.

## Sources and release

No new source. EIA/ECB continue existing opt-ins; Global Voices retains author,
original links and licence credit. UN News requires activation AND acknowledgment.
Guardian remains opt-in subject to its acknowledgment; BBC has no active profile.
Rights and broad breaking-news coverage gaps documented in V4 freshness remain.
PUBLIC includes only explicit export allowlist files with raw and Git-clean hashes.
Tests use isolated fixtures; actual-browser acceptance is recorded separately.
This change does not deploy, commit, push or change hosting environment settings.

## V4.6 News-to-research bridge

`news_intelligence.cards[*].event_triage` adds a read-only research path per
source-backed article. It preserves the original headline, publisher and URL,
publication-time value and precision, first observed time, and the latest
provider check time/status when available. Missing clocks remain Unknown.

An article receives a canonical event identity only when it belongs to exactly
one current event. Official propositions are exposed only when both the
canonical event ID and explicit official-evidence ID match. `OFFICIAL_PARTIAL`
means linked propositions are supported; it does **not** confirm the full News
article. Conflicting evidence copies remain `CONFLICTING_EVIDENCE`; absent
proposition links remain `SOURCE_REPORTED_ONLY` or `NOT_VERIFIED`.

Only an unambiguous event with an explicit ECB identity and monetary-policy
terms in the source title may link to packaged ECB cases. The relationship is
`SAME_POLICY_TOPIC`, not an outcome prediction. Other articles show
`NO_VALID_HISTORICAL_ANALOGUE` and `MARKET_OBSERVATION_NOT_AVAILABLE` unless an
existing instrument-specific case is actually applicable. Historical ECB
values remain daily EX_POST observations with DATE_ONLY clocks and the existing
causality/PIT limits. These cases are not added to current News counts.

Prospective recording continues to use the existing opt-in append-only
intelligence ledger. Recording time is system time; importing a historical
article cannot make it appear in a past as-of view. This bridge starts no
collector and exposes no public write endpoint.


## V4.6 prospective research candidate

News cards open the existing bilingual research workspace with independently labelled publication, upstream observation, provider check, browser display, acquisition and ledger registration clocks. First-observation latency remains UNKNOWN unless its basis is explicitly recorded. Global Voices author attribution resolves to its provider state.

`python -m tools.stage1b_historical_campaign.radar_news_intelligence --capture-snapshot <public snapshot> --retrieval-receipt <receipt> --pilot-root <new external directory> --article <exact reference>` is a bounded explicit one-shot metadata pilot. It creates a NEW isolated IntelligenceStore, content-addressed receipts and non-authoritative previews. No workers, provider requests, write API, protected ledger or authoritative MacroView freeze are created. The existing replay API reads the captured store only when configured explicitly. Capture in 2026 never establishes 2025 knowledge. Receipt hashes bind title/source/time metadata, not full article text.

ECB meeting notices, speeches, forecasts, operational guidelines and non-rate decisions do not receive rate-decision analogues. Current observations remain unavailable; genuine historical ECB daily rates retain DATE_ONLY / EX_POST / NOT_ESTABLISHED and are not executable prices. Historical cases never become current News.


## V4.7 explicit prospective pilot

The new `radar_news_prospective` module shares the existing IntelligenceStore,
read-only detection projection and as-of research API. It is the single justified
runtime addition: the public package inventory becomes 55 bound files, plus its
manifest. No ledger, receipts, pilot inputs or engineering screenshots are exported.

Run only with `--opt-in-isolated-public-capture --pilot-root <durable-local-root>`.
`--initialize` requires a NEW root. The marker fixes provider, interval and request
budget across restarts. Default cadence is 1800 seconds; faster cadence is rejected.
One primary runner holds a local OS lock. A sequential transient HTTP child enforces
a 22-second total network deadline; it has no ledger access or collector authority.
Known tracking keys can be removed from URL identities; semantic parameters remain.
Title corrections preserve article identity and append material content versions.

NEWS_ARTICLE stores content versions; SOURCE_STATE stores each attempt, source
receipt and repeat sighting. Receipts retain title/link/time/author metadata, the
raw response hash and byte count, never the full RSS/article body. Checkpoint and
CURRENT_NEWS are derived caches; restart reconstructs them from the append-only
ledger. Interrupted reservations stay UNKNOWN and still consume the safe budget.
Failed sources do not refresh last_seen or erase last-good news.

First observation is the earliest successfully retrieved metadata whose evidence
was durably appended to this LOCAL pilot. It is not source publication or browser
display time. Exact second-bearing source timestamps can measure the source claim
to first-observation delay; this does NOT prove real-event detection speed.
DATE_ONLY, MINUTE, missing/future source clocks produce UNKNOWN latency.
Importance, freshness, provenance and current research readiness are distinct.
Priority is transparent research triage, never a trading signal or alert service.

The read-only `/api/app/research?event_id=...&as_of=...` uses only ledger rows at
or before as_of. Later official propositions cannot appear earlier. Any recomputed
MacroView is explicitly current interpretation rules on as-of evidence, not a
recorded forecast, authoritative freeze, or retrospective PIT reconstruction.
Historical ECB analogues remain separate EX_POST research and are excluded from
the as-of knowledge payload. Missing current market prices remain unavailable.

Production is NOT activated by this module. A local filesystem restart proof does
not prove Render redeployment durability or always-on availability. Default public
reads create no store or worker; absent storage displays FIRST_SEEN_NOT_PROVEN.
UN News, Guardian, GDELT and BBC are not enabled by the pilot.
