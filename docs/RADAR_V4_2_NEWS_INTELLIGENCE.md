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
