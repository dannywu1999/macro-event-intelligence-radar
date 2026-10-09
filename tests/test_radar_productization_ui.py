"""Actual Showcase rendering with synthetic, in-memory data and no provider calls."""
import json
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NODE = Path.home() / ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe"


def render():
    event = {
        "event_id": "synthetic-event-1", "event_title": "Synthetic headline",
        "verification_status": "UNVERIFIED_NEWS", "source_names": ["Fixture News"],
        "article_count": 1, "first_detected_at": "2026-10-08T12:00:00Z",
        "latest_article_at": "2026-10-08T12:00:00Z", "event_geography": {"status": "UNKNOWN", "geography": []},
        "geography_status": "UNKNOWN", "geography": [], "timeline": [],
    }
    market = {
        "market_id": "synthetic-market-1", "question": "<script>not executable</script>",
        "category": "ENERGY", "market_status": "ACTIVE", "source_status": "SAVED_SNAPSHOT",
        "outcome_type": "BINARY_YES_NO", "outcomes": ["Yes", "No"],
        "probabilities": [0.3, 0.7], "link_status": "NO_MATCH", "canonical_event_id": None,
    }
    view = {
        "events": [event], "items": [], "news_item_count": 1, "distinct_event_count": 1,
        "official_evidence": [], "macroview_previews": [], "status": "AVAILABLE",
        "health_status": "UNKNOWN", "latest_observed_data_at": "2026-10-08T12:00:00Z",
        "prediction_market_watch": {"markets": [market], "market_count": 1,
                                    "categories": ["ENERGY"], "source_status": "SAVED_SNAPSHOT",
                                    "status": "AVAILABLE", "provider": {"reason": None}},
    }
    packet = {"html": (ROOT / "ui/radar_public_showcase_v1.html").read_text(encoding="utf-8"),
              "translations": (ROOT / "ui/radar_demo_translations.js").read_text(encoding="utf-8"),
              "view": view}
    result = subprocess.run([str(NODE), str(ROOT / "tests/ui_render_harness.cjs")],
                            input=json.dumps(packet), capture_output=True, text=True,
                            encoding="utf-8", timeout=20, check=True)
    return json.loads(result.stdout)


class ProductizationUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = render()

    def test_map_is_above_event_feed_and_market_cards(self):
        for lang in ("zh", "en"):
            html = self.result[lang]
            self.assertLess(html.index('id="world-map"'), html.index('id="canonical-events"'))
            self.assertLess(html.index('id="canonical-events"'), html.index('id="prediction-market-watch"'))
            self.assertIn('href="#world-map"', html)
            self.assertIn('class="map-svg-fallback"', html)

    def test_truth_guide_and_zh_translation(self):
        zh = self.result["zh"]
        en = self.result["en"]
        for text in ("新聞是發現線索", "官方證據只確認具體命題", "預測市場呈現參與者預期",
                     "推測地理脈絡與機構總部不是事件發生地", "市場預期", "來源狀態", "地圖參照標記"):
            self.assertIn(text, zh)
        for text in ("News is discovery", "specific proposition", "Market expectations", "Source status"):
            self.assertIn(text, en)

    def test_unknown_health_and_unlinked_market_are_explicit(self):
        zh = self.result["zh"]
        self.assertIn("最新文章觀測時間與來源健康是不同指標", zh)
        self.assertIn("有可信連結的市場: 0", zh)
        self.assertIn("未連結市場: 1", zh)
        self.assertIn("NO_MATCH", zh)
        self.assertNotIn('data-map-event="synthetic-event-1"', zh.split('id="prediction-market-watch"')[1].split('</section>')[0])

    def test_dynamic_market_title_escaped_and_source_view_unchanged(self):
        self.assertIn("&lt;script&gt;not executable&lt;/script&gt;", self.result["zh"])
        self.assertTrue(self.result["unchanged"])
        self.assertEqual(self.result["requests"], ["/api/app/radar"])

    def test_maplibre_popup_outside_app_focuses_event(self):
        self.assertTrue(self.result["popupFocus"])
        self.assertTrue(self.result["popupScroll"])
        self.assertTrue(self.result["popupTimeline"])
        self.assertTrue(self.result["popupProvenance"])


if __name__ == "__main__":
    unittest.main()
