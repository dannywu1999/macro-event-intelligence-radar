# A7.2 Event ↔ Market Expectations

The existing Radar adapter now evaluates saved or opt-in sensor snapshots with
`radar_event_expectation_linker.py`. Reading the feed never fetches a provider,
starts a runtime, or writes a link file. Polymarket remains `EXPECTATION_SENSOR`.
It cannot confirm News, change Official evidence, supply event geography, or
produce a trading decision.

## Deterministic V0 scope

`EVENT_EXPECTATION_LINK_V0` records `link_id`, canonical event ID, market and
snapshot IDs, status, method, categorical confidence, normalized event/market
terms, matched terms and reason. Status is `LINKED`, `NO_MATCH`, `AMBIGUOUS`, or
`INSUFFICIENT_EVIDENCE`. Only `HIGH` supported matches auto-link; no probability
is assigned to link confidence.

The first supported proposition is an explicit ECB/Fed/BOE/BOJ policy-rate
meeting, using known institution aliases. A shared keyword/title similarity is
insufficient. Both titles must explicitly name the same institution and the
same explicit calendar day including year. A generic rate-decision event can link to several
independently compatible outcome markets for that meeting. Specific prospective
actions must agree with the market action and numeric threshold. Observed times
and market closing time must be valid; completed events and expired windows are
rejected. Multiple indistinguishable canonical targets remain ambiguous.

Missing years/days, unequal date precision, negation, deadline/conditional phrasing,
mixed institutions/actions/scopes and unsupported proposition families remain
unlinked. No year is inferred from publication/observation/close time. Description,
resolution fields and selected public provider group metadata are preserved when
available but are not used to guess a missing proposition. This deliberate small
coverage favors precision over recall. Percent level versus percent change is not
guessed; numeric auto-links support explicit basis-point quantities. Truncated
provider proposition metadata refuses automatic linking. Explicit rate
jurisdictions must agree with the named institution; they never create geography.

An existing `EXACT_MARKET_LINKS_V1` file remains an explicit curator assertion,
separate from automatic proposition evidence. `event_to_market` accepts the old
single market ID or a list of IDs per event; the same market cannot be assigned
to multiple events. It overrides auto-linking. Unreadable/invalid configured
mappings fail closed without falling back to automatic links.

## MacroView and knowledge time

Linked snapshots include their link record; current MacroView and newly created
freezes preserve it. Unlinked markets do not enter an event's MacroView. Existing
freezes are never rewritten. Link `observed_at` is null for an unpersisted pure
projection; `market_observed_at` preserves the source snapshot clock. A6 captures
link knowledge in the existing `MARKET_EXPECTATION` ledger payload at actual
ingestion time, including later link/unlink changes. It does not backdate a link
to the market's source timestamp. Replay uses only snapshots and associations
recorded by its cutoff, not today's linker or files.

## Presentation

Event cards hide the expectation panel when no credible link exists. Linked
records display a separate **Market Expectations / 市場預期** section, question,
provider outcome percentages plus original values, observed time and source link.
The disclosure says market expectations do not verify facts. Missing data remains
Unknown; it never becomes a buy/sell instruction. Unlinked snapshots may still
appear in the existing separate provider catalogue, without claiming an event
relationship.

## Verification boundary

Focused offline tests exercise the actual matcher, adapter, MacroView, A6 ledger,
Replay and English/Chinese UI scripts. Synthetic rate meetings prove successful
linking, multi-market outcomes and refusals; they are not a real market demo.
Real saved News/market snapshots are reviewed separately without new requests.
The saved broad Gamma page may contain political markets unrelated to the
EIA/ECB News feed: zero real links is a valid outcome. No deployment, provider
request, lifecycle recovery or trading authorization is part of A7.2.

## Saved real-data result (2026-10-08 offline validation)

The latest accessible saved audit view contains **28** canonical events, not the
29 stated in the task packet. Both the earlier cloud capture and the corrected
audit capture contain 28; no additional event was manufactured or fetched.
The real Gamma capture contains 20 markets: Xi Jinping's tenure and 2028 US
presidential-nomination questions. All 20 include descriptions, provider event
groups, outcome labels/prices and observation clocks. Separate resolutionCriteria
and nonempty resolutionSource fields are absent; descriptions contain rules.

The actual production parser/linker evaluated **560 pairs**: 0 LINKED,
0 AMBIGUOUS, 560 NO_MATCH. Every event is unlinked. Examples:

| Saved News topic | Saved market | Decision |
| --- | --- | --- |
| EIA crude oil prices/refinery margins | Xi Jinping out before 2027? | Different proposition; NO_MATCH |
| ECB monetary-policy diagnostic speech | 2028 Democratic presidential nomination | Different proposition; NO_MATCH |
| EIA natural gas production | 2028 Democratic presidential nomination | Different proposition; NO_MATCH |

There are no real linked pairs to approve. Synthetic policy-meeting fixtures prove
the positive path, not real event-market coverage. Saved News and market source
bytes remain unchanged. Public opt-in acquisition/coverage is a separate review.

## Final offline regression

The focused linker suite passes 44 tests. Relevant MAIN regression passes
355/355 and the shipped PUBLIC regression passes 339/339; both have zero
failures, errors or skips. These are separate suite executions with overlapping
tests, not a count of unique tests. External sockets/DNS were blocked; HTTP
checks used only temporary loopback servers, which were shut down by the tests.
English/Chinese rendering was tested through the existing JavaScript DOM
harness, not a new real-browser acceptance. Source hashes and all 66 existing
PUBLIC manifest entries were verified; prior unrelated working-tree changes
were preserved. Nothing was committed, pushed or deployed.
