# Minimal detector and local acceptance

Implementation: `research/m34_bea.py`; historical fixture validator: `research/m34_rehearsal.py`. Unchanged transport: `m31_access.py` / `m3_discovery.py`.

- `--probe`: one explicitly enabled audit GET; safe parser result is receipted. HTTP 200 alone is insufficient.
- `--pin SCHEDULE_ID TERMS_ID RSS_DOC_ID`: offline verification, immutable plan plus digest.
- `--cycle cycle_NNN --enable-network`: one sequential current-list/RSS observation, then exit; stops after failure, with shared budget.
- `--original-url URL --list-id RECEIPT_ID --request-id ID --enable-network`: one original-document GET, proof-bound to actual authorized list, then exit.
- `--project [--as-of UTC]`: read-only reconstruction; planned and observed remain distinct; body revisions are separate from list metadata. Optional `--snapshot NAME` creates an exclusive local research snapshot.
- `--handoff [--as-of UTC]`: read-only narrow personal-income statement extraction from verified original documents; unsupported GDP/other propositions remain pending manual review, never automatically promoted. No public endpoint or writer is added.

Default invocation needs only `--root`; it makes zero network requests and creates no root. Tests: canonical Python `-m unittest tests.test_m34_bea -v`. No external HTTP in these tests.

The current live original documents were acquired through the unchanged M3.1 transport into a **DOCUMENTS** namespace before the new original-document wrapper existed. `m34_rehearsal.verify` validates their exact contract, original URL/canonical identity, parent list proof, body hash and clocks. `m34_bea.project` does not claim to have fetched those documents through ITEM_*; that end-to-end wrapper is separately tested with explicitly synthetic mocked HTTP. This distinction is preserved in the preflight report.

To recheck the real saved historical fixtures offline, from this checkout, use canonical Python `-m research.m34_rehearsal --study <existing m34_evidence_20261020> --output <new empty external output directory>`. It never refetches or rewrites old receipts. Missing raw inputs are an error, not regenerated historical evidence. Rehearsal revisions/clocks are explicitly synthetic; real acquisition clocks remain their own fields.

Raw receipts and body text remain local-only. Only reviewed research code and public-safe summaries are pushed. No website runtime import, scheduled task, automatic observation, production API or trading control is added.
