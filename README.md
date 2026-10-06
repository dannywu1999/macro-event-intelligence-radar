# Macro Event Intelligence Radar

A read-only event intelligence demo that keeps **news discovery** separate from
**proposition-level official evidence**.

**News Discovery → Canonical Event → Official Evidence**

The bundled public snapshot contains **5 EIA news articles, 5 conservative
Canonical Events and 1 linked Official Evidence record**. It demonstrates source
provenance, chronological article presentation, deterministic event/evidence
identities and transparent missing-data handling.

## What the demo shows

- News remains `UNVERIFIED_NEWS`, including reports from an official agency's feed.
- Official evidence confirms **a specific proposition**, not the entire event.
- The selected oil-price event has one linked `OFFICIAL_CONFIRMED` proposition;
  the other four events have none. Publication time remains null/Unknown.
- The Showcase UI presents article/event/evidence counts, original source links,
  observed/source timestamps and UNKNOWN source health when no health evidence exists.
- `PUBLIC DEMO · READ-ONLY SNAPSHOT` identifies the immutable dataset.

This public snapshot has **no automated live ingestion**. It is not exhaustive
global coverage and does not promise production uptime. This repository/demo
**does not perform live trading**, price prediction or order execution.

## Implementation

Python 3.12.14 standard-library HTTP backend, one read-only Radar adapter,
HTML/CSS/JavaScript Showcase UI, Docker-ready deployment and SHA256 release
provenance. No database, frontend build or third-party Python package is required.
The existing Python package paths are preserved for import compatibility.

The container is non-root, and the application only serves its UI, Radar API
and minimal `GET /healthz`. Mutation methods are rejected; no collectors or
administrative runtime are included.

## Run and deploy

Use the root `Dockerfile` with a Render **Docker Web Service**. Environment
configuration selects the bundled snapshot, headless startup and platform port.
See [Deployment](docs/DEPLOYMENT.md) for exact settings and local commands.

Public route after deployment: `https://<service-name>.onrender.com/#/feed`.
No public URL is claimed before the service is actually deployed.

`PUBLIC_RELEASE_MANIFEST.json` records each other package file's relative path
and SHA256. `demo/radar_public/metadata.json` records immutable data hashes and IDs.

## Attribution

Source: **[U.S. Energy Information Administration](https://www.eia.gov/todayinenergy/)**.
Original EIA article/evidence links are preserved. No EIA logo is reproduced.
This independent demonstration is **not endorsed by EIA**.
