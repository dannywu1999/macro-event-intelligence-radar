"""Headless read-only serving branch of the unified app; standard library only.

No research/control-plane imports, materialization, background refresh, or writes.
The sole Radar adapter and the existing unified HTML remain the product sources.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import unquote, urlsplit

from tools.stage1b_historical_campaign import global_event_radar_read_adapter as event_radar

ROOT = Path(__file__).resolve().parents[2]
UI = ROOT / "ui" / "macro_trading_os_unified_app_v1.html"
HOST, PORT = "127.0.0.1", 8765
GovernanceError = event_radar.EvidenceReadError


def require(value: bool, code: str) -> None:
    if not value:
        raise GovernanceError(code)


def feed_view() -> dict[str, Any]:
    view = event_radar.build_radar_view()
    require(isinstance(view, dict) and isinstance(view.get("events"), list)
            and view.get("canonical_event_contract") == "CANONICAL_EVENT_V0",
            "RADAR_CANONICAL_PROJECTION_UNAVAILABLE:RESTART_RADAR_ONLY_SERVER")
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
        page = UI.read_text(encoding="utf-8")
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
        elif path == "/ui/radar_demo_translations.js":
            # A fixed public presentation asset, never an evidence or API input.
            data = (ROOT / "ui" / "radar_demo_translations.js").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/javascript; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(data)
        elif path == "/api/app/radar":
            try:
                self.reply(200, feed_view())
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
    return server


def serve(open_browser: bool = False, *, radar_only: bool = True) -> None:
    require(radar_only, "RADAR_ONLY_REQUIRED")
    module_file, source_sha = radar_adapter_identity()
    require(UI.is_file(), "RADAR_UI_UNAVAILABLE")
    print(f"RADAR_ADAPTER_MODULE={module_file}", flush=True)
    print(f"RADAR_ADAPTER_SHA256={source_sha}", flush=True)
    print("RADAR_CANONICAL_EVENT_CONTRACT=CANONICAL_EVENT_V0", flush=True)
    server = bind_server(radar_only=True)
    print(f"RADAR_LISTENING={HOST}:{server.server_port}", flush=True)
    print("RADAR READ-ONLY | NO LEGACY RUNTIME", flush=True)
    if open_browser:
        # An explicitly requested local convenience, never a server default.
        browser_host = "127.0.0.1" if HOST == "0.0.0.0" else HOST
        try:
            webbrowser.open(f"http://{browser_host}:{server.server_port}/#/feed")
        except Exception as exc:
            print(f"BROWSER_AUTO_OPEN_FAILED={type(exc).__name__}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
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
