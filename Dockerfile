# Radar-only uses Python's standard library; no dependency installation needed.
FROM python:3.12.14-slim
WORKDIR /app
COPY tools/stage1b_historical_campaign/__init__.py tools/stage1b_historical_campaign/__init__.py
COPY tools/stage1b_historical_campaign/global_event_radar_read_adapter.py tools/stage1b_historical_campaign/global_event_radar_read_adapter.py
COPY tools/stage1b_historical_campaign/radar_web_server.py tools/stage1b_historical_campaign/radar_web_server.py
COPY ui/radar_public_showcase_v1.html ui/radar_public_showcase_v1.html
COPY ui/radar_demo_translations.js ui/radar_demo_translations.js
COPY tools/stage1b_historical_campaign/eia_live_ingestion.py tools/stage1b_historical_campaign/eia_live_ingestion.py
COPY tools/stage1b_historical_campaign/live_source_ingestion.py tools/stage1b_historical_campaign/live_source_ingestion.py
COPY tools/stage1b_historical_campaign/ecb_live_ingestion.py tools/stage1b_historical_campaign/ecb_live_ingestion.py
COPY demo/radar_public/news/rss_headlines_eia_snapshot.csv demo/radar_public/news/rss_headlines_eia_snapshot.csv
COPY demo/radar_public/official-packet.json demo/radar_public/official-packet.json
COPY demo/radar_public/ecb-official-packet.json demo/radar_public/ecb-official-packet.json
COPY tools/stage1b_historical_campaign/radar_market_expectations.py tools/stage1b_historical_campaign/radar_market_expectations.py
COPY tools/stage1b_historical_campaign/radar_macroview_freeze.py tools/stage1b_historical_campaign/radar_macroview_freeze.py
COPY tools/stage1b_historical_campaign/radar_intelligence_store.py tools/stage1b_historical_campaign/radar_intelligence_store.py
COPY tools/stage1b_historical_campaign/radar_reality_replay.py tools/stage1b_historical_campaign/radar_reality_replay.py
COPY demo/radar_public/metadata.json demo/radar_public/metadata.json
# The platform supplies PORT. Without one, the application's local fallback remains.
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOST=0.0.0.0 RADAR_DATA_ROOT=/data
USER 65532:65532
EXPOSE 8765
ENTRYPOINT ["python", "-m", "tools.stage1b_historical_campaign.radar_web_server", "--serve", "--radar-only"]


COPY tools/stage1b_historical_campaign/radar_context_intelligence.py tools/stage1b_historical_campaign/radar_context_intelligence.py
