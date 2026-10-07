"""Root Showcase and read-only HTTP regression, from this standalone tree only."""
import hashlib
import http.client
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import unittest
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]


class PublicRootRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        manifest_path = ROOT / "PUBLIC_RELEASE_MANIFEST.json"
        if manifest_path.is_file():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        else:
            # MAIN source tree: exact product files only, never legacy/handoff scans.
            manifest = {"files": ["ui/radar_public_showcase_v1.html", "ui/radar_demo_translations.js",
                "tools/stage1b_historical_campaign/radar_web_server.py",
                "tools/stage1b_historical_campaign/eia_live_ingestion.py",
                "tools/stage1b_historical_campaign/global_event_radar_read_adapter.py",
                "demo/radar_public/news/rss_headlines_eia_snapshot.csv",
                "demo/radar_public/official-packet.json", "demo/radar_public/metadata.json"]}
        cls.before = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                      for name in manifest["files"]}
        # Compare current working-tree bytes before/after serving. Git line-ending
        # conversion is separate from the root-route/read-only contract.
        env = {k: v for k, v in os.environ.items() if not k.startswith("GLOBAL_EVENT_RADAR_")
               and k not in {"HOST", "PORT", "RADAR_DATA_ROOT", "RADAR_DEMO_MODE", "RADAR_LIVE_EIA", "RADAR_LIVE_ECB", "RADAR_RUNTIME_ROOT", "PYTHONPATH"}}
        env.update({"HOST": "127.0.0.1", "PORT": "0", "RADAR_DATA_ROOT": str(ROOT / "demo/radar_public"),
                    "GLOBAL_EVENT_RADAR_NEWS_PATH": "news",
                    "GLOBAL_EVENT_RADAR_OFFICIAL_PATH": "official-packet.json", "RADAR_DEMO_MODE": "1"})
        launch = "import sys,runpy;sys.path.insert(0,sys.argv[1]);sys.argv=['radar','--serve','--radar-only'];runpy.run_module('tools.stage1b_historical_campaign.radar_web_server',run_name='__main__')"
        cls.process = subprocess.Popen([sys.executable, "-I", "-B", "-X", "utf8", "-c", launch, str(ROOT)],
                cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, encoding="utf-8")
        lines = queue.Queue()
        def read():
            for line in cls.process.stdout:
                lines.put(line.strip())
        cls.reader = threading.Thread(target=read, daemon=True)
        cls.reader.start()
        try:
            cls.port = None
            adapter = None
            for _ in range(8):
                line = lines.get(timeout=8)
                if line.startswith("RADAR_ADAPTER_MODULE="):
                    adapter = Path(line.split("=", 1)[1])
                if line.startswith("RADAR_LISTENING="):
                    cls.port = int(line.rsplit(":", 1)[1])
                    break
            if cls.port is None or cls.port == 8765:
                raise AssertionError("ISOLATED_TEST_PORT_REQUIRED")
            if adapter != ROOT / "tools/stage1b_historical_campaign/global_event_radar_read_adapter.py":
                raise AssertionError("WRONG_CHECKOUT_IMPORT")
        except BaseException:
            cls.close_server()
            raise

    @classmethod
    def close_server(cls):
        if cls.process.poll() is None:
            cls.process.terminate()
        cls.process.wait(timeout=8)
        cls.reader.join(timeout=2)
        cls.process.stdout.close()
        cls.process.stderr.close()

    @classmethod
    def tearDownClass(cls):
        cls.close_server()
        after = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in cls.before}
        if cls.before != after:
            raise AssertionError("SOURCE_BYTES_CHANGED")

    def request(self, path, method="GET"):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            connection.request(method, path)
            response = connection.getresponse()
            return response.status, response.getheader("Content-Type"), response.read()
        finally:
            connection.close()

    def test_root_is_existing_showcase_html(self):
        status, content_type, body = self.request("/")
        self.assertEqual(status, 200)
        self.assertEqual(content_type, "text/html; charset=utf-8")
        page = body.decode("utf-8")
        self.assertTrue(page.startswith("<!doctype html>"))
        for text in ("radarOnly:true", "demoMode:true", "News Discovery", "Canonical Events",
                     "Official Evidence", "PUBLIC DEMO", "READ-ONLY SNAPSHOT"):
            self.assertIn(text, page)
        expected = (ROOT / "ui/radar_public_showcase_v1.html").read_text(encoding="utf-8")
        expected = expected.replace("LOCALHOST ONLY", "READ-ONLY RADAR").replace('>LOCALHOST</span>', '>READ ONLY</span>')
        expected = expected.replace("<script>", '<script>window.__MACRO_OS_CONFIG__={radarOnly:true,demoMode:true};</script><script>', 1)
        self.assertEqual(page, expected)

    def test_index_and_feed_reuse_root_html(self):
        root = self.request("/")
        self.assertEqual(self.request("/index.html"), root)
        self.assertEqual(self.request("/feed"), root)

    def test_hash_fragment_requires_only_root_request(self):
        url = urlsplit("http://127.0.0.1:" + str(self.port) + "/#/feed")
        self.assertEqual((url.path, url.fragment), ("/", "/feed"))
        self.assertEqual(self.request(url.path)[0], 200)

    def test_health_is_minimal_and_available(self):
        status, _, body = self.request("/healthz")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), {"status": "ok", "service": "macro-trading-os-radar"})

    def test_radar_five_five_one_and_evidence_semantics(self):
        status, _, body = self.request("/api/app/radar")
        self.assertEqual(status, 200)
        view = json.loads(body)
        self.assertEqual((len(view["items"]), len(view["events"]), view["distinct_event_count"], len(view["official_evidence"])), (5, 5, 5, 1))
        metadata = json.loads((ROOT / "demo/radar_public/metadata.json").read_text(encoding="utf-8"))
        self.assertEqual(sorted(e["event_id"] for e in view["events"]), metadata["canonical_event_ids"])
        self.assertEqual([e["official_evidence_id"] for e in view["official_evidence"]], metadata["official_evidence_ids"])
        linked = [e for e in view["events"] if e["official_evidence_count"]]
        self.assertEqual(len(linked), 1)
        self.assertEqual((linked[0]["verification_status"], linked[0]["official_evidence_count"]), ("UNVERIFIED_NEWS", 1))
        self.assertTrue(all(e["official_evidence_count"] == 0 for e in view["events"] if e not in linked))
        self.assertEqual(view["official_evidence"][0]["evidence_status"], "OFFICIAL_CONFIRMED")
        self.assertIsNone(view["official_evidence"][0]["published_at"])

    def test_write_methods_and_other_apis_remain_inaccessible(self):
        for method in ("POST", "PUT", "PATCH", "DELETE"):
            self.assertEqual(self.request("/api/app/radar", method)[0], 405)
        for path in ("/api/app/status", "/api/app/refresh", "/api/paper", "/api/broker", "/api/live"):
            self.assertEqual(self.request(path)[0], 404)


if __name__ == "__main__":
    unittest.main()
