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
