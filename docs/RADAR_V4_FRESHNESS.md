# V4: publication freshness and Chinese market questions

## Bounded acquisition

Existing EIA/ECB opt-ins now use one request-triggered coordinator. On a Radar
read, only due sources refresh; concurrent reads use the published cache. Each
source makes one verified HTTPS request (10-second transport timeout, 2 MiB
maximum, redirects rejected). No retry. Failures retain the last valid source
rows, with a typed acquisition error. Default TTL is 1800 seconds (existing EIA
TTL configuration remains supported). Health is never inferred from article age.

- `RADAR_LIVE_EIA=1`: existing EIA discovery.
- `RADAR_LIVE_ECB=1`: existing ECB discovery.
- `RADAR_LIVE_NEWS=1`: Global Voices, default max 100 articles.
- `RADAR_LIVE_GUARDIAN=1` additionally requires
  `RADAR_GUARDIAN_NONCOMMERCIAL=1`: Guardian World RSS. Do not use this flag for
  commercial redistribution without separate permission. The flag records an
  operator assertion; it does not grant rights.
- `RADAR_NEWS_REFRESH_SECONDS`: 300–86400, default 1800.
- `RADAR_NEWS_MAX_ARTICLES`: 1–1000, default 100 per broad source.
- `RADAR_RUNTIME_ROOT`: existing isolated ephemeral runtime root.

Sources are independent opt-ins. No deployment environment has been changed.
Global Voices and Guardian broad discovery store titles and links only, not full
articles, descriptions or images. Global Voices rows require the credited author
in source attribution and display the [CC BY 3.0 licence](https://creativecommons.org/licenses/by/3.0/).
See [Global Voices attribution policy](https://globalvoices.org/about/global-voices-attribution-policy/)
and [Guardian RSS access conditions](https://www.theguardian.com/help/feeds).
Coverage is selective, not exhaustive, and all news remains UNVERIFIED_NEWS.
GDELT remains secondary/experimental; Nasdaq remains specialized discovery.

## Clock semantics and UI

`news_freshness` is a read-only projection. Latest /24h /48h /Older uses only
known reported publication timestamps. Date proxies, missing/naive dates and
future timestamps do not count as recent publication. System observation and
successful fetch are displayed separately. Saved old rows do not become recent
on restart. Counts of recent canonical events use the existing Event V0 article
membership, not inferred real-world clustering. A new article can contribute to
an existing event without claiming that the event itself just began.

The latest list is chronological. The existing canonical overview still prioritizes
linked Official evidence (explicit existing sort note). Map remains before Watch.
Official confirmation remains proposition-specific. MacroView remains PREVIEW;
Replay remains unavailable without legitimate recorded history.

## Translation boundaries

1. Reviewed question summaries require exact market ID and original text.
2. Anchored deterministic templates validate complete known question patterns:
   ceasefires, Fed rate decisions, US–Canada tariff agreements, Section 232 copper
   cable tariffs and WTI HIGH thresholds. Invalid dates/extra conditions fall back.
3. Other questions show Chinese topic/terminology explanation and prominent
   English original. This is never a complete translation of settlement terms.

Dates without a year retain that omission. Through includes the stated date;
after, no-change, 50+ bps and HIGH are retained. Outcome identities and source
resolution terms are not translated by these templates. No external LLM service.

## Deployment limitations

Public persistence remains disabled. Render sleep/restart loses process-owned
live cache and cooldown deadlines. The first request can spend up to one timeout
per due source; concurrent reads receive the cached snapshot. The immutable EIA
bundle is a clearly older fallback, not newly acquired evidence. Same-URL article
revisions retain the first observed row; revision history is not implemented.
First system observation is process-local unless an existing recorder is explicitly
configured separately. No always-on acquisition or durable availability promise.

V4 is an uncommitted local candidate. The live site has not been updated. A later
release review must inspect source opt-ins, permitted Guardian usage, live fetch
receipts and cold-start latency before deploying.

## Combined V3+V4 public-release correction

Guardian World must remain `RADAR_LIVE_GUARDIAN=0` and
`RADAR_GUARDIAN_NONCOMMERCIAL=0` on the public service. A free website does not
establish personal-use or redistribution permission. No permission was established
by this review. Prior counts including Guardian are not public-release metrics.

Broad-source parsing now admits only explicit macro-relevant title terms/phrases
with word boundaries (trade/tariffs, policy/rates/inflation/jobs, energy/supply,
major geopolitical/security developments and large natural-disaster discovery).
This conservative lexical selection is not a classifier of truth, importance or
exhaustive coverage. Ordinary food-health, culture and local-crime stories do not
inflate macro-discovery counts. Titles with indirect macro implications can be
missed. A valid feed with zero selected titles is a successful zero-new cycle;
malformed/unusable feed failures still preserve the last valid cache.

Every Global Voices article card displays author/source and original link, a CC BY
link and a metadata-only/whitespace-normalization notice in both languages.
No article body, article translation, image, audio or video is copied. The policy
link does not claim all third-party material inherits a Global Voices licence.

Existing public launch flags (set manually only after publication):
`RADAR_LIVE_EIA=1`, `RADAR_LIVE_ECB=1`, `RADAR_LIVE_NEWS=1`.
Recommended existing TTL settings: `RADAR_EIA_REFRESH_SECONDS=1800`,
`RADAR_ECB_REFRESH_SECONDS=1800`, `RADAR_NEWS_REFRESH_SECONDS=1800`.
Keep `RADAR_PERSIST_INTELLIGENCE=0`; no private database path is configured.
