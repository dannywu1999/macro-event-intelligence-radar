# A7.3 Prediction Market Watch V1

The existing Showcase Feed includes an independent bilingual market section.
No News link is required. Only conservative question/group-title macro matches
are displayed; generic elections, sports, entertainment and crypto speculation
are excluded. Categories are discovery labels, not canonical event identities.

## Local saved-data preview

Set `RADAR_DEMO_MODE=1` and the existing `GLOBAL_EVENT_RADAR_POLYMARKET_PATH` to
an explicitly selected local Gamma-format JSON snapshot with `observed_at`.
Launch the existing `radar_web_server --serve --radar-only` module. Source files
are only read. Missing data displays Unknown or an empty/unavailable Watch.
The original 20 saved political markets do not establish representative coverage.

## Optional bounded provider discovery

`RADAR_LIVE_MARKET_WATCH=1` enables demand-driven server-side discovery. Default
is disabled. `RADAR_MARKET_WATCH_TTL_SECONDS` defaults to 1800 (300–86400).
The existing `RADAR_LIVE_POLYMARKET` flag is never enabled automatically; if both
are explicitly configured, Watch supplies the expectations without starting the
legacy expectation refresh thread. No new background thread or polling loop exists.

One shared in-memory cache serves browser users. A cold/expired request performs
four public Gamma searches (Fed, tariffs, oil, Iran), at most eight event detail
GETs, at most 12 requests, at most 20 selected markets. No pagination or retry.
Event groups are considered round-robin across the four searches. Selected
markets are active-first and round-robin across macro categories, so the first
query or a large group cannot consume every display slot.
Batch starts are bounded to 30 seconds; an in-flight GET has an 8-second timeout.
All requests use verified TLS and reject redirects. The first failure ends the
batch. Failure is cached for the TTL; 429 defaults to six hours, or an actual
numeric Retry-After bounded to the TTL–24h range. Restart discards this in-memory
cache; this is not a persistent provider cooldown or comprehensive global discovery.

Source status is LIVE_FETCHED only for the first successful response, then CACHED.
Local files remain SAVED_SNAPSHOT; old observations are STALE. Failure retaining
previous provider data is explicitly STALE, never a silent live fallback. Timestamps
show system Observed At separately from Provider Updated At; neither is event time.

## Authority, outcomes and history

Only the explicit two labels Yes and No qualify as binary; label order is preserved.
Other outcomes are categorical/multi-outcome, without assuming exclusivity or
normalizing totals. Percent display is the provider outcome price times 100;
original prices remain visible. Liquidity/volume preserve supplied values without
guessing units. Resolution text and links are provider metadata, not Official facts.
When Gamma supplies aligned public outcome identifiers, the Watch retains them
alongside the corresponding outcome labels. The detail panel also gives the
actual matched question or group-title cue for its broad macro classification.
Neither identifier nor classification supplies an event identity or verification.

## Bounded real-data acceptance

An isolated local run on 2026-10-08 used four public Gamma searches with verified
TLS, no retry, and no persistent capture. The corrected adapter selected 20
active markets, five in each displayed macro category; all 20 had aligned public
outcome identifiers. The response was displayed in the existing bilingual desktop
and 375px mobile Feed through a temporary read-only server. The browser was fed a
TEMP copy of the real result and labeled it `SAVED_SNAPSHOT`, not live monitoring.
Observed At is the fetch time; Provider Updated At is the source timestamp and
does not assert a continuous quote stream. None of those markets had a credible
link to the available Radar events, so they remained `NO_MATCH`. The four-query
sample does not establish broad coverage. Multi-outcome handling remains verified
with focused fixtures rather than this all-binary live sample.

The existing MARKET_EXPECTATION_V1 and EVENT_EXPECTATION_LINK_V0 evaluator are
reused unchanged. Only valid linked expectations enter event-specific previews;
unmatched markets remain independent. New observations can be consumed by the
existing private one-shot recorder; this feature never enables it or exposes its DB.
Old freezes and knowledge-time Replay are not rewritten. No wallet, order,
authentication, trading, recovery or control-plane endpoint is called.

## Combined release preparation

No commit, push or deployment is performed by this milestone. The existing PUBLIC
manifest remains an obsolete mixed candidate. A separate release review must first
attribute A7.2, A8.1 and A7.3 changes, run the combined suite, include all new runtime
and test/doc dependencies in the public package, then rebuild and validate both
`files` and `git_clean_files` against the exact combined candidate. Do not compare
current bytes to themselves and call that release approval. Private A6+ code, DBs
and private provider configuration must remain excluded.

Official documentation consulted:
https://docs.polymarket.com/market-data/discover-markets
https://docs.polymarket.com/api-reference/search/search-markets-events-and-profiles
