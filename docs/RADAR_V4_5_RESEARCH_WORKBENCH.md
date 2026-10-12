# Macro Radar V4.5 — historical ECB research workbench

This read-only library contains three source-backed ECB policy cases: 6 March,
17 April and 5 June 2025. It is a historical research area, separate from live
News, canonical-event totals, source freshness and public PIT Replay.

## Comparable daily reference method

Each case uses ECB series `EXR.D.USD.EUR.SP00.A` (daily USD per EUR reference
rate). For a date-only announcement, the baseline is the nearest valid provider
date strictly before the event, and the post observation is the nearest
available provider date strictly after it. The event-day value is excluded from
both sides. We show the actual dates, values, calendar-day span, missing dates,
source links and the reproducible Decimal calculation. Different spans remain
visible; there is no aggregate score.

| ECB decision | Effective date | Before → after | Change | Span |
| --- | --- | --- | --- | --- |
| 6 March 2025: three key rates cut 25 bp | 12 March | 5 Mar 1.0694 → 7 Mar 1.0857 | +0.0163 USD/EUR; +1.524219% | 2 calendar days |
| 17 April 2025: three key rates cut 25 bp | 23 April | 16 Apr 1.1355 → 22 Apr 1.1476 | +0.0121 USD/EUR; +1.065610% | 6 calendar days |
| 5 June 2025: three key rates cut 25 bp | 11 June | 4 Jun 1.1384 → 6 Jun 1.1411 | +0.0027 USD/EUR; +0.237175% | 2 calendar days |

The April post date follows the Easter holiday/weekend gap. The 17 April
event-day reference is present in the source data, but is not classified as a
before/after value. Rates are ECB daily references, not traded closes,
executable quotes or intraday bars. Exact announcement and observation UTC
times are unknown.

## Interpretation limits

The display describes what the daily reference series showed between the stated
provider dates. It does not attribute the change to an ECB decision, establish
an abnormal return or validate a directional hypothesis. A conditional channel
may run through relative rate expectations, yields and funding conditions, but
the net EUR/USD direction is not implied. The package does not identify
specific concurrent causes. News/event status remains `UNVERIFIED_NEWS`; each
`OFFICIAL_CONFIRMED` record is limited to its stated ECB proposition.

All three cases were acquired and imported in 2026. None is a frozen 2025
MacroView or point-in-time Replay record. Stronger research would need exact
announcement timestamps, intraday observations, time-valid expectations and
controls, and more comparable event samples. The library makes no win-rate,
strategy, alpha, Sharpe, trading or prediction-accuracy claim.

Original ECB release links and the original data/API links are retained in each
case receipt. Reuse follows the existing V4.4 ECB attribution and derived-data
terms review; the source observations are bundled as unmodified provider CSV.
