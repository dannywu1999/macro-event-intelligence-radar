# Standalone demo deployment

This repository contains only the read-only Radar product and bundled EIA
snapshot. There is no live ingestion, persistent disk or account secret required
by the application. Actual Linux/cloud execution must be verified at deployment;
offline package verification is not a claim of a deployed public service.

## Render Dashboard

After publishing this clean standalone repository to the user's GitHub account:

| Setting | Value |
| --- | --- |
| Service | New **Web Service**, select the published GitHub repository |
| Language | **Docker** |
| Root Directory | Blank (repository root) |
| Dockerfile Path | **`./Dockerfile`** |
| Docker Command | Blank; image entrypoint starts the Radar-only server |
| Health Check Path | **`/healthz`** |
| Persistent Disk | None |

Set these environment variables:

```text
HOST=0.0.0.0
PORT=<platform-provided; do not enter a literal placeholder or pin a port>
RADAR_DATA_ROOT=/app/demo/radar_public
GLOBAL_EVENT_RADAR_NEWS_PATH=/app/demo/radar_public/news
GLOBAL_EVENT_RADAR_OFFICIAL_PATH=/app/demo/radar_public/official-packet.json
RADAR_DEMO_MODE=1
```

Do not configure the optional Polymarket, source-health or MacroView paths.
With an explicit data root the development MacroView fallback is isolated.
There is no browser auto-open. Render provides the external HTTPS endpoint.

References: [Docker on Render](https://render.com/docs/docker),
[Web Services](https://render.com/docs/web-services),
[HTTP health checks](https://render.com/docs/health-checks).

## Local headless run from this exported tree

Using Python 3.12.14, no package installation is needed:

```sh
RADAR_DATA_ROOT=demo/radar_public \
GLOBAL_EVENT_RADAR_NEWS_PATH=news \
GLOBAL_EVENT_RADAR_OFFICIAL_PATH=official-packet.json RADAR_DEMO_MODE=1 \
python -B -m tools.stage1b_historical_campaign.radar_web_server --serve --radar-only
```

Local defaults stay `127.0.0.1:8765`. The web application does not write evidence.
For a local Docker test use a temporary port bound only to loopback:

```sh
docker build -t macro-radar-public .
docker run --rm -p 127.0.0.1::8080 -e PORT=8080 -e RADAR_DEMO_MODE=1 \
  -e RADAR_DATA_ROOT=/app/demo/radar_public \
  -e GLOBAL_EVENT_RADAR_NEWS_PATH=/app/demo/radar_public/news \
  -e GLOBAL_EVENT_RADAR_OFFICIAL_PATH=/app/demo/radar_public/official-packet.json \
  macro-radar-public
```

## Acceptance after deployment

Expect 5 Articles / 5 Events / 1 Official Evidence and a visible snapshot notice.
The oil-price event remains `UNVERIFIED_NEWS`; only its linked fact proposition
is `OFFICIAL_CONFIRMED`, with Published shown as Unknown. Other four events have
zero linked evidence. `/healthz` returns only status/service, not source health.
POST/PUT/PATCH/DELETE to the Radar API return 405; other application APIs return 404.

## Git publication, later by the user

Work only from this standalone export, whose own Git root must equal this
directory. Do not publish from the original project or an ancestor repository.
Git author identity must be configured by the user before committing; no author
identity, remote, account or push is configured by the exporter.

After creating an empty GitHub repository, review the files and run:

```sh
git init -b main
git add .
git status
git commit -m "Publish read-only EIA Radar demo"
git branch -M main
git remote add origin <GITHUB_REPO_URL>
git push -u origin main
```

Do not proceed if any command fails. Do not force-add ignored runtime/generated
files. A passing offline export check does not automatically authorize deployment.
