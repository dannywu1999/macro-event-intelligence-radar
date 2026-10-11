# V4.4 — one real daily market-reference observation

The read-only API adds `market_reaction_research`: a separately labeled historical
research case, not added to current News/event counts, freshness or PIT history.
It uses the existing canonical ID, Official Evidence and V4.3 impact constructors.
No existing hypothesis, event fact, market snapshot or freeze is rewritten.

Event: ECB monetary policy decisions, 5 June 2025. The official decision lowers
three key rates by 25 basis points; effective date 11 June 2025. Original source:
https://www.ecb.europa.eu/press/pr/date/2025/html/ecb.mp250605~3b5f67d007.en.html
The retrieved original document identifies the date, not an exact publication
clock. DATE_ONLY, publication/effective UTC null. General scheduled release time
is not promoted to evidence of this document's exact actual publication minute.

Instrument: EUR/USD, USD per 1 EUR. ECB EXR.D.USD.EUR.SP00.A is a daily reference
rate, not a traded close, bid/ask, execution price or minute bar. Seven original
provider rows (2–10 June 2025) are bundled unchanged with source SHA256. A dated
provider label has null exact UTC observation time. Methodology gives an ordinary
concertation/publication schedule, not a guaranteed exact historical quote clock:
https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/html/index.en.html

ECB permits accurate reuse with source attribution. Derived calculations must be
identified; original information is free, linked without framing. No authored
working paper is republished. Terms and reviewed document SHA are in the receipt:
https://www.ecb.europa.eu/services/using-our-site/disclaimer/html/index.en.html
Public values are ECB statistics, never private commercial-source observations.

`MARKET_REACTION_RECEIPT_V0` exposes source/case hashes, instrument and units,
separate clocks, actual retrieval/knowledge time, provider dates, original values,
Decimal differences, supported window and missing-data/quality/causality fields.
4 June: 1.1384; 6 June: 1.1411. Difference +0.0027 USD/EUR; +0.237175% (rounded
product calculation). Event-day value 1.1423 is plotted but excluded from both
before/after classification because intraday ordering is not established.
This spans two calendar days, not a measured 24-hour return or minute reaction.
The next available provider date is not an invented full trading-calendar rule.
7–8 June missing weekend observations are shown by an unconnected chart segment.
No interpolation, overnight gap masking, corporate action adjustment or OHLC.

The original generic title can yield V4.3 impact UNKNOWN. That remains honest.
ECB policy can enter relative financing expectations, making FX a research
candidate; no directional forecast is created. The historical increase does not
score the hypothesis, establish causal impact, abnormal returns, prediction
accuracy or profitability. No specific confounder is invented without evidence.

The existing Explore Impact/Event Detail contains an interactive SVG daily chart,
clickable real dates, before/after cards, limitations and expandable provenance.
Navigation links the explicitly historical case; main News/Map/Watch unchanged.
Only the saved case is read at serving time. No provider fetch or persistence is
started. Missing/corrupt/unlicensed/synthetic inputs return NOT_MEASURED, with no
chart/prices. A8 current/PIT interfaces remain separate: this new historical
import is EX_POST_MARKET_OBSERVATION, never visible at the historical event cutoff.
Public replay remains unavailable without real recorded PIT history.
