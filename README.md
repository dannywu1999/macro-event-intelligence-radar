# Macro Radar — M3.5 Research Workbench V2 + preserved M1/M2

New entry: `/workbench/`; CPI workbench: `/workbench/cpi-20261014/`.
Six allowlisted new presentation assets are built from the unchanged, pinned
M1/M2 inputs. They add quick statistics, proposition evidence, a visual timeline,
source/topic/evidence filters, and actual Markdown/JSON/citation clipboard exports.
`workbench/v2/manifest.json` versions this presentation separately. No newly
observed news, historical revisions, production PIT or trading feature is added.

M2 case: `/research/m2-cpi-20261014/` (Traditional Chinese HTML),
`case.txt`, `case.json`, `asof-examples.json`, and its own SHA256 manifest.
Four September 2026 CPI propositions were checked against the BLS archive
during a new one-shot research session. This is not breaking-news detection,
independent news-source corroboration, a production ledger, or a frozen view.
The conflicting feed publication and document embargo clocks remain explicit.
Only local receipt observation is proven; adjacent identity fields state that
scope. Reviewed propositions and Chinese analysis become available at the
case creation time, after the separately recorded raw document observation.

All eleven original M1 public files remain byte-identical to
`eed920ce82e645aabef2a694647b9d3639bfac83`; they describe their own seven-article
historical release. The M2 page does not silently change that saved dataset.

Static, anonymous reading of seven saved public headline records. No backend,
database, collection, official verification writer or trading system runs here.

## Rebuild and test

```text
python3 -B build_gateway.py
python3 -B -m unittest discover -s tests -v
```

Render Static Site: build `python3 -B build_gateway.py`, publish `public`,
Auto-Deploy OFF, no credentials, no disk/database or paid compute instance.
Set `SKIP_INSTALL_DEPS=true`; this build uses the Python standard library only.
Do not serve the repository root. Only **23** explicitly allowlisted public
assets are published: original M1 eleven + M2 six + workbench six. All original
17 M1/M2 files remain byte-identical, pinned by `m35_archive_preservation.json`.
No raw HTML receipts, one-shot runner, source logs or local paths
are included in the publish directory. No runtime collector or writer exists.

`contracts_v0.py` contains source-exact pure existing canonical/event and
official proposition contract functions; provenance and SHA are recorded in
`contract_provenance.json`. It neither imports nor activates the original
backend. `event_release.json` pins the reviewed case and these contracts.

Source metadata and rights were extracted from Friends Preview commit
`acd96ccd3bd04ab7af9d66c301f326a2eca291aa` without changing original files.
`release.json` pins the compact source SHA256 and the actual release-generation
timestamp. Rebuilds reuse this timestamp for byte reproducibility; it is never
used as an article observation time. Change the release configuration only for
a deliberate reviewed release. Generated assets are checked in for raw-host
fallback and independently verifiable builds.

No new articles are fetched. Chinese headlines are unofficial presentation-only
translations, retaining original headlines. All seven event candidates remain
`UNVERIFIED_NEWS` / `NO_OFFICIAL_EVIDENCE_LINKED`. No durable first-seen, frozen
MacroView, production PIT or execution-readiness claim is made.

The public reviewer guide separates data, evidence, product-concept and website
UX review. Reading static files does not prove operation of the interactive UI.
