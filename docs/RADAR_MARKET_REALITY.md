# Market Reality foundation (A8.0)

This is descriptive market observation, not prediction, causality or trading.
It adds `MARKET_REALITY_SNAPSHOT_V0` to Radar events without changing News or
Official authority. Public persistence remains disabled.

## Local data audit

Existing SPY research supports historical daily bars, without the required
system knowledge timestamps. The legacy OHLC completion layer accepts generic
local series. Its NQ series is not QQQ. Existing FRED research uses VIXCLS, DGS10,
DTWEXBGS, SP500 and NASDAQ100: daily source data and retrieval times are not a
point-in-time vintage contract. DTWEXBGS is not DXY, SP500 is not SPY and NASDAQ100
is not QQQ. No qualified point-in-time input for these five requested instruments
was established. No legacy process or dataset is automatically used by A8.

## Explicit input

`GLOBAL_EVENT_RADAR_MARKET_REALITY_PATH` optionally selects a JSON file, resolved
relative to `RADAR_DATA_ROOT` when configured. Unset/empty means not configured.
Packet: `{"schema":"MARKET_REALITY_INPUT_V0","observations":[...]}`.
See `tests/fixtures/market_reality_v0.json` for a **synthetic offline fixture**.
The normal reader refuses packets declaring `synthetic=true` or an ambiguous
synthetic marker. Browser fixture verification uses an explicit TEMP-only mocked
market-source boundary, never a production serving flag or configuration bypass.

Each record requires the exact canonical event ID, symbol, `event_observed_at`
(system event observation), `market_timestamp`, `observed_at` (system knowledge),
`time_basis=SYSTEM_RECORDED_TIME`, numeric `price_or_level`, exact `value_unit`,
source name and source observation ID. Source URL and independently known
previous close may be null. Provenance and time ordering are validated.
Input is bounded to 8 MiB / 4096 observations; identical observations collapse,
conflicting source IDs or event anchors make the input unavailable.

SPY/QQQ use PRICE; VIX/DXY use INDEX_LEVEL; US10Y uses YIELD_PERCENT. Yield changes
are basis points; other changes are percent. Missing sources, previous closes,
event-system anchors and stale observations remain null. Freshness is 900 seconds
of market age at the requested window. All five symbols remain in the contract;
the card appears only for PARTIAL/COMPLETE data and shows missing symbols openly.
Without source observations, market cutoff fields remain null rather than
manufacturing request-clock changes in previews/freezes. The enclosing Replay
still reports its requested cutoff. Meaningful supplied data is included in new
MacroView previews; previously persisted freezes are never rewritten.

## Time and replay

Publication, event occurrence, collector observation, event-system observation,
market time and market-system knowledge are distinct. CSV observed time is not
silently promoted to an event-system anchor. Windows: T0, T+5m, T+30m, T+1h,
T+1_TRADING_DAY. Future windows remain unavailable until their cutoff. Trading-day
resolution requires an externally established calendar target; no next-calendar-
day guess is made. V0 has a pure window projector, not a new API window selector.

Replay reads append-only MARKET_REALITY ledger rows visible by its cutoff, never
the current market input. Imported older data is known no earlier than its ledger
recording time. Replay anchors on the first recorded canonical state. Frozen
MacroViews copy supplied market observations; old frozen evidence is unchanged.
Tests cover 10:02/10:10/10:20/10:30 future leakage, late imports and immutable
freezes. No current source fetch, broker, paid data or persistence enablement is
part of this milestone. Without suitable input, real market status remains
`NO_SUITABLE_POINT_IN_TIME_SOURCE`.
