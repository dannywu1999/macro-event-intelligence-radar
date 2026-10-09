"""Headless read-only serving branch of the unified app; standard library only.

No research/control-plane imports or materialization. Optional process-owned
acquisition and intelligence recording never introduce a public write API.
The sole Radar adapter and the existing unified HTML remain the product sources.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import unquote, urlsplit, parse_qs
import re

from tools.stage1b_historical_campaign import global_event_radar_read_adapter as event_radar

ROOT = Path(__file__).resolve().parents[2]
UI = ROOT / "ui" / "macro_trading_os_unified_app_v1.html"
HOST, PORT = "127.0.0.1", 8765
GovernanceError = event_radar.EvidenceReadError


def require(value: bool, code: str) -> None:
    if not value:
        raise GovernanceError(code)


def feed_view(ingestion=None, expectation_sensor=None, market_watch=None) -> dict[str, Any]:
    if ingestion is not None:
        view = ingestion.read_view(event_radar, event_radar.EvidencePaths.from_environment())
    else:
        view = event_radar.build_radar_view()
        view['live_ingestion'] = {'enabled': False, 'source': 'EIA Today in Energy', 'status': 'DISABLED',
                                 'last_attempt_at': None, 'last_success_at': None,
                                 'refresh_interval_seconds': None, 'article_count': view.get('item_count'),
                                 'new_article_count': 0, 'reason': None}
        from tools.stage1b_historical_campaign.live_source_ingestion import disabled_status, EIA_SOURCE, ECB_SOURCE
        view['discovery_sources'] = {EIA_SOURCE: dict(view['live_ingestion']),
                                     ECB_SOURCE: disabled_status(ECB_SOURCE)}
    require(isinstance(view, dict) and isinstance(view.get("events"), list)
            and view.get("canonical_event_contract") == "CANONICAL_EVENT_V0",
            "RADAR_CANONICAL_PROJECTION_UNAVAILABLE:RESTART_RADAR_ONLY_SERVER")
    from tools.stage1b_historical_campaign.radar_market_reality import public_market_view
    view = public_market_view(view)
    if expectation_sensor is not None:
        records, state = expectation_sensor.snapshot()
        view.update(event_radar.project_market_records(view["events"], records,
                    event_radar.EvidencePaths.from_environment().expectation_links))
        view["expectation_provider"] = state
    else:
        view["expectation_provider"] = {"enabled": False, "status": "DISABLED",
                                      "last_attempt_at": None, "last_success_at": None, "reason": None}
    from tools.stage1b_historical_campaign.radar_prediction_market_watch import build_watch
    watch_state = None
    if market_watch is not None:
        records, watch_state = market_watch.snapshot()
        view.update(event_radar.project_market_records(view['events'], records,
                    event_radar.EvidencePaths.from_environment().expectation_links))
        view['expectation_provider'] = watch_state
    elif expectation_sensor is not None:
        watch_state = {**view['expectation_provider'], 'status': 'STALE' if view['expectation_provider']['status'] == 'LAST_VALID_FALLBACK' else 'CACHED'}
    elif view.get('sources', {}).get('polymarket', {}).get('status') in {'NOT_CONFIGURED', 'UNAVAILABLE'}:
        watch_state = {'enabled': False, 'status': 'UNAVAILABLE', 'reason': view['sources']['polymarket']['status']}
    view['prediction_market_watch'] = build_watch(view.get('market_expectations', []), provider=watch_state)
    from tools.stage1b_historical_campaign.radar_macroview_freeze import build_previews
    view["macroview_preview_contract"] = "MACROVIEW_PREVIEW_V0"
    view["macroview_previews"] = build_previews(view)
    count = view.get("distinct_event_count")
    complete = view.get("canonical_event_projection_status") == "AVAILABLE"
    require((type(count) is int and count == len(view["events"])) if complete else count is None,
            "RADAR_CANONICAL_EVENT_COUNT_INVALID")
    return view


def radar_adapter_identity() -> tuple[Path, str]:
    module_file = Path(event_radar.__file__).resolve()
    require(module_file == Path(__file__).resolve().with_name("global_event_radar_read_adapter.py"),
            "RADAR_ADAPTER_MODULE_MISMATCH")
    require(callable(getattr(event_radar, "normalize_news_text", None))
            and callable(getattr(event_radar, "_feed_order_key", None)),
            "RADAR_ARTICLE_PROJECTION_UNAVAILABLE")
    require(callable(getattr(event_radar, "build_canonical_events", None)),
            "RADAR_CANONICAL_PROJECTION_UNAVAILABLE:RESTART_RADAR_ONLY_SERVER")
    return module_file, hashlib.sha256(module_file.read_bytes()).hexdigest()


class Handler(BaseHTTPRequestHandler):
    def reply(self, status: int, value: Any) -> None:
        data = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _html(self) -> None:
        showcase = any(os.environ.get(name, "").strip() == "1"
                       for name in ("RADAR_DEMO_MODE", "RADAR_LIVE_EIA", "RADAR_LIVE_ECB", "RADAR_LIVE_POLYMARKET", "RADAR_LIVE_MARKET_WATCH"))
        page_file = ROOT / "ui/radar_public_showcase_v1.html" if showcase or not UI.is_file() else UI
        page = page_file.read_text(encoding="utf-8")
        # Change only this read-only response's legacy local-operation labels.
        page = page.replace("LOCALHOST ONLY", "READ-ONLY RADAR").replace(
            '>LOCALHOST</span>', '>READ ONLY</span>')
        # Configuration is a strict boolean, never interpolated source/env text.
        demo = ",demoMode:true" if os.environ.get("RADAR_DEMO_MODE", "").strip() == "1" else ""
        data = page.replace("<script>",
                            '<script>window.__MACRO_OS_CONFIG__={radarOnly:true' + demo + '};</script><script>',
                            1).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        path = unquote(urlsplit(self.path).path)
        if path == "/healthz":
            self.reply(200, {"status": "ok", "service": "macro-trading-os-radar"})
        elif path in {"/ui/radar_interactive_map.js", "/ui/vendor/maplibre-gl.js", "/ui/vendor/maplibre-gl.css", "/ui/vendor/MAPLIBRE-LICENSE.txt"}:
            # Exact public-safe assets only; no directory traversal / file API.
            data = (ROOT / path.lstrip('/')).read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/css; charset=utf-8" if path.endswith('.css') else "text/javascript; charset=utf-8" if path.endswith('.js') else "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            # The map controller changes with UI semantics; keep only vendored
            # MapLibre bytes on the longer cache policy.
            self.send_header("Cache-Control", "no-cache" if path == "/ui/radar_interactive_map.js"
                             else "public, max-age=3600")
            self.end_headers();self.wfile.write(data)
        elif path == "/ui/radar_demo_translations.js":
            data = (ROOT / "ui/radar_demo_translations.js").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/javascript; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(data)
        elif path == "/api/app/replay":
            try:
                raw_query = urlsplit(self.path).query
                if len(raw_query) > 4096:
                    raise ValueError("QUERY_TOO_LARGE")
                query = parse_qs(raw_query, keep_blank_values=True, max_num_fields=4)
            except ValueError:
                self.reply(400, {"error": "INVALID_REPLAY_REQUEST", "read_only": True})
                return
            if (set(query) != {"event_id", "as_of"} or any(len(v) != 1 for v in query.values())
                    or not re.fullmatch(r"canonical-event-v0-[a-f0-9]{64}", query.get("event_id", [""])[0])):
                self.reply(400, {"error": "INVALID_REPLAY_REQUEST", "read_only": True})
                return
            from tools.stage1b_historical_campaign.radar_intelligence_store import IntelligenceStore, StoreError, time_value, configured_db
            from tools.stage1b_historical_campaign.radar_reality_replay import replay_event_as_of
            try:
                time_value(query["as_of"][0])
            except StoreError:
                self.reply(400, {"error": "INVALID_REPLAY_AS_OF", "read_only": True})
                return
            try:
                db_path = configured_db()
                if db_path is None:
                    raise StoreError("STORE_NOT_CONFIGURED")
                self.reply(200, replay_event_as_of(IntelligenceStore(db_path), query["event_id"][0], query["as_of"][0]))
            except (StoreError, OSError, ValueError):
                self.reply(503, {"error": "INTELLIGENCE_REPLAY_UNAVAILABLE", "read_only": True})
        elif path == "/api/app/radar":
            try:
                self.reply(200, feed_view(getattr(self.server, "live_ingestion", None), getattr(self.server, "expectation_sensor", None), vars(self.server).get('market_watch')))
            except GovernanceError as exc:
                self.reply(503, {"error": str(exc), "read_only": True})
        elif path == "/" or (path.startswith("/") and not path.startswith("/api/")):
            self._html()
        else:
            self.reply(404, {"error": "RADAR_ONLY_ROUTE_NOT_AVAILABLE", "read_only": True})

    def do_POST(self) -> None:
        self.close_connection = True
        self.reply(405, {"error": "RADAR_ONLY_READ_ONLY", "read_only": True})

    do_PUT = do_PATCH = do_DELETE = do_POST


def bind_server(*, radar_only: bool = True) -> ThreadingHTTPServer:
    require(radar_only, "RADAR_ONLY_REQUIRED")
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    server.radar_only = True
    server.daemon_threads = True
    server.live_ingestion = None
    server.expectation_sensor = None
    server.market_watch = None
    return server


def serve(open_browser: bool = False, *, radar_only: bool = True) -> None:
    require(radar_only, "RADAR_ONLY_REQUIRED")
    module_file, source_sha = radar_adapter_identity()
    require(UI.is_file() or (ROOT / "ui/radar_public_showcase_v1.html").is_file(), "RADAR_UI_UNAVAILABLE")
    print(f"RADAR_ADAPTER_MODULE={module_file}", flush=True)
    print(f"RADAR_ADAPTER_SHA256={source_sha}", flush=True)
    print("RADAR_CANONICAL_EVENT_CONTRACT=CANONICAL_EVENT_V0", flush=True)
    server = bind_server(radar_only=True)
    if os.environ.get("RADAR_LIVE_ECB", "").strip() == "1":
        from tools.stage1b_historical_campaign.live_source_ingestion import DiscoveryIngestion
        try:
            server.live_ingestion = DiscoveryIngestion.from_environment()
        except Exception:
            server.server_close()
            raise
    elif os.environ.get("RADAR_LIVE_EIA", "").strip() == "1":
        # Preserve the existing EIA-only launch/factory and environment contract.
        from tools.stage1b_historical_campaign.eia_live_ingestion import EiaIngestion
        try:
            server.live_ingestion = EiaIngestion.from_environment()
        except Exception:
            server.server_close()
            raise
    if os.environ.get('RADAR_LIVE_MARKET_WATCH', '').strip() == '1':
        from tools.stage1b_historical_campaign.radar_prediction_market_watch import PredictionMarketWatch
        server.market_watch = PredictionMarketWatch(enabled=True, ttl=int(os.environ.get('RADAR_MARKET_WATCH_TTL_SECONDS', '1800')))
    if os.environ.get("RADAR_LIVE_POLYMARKET", "").strip() == "1" and server.market_watch is None:
        from tools.stage1b_historical_campaign.radar_market_expectations import MarketExpectationSensor
        try:
            interval = int(os.environ.get("RADAR_POLYMARKET_REFRESH_SECONDS", "1800"))
            server.expectation_sensor = MarketExpectationSensor(interval=interval)
        except Exception:
            server.server_close()
            if server.live_ingestion is not None:
                server.live_ingestion.close()
            raise
    server.intelligence_recorder = None
    if os.environ.get("RADAR_PERSIST_INTELLIGENCE", "").strip() == "1":
        from tools.stage1b_historical_campaign.radar_intelligence_store import IntelligenceRecorder, configured_db, StoreError
        try:
            server.intelligence_recorder = IntelligenceRecorder(configured_db(),
                lambda: feed_view(server.live_ingestion, server.expectation_sensor, server.market_watch),
                interval=int(os.environ.get("RADAR_INTELLIGENCE_RECORD_SECONDS", "60")))
        except (StoreError, OSError, ValueError):
            # Storage is additive. Neither startup failure nor a recorder failure
            # makes current News/Evidence serving depend on database availability.
            print("RADAR_INTELLIGENCE_STATUS=UNAVAILABLE", flush=True)
    print(f"RADAR_LISTENING={HOST}:{server.server_port}", flush=True)
    print("RADAR READ-ONLY | NO LEGACY RUNTIME", flush=True)
    if open_browser:
        # An explicitly requested local convenience, never a server default.
        browser_host = "127.0.0.1" if HOST == "0.0.0.0" else HOST
        try:
            webbrowser.open(f"http://{browser_host}:{server.server_port}/#/feed")
        except Exception as exc:
            print(f"BROWSER_AUTO_OPEN_FAILED={type(exc).__name__}", flush=True)
    previous_sigterm = None
    if threading.current_thread() is threading.main_thread():
        previous_sigterm = signal.getsignal(signal.SIGTERM)
        def terminate(signum, frame):
            raise KeyboardInterrupt
        signal.signal(signal.SIGTERM, terminate)
    try:
        if getattr(server, "live_ingestion", None) is not None:
            server.live_ingestion.start()
        if getattr(server, "expectation_sensor", None) is not None:
            server.expectation_sensor.start()
        if getattr(server, "intelligence_recorder", None) is not None:
            server.intelligence_recorder.start()
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        if getattr(server, "intelligence_recorder", None) is not None:
            server.intelligence_recorder.close()
        if getattr(server, "expectation_sensor", None) is not None:
            server.expectation_sensor.close()
        if getattr(server, "live_ingestion", None) is not None:
            server.live_ingestion.close()
        if previous_sigterm is not None:
            signal.signal(signal.SIGTERM, previous_sigterm)
        print("STATUS: STOPPED", flush=True)


def main(argv: Sequence[str] | None = None) -> int:
    global HOST, PORT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--radar-only", action="store_true")
    parser.add_argument("--open-browser", action="store_true")
    parser.add_argument("--materialize", action="store_true")
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--host", default=os.environ.get("HOST") or "127.0.0.1")
    parser.add_argument("--port", type=int, default=os.environ.get("PORT") or 8765)
    args = parser.parse_args(argv)
    if not args.serve or not args.radar_only or args.materialize or args.preflight:
        parser.error("--radar-only requires --serve and cannot be combined with --materialize or --preflight")
    if not args.host.strip() or not 0 <= args.port <= 65535:
        parser.error("host must be nonempty and port must be between 0 and 65535 (0 selects a test port)")
    HOST, PORT = args.host.strip(), args.port
    serve(args.open_browser, radar_only=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
