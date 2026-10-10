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

V3/V4 was published as commit `3a43a10`. V4.1 below is an undeployed local
candidate; current Render configuration must be checked separately. No release
or source-permission approval is implied by local validation.

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


## V4.1 stale discovery repair (candidate, not deployed)

A read-only public API check on 10 October 2026 found only EIA/ECB instantiated:
EIA timed out and retained its bundled snapshot; ECB successfully returned 15
items but only one was published in the preceding 48 hours. Global Voices was
absent from acquisition status. The effective broad-news flag was off (the exact
Render dashboard value is inaccessible). API `Cache-Control: no-store` and actual
publication timestamps explain 0/24h and 1/48h without a frontend-cache hypothesis.

All known broad sources now have explicit DISABLED status when not selected.
Failures expose a sanitized reason in the existing source-check UI. Successful
broad-feed cycles expose input/selected counts, exclusion reasons and missing
publication dates. These describe the last successful cycle, not current source
health. No matched title term means excluded by a heuristic, not proven irrelevant.

The title selector now recognizes contextual military escalation, Fed/rate news,
trade, banking stress and severe disaster terms. Generic strikes, entertainment,
`fed up`, or an actor named Powell alone do not qualify. It remains a small lexical
heuristic, not a truth/importance classifier. Event occurrence time stays Unknown.

### Optional UN News complement

- Official endpoint: <https://news.un.org/feed/subscribe/en/news/all/rss.xml>, linked
  from <https://www.ungeneva.org/en/news-media/rss>.
- That RSS page permits display on a website. The general UN news-material policy
  also requires appropriate credit and advising the UN:
  <https://www.un.org/en/about-us/copyright>.
- **Before public activation**, the operator must advise the UN and retain an
  acknowledgement record outside this public repository. This task sent no notice.
- `RADAR_LIVE_UN_NEWS=1` enables the profile only with
  `RADAR_UN_NEWS_REUSE_ACKNOWLEDGED=1`. The acknowledgement asserts those existing
  obligations were completed; it does not create permission or waive restrictions.
- Default is off; a missing acknowledgement fails configuration closed.
- Title, explicit same-story original URL and supplied publication date only.
  No descriptions, article text, images, translations or other media are copied.
- The existing `RADAR_NEWS_REFRESH_SECONDS` (1800 default, minimum 300) and
  `RADAR_NEWS_MAX_ARTICLES` apply independently to each broad source.
- Attribution is visible in both languages. **UN News headline discovery is still
  UNVERIFIED_NEWS**, never automatic statement-level official confirmation.

The first due read performs at most one request per enabled source (10s/2MiB,
normal TLS, no redirects/retries). Four-source cold start can wait up to roughly
four transport timeouts plus parsing; concurrent reads return the available cache.
The second read inside TTL performs no source request. Failed sources retain their
last valid rows and last success; a successful HTTP response with no selected new
URLs is not called a failure or a new publication. Public SQLite remains off.
Restart loses ephemeral rows/deadlines. Bundled fallback publication dates and
observation times remain unchanged; restart never changes old news into recent news.

### Evaluated, not activated

BBC World/Business RSS returned current items, but the BBC metadata/RSS terms
<https://downloads.bbc.co.uk/usingthebbc/bbc_terms_of_use_31March2022english.pdf>
do not establish permission for this filtered/normalized public metadata service.
No BBC profile was installed. Guardian stays off without separate authorization.
VOA Middle East/Economy RSS returned March 2025 items, unsuitable as a fresh source;
agency-supplied VOA content also does not inherit VOA public-domain status.
Nasdaq Trader works but is primarily issuer/trading notices, not broad macro news.
GDELT remains experimental with its existing cooldown contract; it was not retried.
UN News is a global-policy complement, not a substitute for licensed mainstream
breaking coverage. That coverage remains a product gap.

### Manual Render checks after a separate release review

This task changes no Render settings and deploys nothing. Verify deployed commit,
then explicitly set `RADAR_LIVE_NEWS=1`, preserve EIA/ECB opt-ins, and use the existing
1800-second refresh settings. Add the UN flags only after the credit/notification
obligations above are completed. Keep `RADAR_LIVE_GUARDIAN=0`,
`RADAR_GUARDIAN_NONCOMMERCIAL=0`, and `RADAR_PERSIST_INTELLIGENCE=0`.
Check `/api/app/radar` for Global Voices/UN enabled status, actual attempt/success
clocks, failure reasons and recent publication counts. Local source success does
not prove Render's network access. Render sleep cannot provide continuous discovery.
