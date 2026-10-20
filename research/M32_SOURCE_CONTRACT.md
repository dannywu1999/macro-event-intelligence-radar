# M3.2 research source contract

Status: **PARTIAL**. Personal research capability is demonstrated; public news coverage is not recovered.

## Source selection and rights

The prior 23-source experiment and policy registry were inspected first. Historical HTTP 200 statuses were not treated as current access or current permission. No original M3/M3.1 receipt or plan was changed.

| Source | Current result | Permitted scope used | Selection |
|---|---|---|---|
| Global Voices | direct GET 200, 15 metadata records, no selected macro candidate | CC BY 3.0; retain author, title, original URL, licence; no third-party images | qualification only |
| 360info | direct GET 200, 10 metadata records, no selected macro candidate | CC BY 4.0 with attribution; no third-party material | older context, not breaking coverage |
| CNA Business | direct GET 200, 20 records, two recent central-bank expectations candidates after one false positive excluded | **personal, non-commercial only; no redistribution** | isolated local research only |
| BBC / CNBC / DW / NPR / BoE | not requested this experiment | public reuse unresolved or constrained; web robots refusal respected | not integrated |
| VOA | official RSS directory and copyright statement inspected, feed not directly tested | exclusive VOA works differ from licensed wire content; article-level origin not established | not integrated |
| Democracy Now / Common Dreams | documentation inspected only | conditional non-commercial or selective-use terms, not cleared for this product | not integrated |
| Existing ECB / Fed / EIA / BEA / BLS | historical registry retained | institutional discovery is separate from proposition authority | no production change; no repeat BLS feed denial probe |

Sources: [GV](https://globalvoices.org/about/), [360info](https://360info.org/how-to-use-our-content/), [CNA feed directory](https://www.channelnewsasia.com/rss), [CNA binding RSS terms](https://www.channelnewsasia.com/rss/rssterms), [VOA copyright](https://www.voanews.com/p/5338.html).

CNA is not public-domain data. Its feed may contain wire reporting. Local receipts, article titles, links and derived packets are **not part of the Git publication**. No full article, image, translation or public feed redistribution is implemented. The feed is not edited; classification is a separate local research projection. Any future public/commercial use requires separate clearance. There is no claim that a source's accessibility authorizes deployment or periodic production capture.

## Versioned namespaces and budgets

V1 qualified GV and 360info with two GETs. Its contract, source registry, raw bodies and receipts are preserved. Finding no relevant recent article was a negative result. CNA was discovered from its publisher's directory **after** that result, so it was added only to a new V2 contract/namespace. V1 was not silently expanded. The predeclared evaluation file remains unchanged.

V2 selects only CNA Business in its frozen plan. Official calendar fetches have a separate fixed contract and namespace. A shared study wrapper counts `RUN` (V1), `RUN_V2`, and `OFFICIAL` under one OS lock before every new request: <=120 direct GET reservations, <=20,000,000 charged bytes; unknown transport results reserve the full 2 MiB. Existing transport is sequential, no redirect, no retry, bounded body and timeout. Web documentation search is separate: provider internal request/byte counts are unavailable and never represented as measured direct-source bytes.

`m31_access.py` gained explicit immutable dependency injection. Its default registry, plan, identity marker, caps, source family quota and ACK scope remain M3.1 compatible. M3.2 never mutates module globals or monkeypatches the old registry. No M3/M3.1 original repository or historical receipt was edited.

## Identity, clocks and replay

Article identity reuses normalized original URL. Translations and relevance labels do not participate. Similar titles at different URLs remain separate article-set candidates; they are not proven distinct world events. Unchanged content is DUPLICATE; changed title/time is UPDATED; first observation remains fixed.

Source-reported publication time, HTTP retrieval, parsed recording, successful checkpoint availability and projection as-of are separate. DATE_ONLY remains DATE_ONLY. Unknown publication clocks stay null. Projections validate reserve/ACK/body/parsed/terminal bindings and are read-only. Receipt corruption fails closed. Future-source-time candidates and later-recorded versions are excluded from the selected as-of view.

No global first-seen, immutable production PIT, Frozen MacroView, breaking-news latency or 24/7 service claim is made. MacroView output is a local research preview with unknowns and no trading permission.

## News → official

Real news reports concern anticipated central-bank decisions. The BOJ/BOK calendars confirm **scheduled meeting dates only**. They cannot confirm anonymous inflation forecasts, polling predictions, or future rate actions. Each main news claim remains `OFFICIAL_VERIFICATION_PENDING`. Calendar retrieval after an as-of time is unavailable to that historical projection.

Historical M3 exact-URL benchmark is unchanged: original 1/3; M3.2 alone 0/3; union still 1/3. New private recent candidates demonstrate a bounded capability gain, not recovered public recall.
