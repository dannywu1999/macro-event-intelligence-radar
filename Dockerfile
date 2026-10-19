FROM python:3.12.14-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOST=0.0.0.0
COPY data/SOURCE_RIGHTS.json data/SOURCE_RIGHTS.json
COPY data/baseline_168.json data/baseline_168.json
COPY data/baseline_48.json data/baseline_48.json
COPY data/ecb/ecb_2025_03_06.json data/ecb/ecb_2025_03_06.json
COPY data/ecb/ecb_2025_04_17.json data/ecb/ecb_2025_04_17.json
COPY data/ecb/ecb_2025_06_05.json data/ecb/ecb_2025_06_05.json
COPY data/ecb/ecb_eurusd_2025_03.csv data/ecb/ecb_eurusd_2025_03.csv
COPY data/ecb/ecb_eurusd_2025_04.csv data/ecb/ecb_eurusd_2025_04.csv
COPY data/ecb/ecb_eurusd_2025_06.csv data/ecb/ecb_eurusd_2025_06.csv
COPY data/public_168.json data/public_168.json
COPY data/public_48.json data/public_48.json
COPY friends_preview_server.py friends_preview_server.py
COPY ui/radar_headline_presentation.js ui/radar_headline_presentation.js
COPY ui/radar_product_workbench.css ui/radar_product_workbench.css
COPY ui/radar_product_workbench.js ui/radar_product_workbench.js
COPY ui/radar_public_showcase_v1.html ui/radar_public_showcase_v1.html
COPY Dockerfile Dockerfile
COPY .dockerignore .dockerignore
COPY FRIENDS_PACKAGE_MANIFEST.json FRIENDS_PACKAGE_MANIFEST.json
USER 65532:65532
EXPOSE 8765
ENTRYPOINT ["python", "-B", "friends_preview_server.py"]
