# Macro Radar — M1 LLM Review Gateway

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
Do not serve the repository root. Only the 11 files in `public` are public assets.

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
