# M3.5 — versioned research presentation

Parent: `1ea07d764f7fb53ba5c4b28ac11547d2174b558d`. Research branch:
`m3-5-research-workbench-20261020`. Publishing branch, only after release gates:
`llm-review-gateway-20261020`. No main/Friends Preview changes.

## Product decisions

- `/workbench/`: compact CPI summary followed by seven saved public articles.
- `/workbench/cpi-20261014/`: four source-derived statistics, original discovery
  versus four proposition-scoped BLS excerpts, expandable seven-node timeline,
  unknowns, conditional MacroView Preview, citations and source files.
- Native controls, system fonts, restrained navy/teal/amber, keyboard focus,
  labelled disclosures and responsive stacking; no framework or animation.
- HTML entry shells have no-script links to preserved readable M1/M2 resources.
  Interactive workbench requires JavaScript and loads one same-origin saved JSON.
- Copy Markdown, JSON and citation use the actual pinned case. JSON export is
  explicitly `MACRO_RADAR_RESEARCH_EXPORT_V2`, not JSON-LD. Clipboard failure has
  a manual-copy dialog; no analytics, external translation or model service.
- Filters separate article identity from proposition research. The CPI article
  links to four supported propositions and retains UNVERIFIED_NEWS. Source labels
  group publisher display while preserving original source/author fields.
- Unsupported interpretations are explicitly research-boundary examples from
  the original case, not invented media reports which have been “debunked”.

## Evidence and advanced gates

All four values derive from the original proposition excerpts, never a second
editable metric database. Original English headlines, sources, times, rights,
IDs, status and unknowns remain unchanged. Source feed time versus scheduled
embargo conflict is visible; no negative latency or measured online-publication
time is inferred. Research creation is later than document acquisition, visible
and present in exports. Build time never becomes an evidence observation.

Revision diff: deferred, no real saved revision pair. Interactive as-of: deferred;
the original four saved-receipt projections stay available as a clearly labelled
source file, not full historical PIT. Causality: not established. LLM consensus:
not implemented; independent code review is not a model-vote score.

## Build/public boundary

`python3 -B build_gateway.py` retains M1/M2 output bytes, then calls
`build_workbench.py`. The root publish directory contains exactly 23 files.
The new `workbench/` subtree has six exact allowlisted files; unknown files,
directories and symlinks fail validation. Source inputs, archive hashes and
per-output SHA256 are retained in the presentation manifest. Tests cover
determinism with network/DNS blocked and raw archive equality.

No backend, credentials, collectors, writer, Cloudflare, ownership, frozen
contract or trading changes. Synthetic HTTP/XSS faults are served only by an
external local QA helper; they never enter the repository or public build.

## Local acceptance

Use native canonical Python at
`%USERPROFILE%\AppData\Local\Programs\Python\Python313\python.exe`.
From this checkout: `-B build_gateway.py`, then
`-B -m unittest discover -s tests -v`. Serve **public only** on an unused localhost
port. Open `/workbench/`, search Chinese/English, filter evidence, open a metric,
expand its original excerpt, switch timeline UTC/Taiwan and copy all three formats.
Do not start any production collector to view this saved data.
