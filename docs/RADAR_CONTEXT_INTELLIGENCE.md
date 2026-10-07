# Context intelligence and map (A7 V1)

Three separate concepts:
- Event Geography: source-supported location of the event. Unsupported = UNKNOWN.
- Context Geography: deterministic inference/navigation aid, never factual event location.
- Institution Geography: curated headquarters/jurisdiction reference, never event location.

Legacy CURATED_PRESENTATION geography remains available and explicitly labeled;
it does not become a verified event pin. New context anchors are approximate
regional centroids, and institution diamonds are headquarters. The inline SVG
basemap is a schematic drawing, not a boundary dataset.

The small reference registry supports ECB and EIA; it does not claim additional
active integrations. Definitions use current product/user-established institution
metadata with official reference links; they are presentation reference metadata.
No external AI or provider call is performed. Missing currency/location stays null.

Inference uses available headline/title text, optional body/summary and recognized
institution references, not markets or unrelated publisher headquarters. Evidence
priority is explicit headline geography, then explicit body geography, then
institution jurisdiction only when no explicit candidate exists. Aliases and
repetition count as one canonical region per distinct text. Support is compared
only within the strongest available tier; lower tiers cannot break an explicit
tie. Long overlapping phrases win; equally supported explicit text prefers a more
specific region type, and remaining ties stay MULTI_REGION with no single anchor.
Europe, European Union and Euro Area remain distinct; institution metadata cannot
discard explicit Europe or Global. Global has no point coordinates. Explicit
headline = HIGH; body/institution mention = MEDIUM; source institution alone = LOW.
Ambiguous names Georgia, Turkey, Jordan and Amazon are not mapped in V1.

Event context is additive EVENT_CONTEXT_V1. CONTEXT_GEOGRAPHY ledger rows have
system observed_at, canonical_event_id, article-reference derivation, method,
confidence and a registry fingerprint. Changes append. Replay uses persisted
context and never recomputes with current registry data. No pre-ledger context
history is manufactured. Reference metadata embedded in a recorded inference is
preserved as observed, distinct from a claim about historical institution changes.

Map filters: all, verified location, inferred context, institution headquarters.
Markers expand/focus the existing event card or provide a list of related events.
News remains UNVERIFIED_NEWS; Official Evidence remains proposition-level;
Polymarket remains EXPECTATION_SENSOR. No impact/trade prediction is generated.

Public persistence remains disabled. No commit, deploy or live collection is
necessary for this capability. Future work: broader vetted aliases/regions,
reference metadata versioning, and durable storage approval.
