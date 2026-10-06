"""Actual served frontend JavaScript + isolated HTTP server; no external network."""
import copy
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import unittest
import test_public_root_route as http_fixture
ROOT = http_fixture.ROOT

BUNDLED_NODE = Path.home() / ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe"
NODE = os.environ.get('RADAR_TEST_NODE') or (str(BUNDLED_NODE) if BUNDLED_NODE.is_file() else shutil.which('node'))
TARGET = "canonical-event-v0-3157198c23e7f1b75248aaeb68f4ab5b750adcfb54749b60143dcb231530abf3"


class BilingualVisualTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        http_fixture.PublicRootRouteTests.setUpClass()
        try:
            cls.http = http_fixture.PublicRootRouteTests()
            cls.html = cls.http.request("/")[2].decode("utf-8")
            status, content_type, data = cls.http.request("/ui/radar_demo_translations.js")
            assert status == 200 and content_type == "text/javascript; charset=utf-8"
            cls.translations = data.decode("utf-8")
            cls.view = json.loads(cls.http.request("/api/app/radar")[2])
        except BaseException:
            http_fixture.PublicRootRouteTests.tearDownClass()
            raise

    @classmethod
    def tearDownClass(cls):
        http_fixture.PublicRootRouteTests.tearDownClass()

    def render(self, **options):
        payload = dict(html=self.html, translations=self.translations, view=copy.deepcopy(self.view))
        payload.update(options)
        result = subprocess.run([NODE, str(ROOT / "tests/ui_render_harness.cjs")], input=json.dumps(payload),
                                text=True, encoding="utf-8", capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_browser_locale_and_real_language_clicks(self):
        result = self.render(locale="zh-HK")
        self.assertEqual(result["initial"]["language"], "zh-TW")
        self.assertEqual(result["initial"]["title"], "全球事件雷達")
        self.assertIn("新聞發現", result["zh"])
        self.assertIn("Canonical Events", result["en"])
        self.assertEqual(result["requests"], ["/api/app/radar"])
        self.assertEqual(result["pressed"], ["false", "true"])
        self.assertEqual(result["busy"], "false")

    def test_saved_choice_and_storage_failure(self):
        result = self.render(locale="zh-TW", storage={"radar-language": "en"})
        self.assertEqual(result["initial"]["language"], "en")
        self.assertEqual(result["storage"]["radar-language"], "en")
        self.assertEqual(self.render(locale="zh-TW", storageBlocked=True)["initial"]["language"], "zh-TW")
        self.assertEqual(self.render(locale="en-US", storage={"radar-language": "bogus"})["initial"]["language"], "en")

    def test_five_title_and_one_fact_translations_are_presentation_only(self):
        metadata = json.loads(self.translations.split("=", 1)[1].strip().rstrip(";"))
        self.assertTrue(metadata["presentation_only"])
        self.assertEqual(set(metadata["events"]), {e["event_id"] for e in self.view["events"]})
        self.assertEqual(set(metadata["facts"]), {e["official_evidence_id"] for e in self.view["official_evidence"]})
        result = self.render()
        self.assertEqual(result["zh"].count('data-presentation-only="true"'), 6)
        self.assertIn("中文翻譯僅供閱讀，原始英文為證據依據。", result["zh"])
        self.assertIn("not official EIA translations", result["en"])
        self.assertTrue(result["unchanged"])

    def test_full_authoritative_english_is_exposed_in_both_languages(self):
        result = self.render()
        for html in (result["zh"], result["en"]):
            for event in self.view["events"]:
                self.assertIn(event["event_title"], html)
                self.assertIn(event["event_id"], html)
            evidence = self.view["official_evidence"][0]
            for key in ("fact_proposition", "document_title", "official_evidence_id", "authority_name"):
                self.assertIn(evidence[key], html)
            self.assertIn('href="'+evidence["document_url"]+'"', html)
            self.assertIn('rel="noopener noreferrer"', html)

    def test_visual_flow_real_counts_and_status_legend(self):
        result = self.render()
        for html in (result["zh"], result["en"]):
            self.assertIn('class="flow"', html)
            for key, count in (("newsCount", 5), ("eventCount", 5), ("factCount", 1)):
                self.assertIn(f'data-count="{key}">{count}</div>', html)
            self.assertIn('class="legend"', html)
            self.assertEqual(html.count('data-event-status="UNVERIFIED_NEWS"'), 5)
            self.assertEqual(html.count('data-evidence-status="OFFICIAL_CONFIRMED"'), 1)
        self.assertIn("not every claim", result["en"])
        self.assertIn("不代表整則新聞或事件都被確認", result["zh"])

    def test_evidenced_event_first_without_mutating_api_order(self):
        view = copy.deepcopy(self.view)
        view["events"].reverse()
        result = self.render(view=view)
        self.assertTrue(result["unchanged"])
        self.assertEqual(re.findall(r'data-event-id="([^"]+)"', result["en"])[0], TARGET)
        self.assertEqual(result["en"].count('<details class="official-panel" open>'), 1)
        self.assertEqual(result["en"].count('class="no-evidence"'), 4)
        self.assertIn("Display only", result["en"])
        self.assertIn('<details class="provenance"><summary>Details', result["en"])

    def test_unknown_publication_occurrence_and_health_are_not_fabricated(self):
        result = self.render()
        self.assertIn("Published: <time>Unknown</time>", result["en"])
        self.assertIn("發布時間: <time>未知</time>", result["zh"])
        self.assertIn("Event occurrence: Unknown", result["en"])
        self.assertIn("Source health: <strong>Unknown</strong>", result["en"])
        self.assertIsNone(self.view["official_evidence"][0]["published_at"])

    def test_translation_and_demo_notice_are_demo_flag_only(self):
        html = self.html.replace(",demoMode:true", "")
        result = self.render(html=html)
        self.assertNotIn('data-presentation-only="true"', result["zh"])
        self.assertNotIn('class="demo-notice"', result["en"])
        self.assertIn('class="demo-notice"', self.render()["en"])

    def test_escaping_and_non_http_links_are_rejected(self):
        view = copy.deepcopy(self.view)
        attack = '<img src=x onerror="alert(1)">'
        view["events"][0]["event_title"] = attack
        view["events"][0]["source_names"] = [attack]
        view["items"][0]["title"] = attack
        view["items"][0]["news_source"]["url"] = "javascript:alert(1)"
        view["official_evidence"][0]["fact_proposition"] = attack
        view["official_evidence"][0]["document_url"] = 'javascript:alert(1)'
        result = self.render(view=view)
        for html in (result["en"], result["zh"]):
            self.assertNotIn('<img', html)
            self.assertIn('&lt;img src=x onerror=&quot;alert(1)&quot;&gt;', html)
            self.assertNotIn('href="javascript:', html)

    def test_empty_view_has_no_demo_events_or_invented_counts(self):
        view = copy.deepcopy(self.view)
        view.update(events=[], items=[], official_evidence=[], distinct_event_count=None, news_item_count=0)
        result = self.render(view=view)
        self.assertNotIn('data-event-id=', result["en"])
        self.assertIn('data-count="eventCount">Unknown', result["en"])
        self.assertIn('No records available.', result["en"])

    def test_fetch_error_is_accessible_and_escaped_in_both_languages(self):
        result = self.render(failure='<script>bad</script>')
        for html in (result["zh"], result["en"]):
            self.assertIn('role="alert"', html)
            self.assertNotIn('<script>', html)
        self.assertIn('無法載入唯讀新聞', result["zh"])

    def test_responsive_and_keyboard_accessibility_structure(self):
        for token in ('@media(min-width:1440px)', '@media(max-width:1100px)', '@media(max-width:650px)',
                      'minmax(0,1fr)', 'grid-template-columns:1fr', ':focus-visible', 'aria-pressed=',
                      'type="button"', '<nav ', '<main ', 'aria-hidden="true"'):
            self.assertIn(token, self.html)
        self.assertNotIn('MACRO TRADING OS', self.html)
        self.assertNotIn('onclick=', self.html)
        self.assertNotIn('https://', self.html.split('<style>')[1].split('</style>')[0])

    def test_translation_not_loaded_by_adapter_and_container_contains_asset(self):
        adapter = (ROOT / 'tools/stage1b_historical_campaign/global_event_radar_read_adapter.py').read_text(encoding='utf-8')
        self.assertNotIn('RADAR_DEMO_TRANSLATIONS', adapter)
        self.assertNotIn('radar_demo_translations', adapter)
        self.assertIn('COPY ui/radar_demo_translations.js ui/radar_demo_translations.js', (ROOT / ('Dockerfile' if (ROOT/'Dockerfile').is_file() else 'Dockerfile.radar')).read_text())
        self.assertIn('!ui/radar_demo_translations.js', (ROOT / ('.dockerignore' if (ROOT/'.dockerignore').is_file() else 'Dockerfile.radar.dockerignore')).read_text())

    def test_live_status_is_bilingual_and_separate_from_health(self):
        view=copy.deepcopy(self.view)
        view['live_ingestion']={'enabled':True,'status':'LIVE','last_success_at':'2026-10-06T15:00:00Z'}
        result=self.render(view=view)
        self.assertIn('CLOUD-UPDATED EIA FEED',result['en'])
        self.assertIn('雲端自動更新 EIA 資料',result['zh'])
        self.assertIn('2026-10-06T15:00:00Z',result['zh'])
        self.assertIn('Source health: <strong>Unknown',result['en'])
        self.assertNotIn('PUBLIC DEMO',result['en'])
        self.assertTrue(result['unchanged'])

    def test_starting_and_fallback_are_not_fatal_and_never_hide_data(self):
        for status in ('STARTING','SNAPSHOT_FALLBACK'):
            view=copy.deepcopy(self.view)
            view['live_ingestion']={'enabled':True,'status':status,'last_success_at':None}
            result=self.render(view=view)
            self.assertEqual(result['en'].count('data-event-status="UNVERIFIED_NEWS"'),5)
            self.assertNotIn('class="error"',result['en'])
            self.assertIn('validated snapshot',result['en'])
            self.assertIn('已驗證快照',result['zh'])

    def test_new_article_has_original_english_without_fake_translation(self):
        view=copy.deepcopy(self.view)
        event=copy.deepcopy(view['events'][1])
        event.update(event_id='new-eia-event',event_title='New EIA article in English',official_evidence_ids=[],official_evidence_count=0)
        view['events'].append(event)
        result=self.render(view=view)
        self.assertIn('原文 / Original',result['zh'])
        self.assertIn('New EIA article in English',result['zh'])
        self.assertEqual(result['zh'].count('data-presentation-only="true"'),6)

    def test_event_timelines_are_bilingual_and_only_evidenced_one_is_expanded(self):
        result=self.render()
        for markup in (result['en'],result['zh']):
            self.assertEqual(markup.count('class="event-timeline"'),5)
            self.assertEqual(markup.count('<details class="event-timeline" open>'),1)
            self.assertEqual(markup.count('data-timeline-type="NEWS_DISCOVERED"'),5)
            self.assertEqual(markup.count('data-timeline-type="OFFICIAL_EVIDENCE"'),1)
        self.assertIn('Event Timeline',result['en'])
        self.assertIn('事件時間軸',result['zh'])
        self.assertIn('Current status',result['en'])
        self.assertIn('目前狀態',result['zh'])
        self.assertTrue(result['unchanged'])

    def test_timeline_official_observation_and_publication_labels_are_distinct(self):
        result=self.render()
        self.assertIn('data-timestamp-role="EVIDENCE_FIRST_SEEN_AT"',result['en'])
        self.assertIn('Evidence first observed:',result['en'])
        self.assertIn('首次取得證據:',result['zh'])
        self.assertIn('Published: Unknown',result['en'])
        self.assertIn('發布時間: 未知',result['zh'])
        self.assertIn(' UTC</time>',result['en'])
        self.assertIn('title="2026-10-06T03:15:25.730676Z"',result['en'])
        self.assertNotIn('data-timestamp-role="EVIDENCE_PUBLISHED_AT"',result['en'])

    def test_unknown_timeline_time_has_a_separate_section(self):
        view=copy.deepcopy(self.view)
        entry=view['events'][0]['timeline'][0]
        entry.update(timestamp=None,timestamp_role='UNKNOWN',observed_at=None)
        result=self.render(view=view)
        self.assertIn('class="timeline-unknown"',result['en'])
        self.assertIn('Time unknown',result['en'])
        self.assertIn('時間未知',result['zh'])
        self.assertNotIn('Invalid Date',result['en'])

    def test_timeline_titles_sources_links_and_role_fields_are_escaped(self):
        view=copy.deepcopy(self.view)
        entry=view['events'][0]['timeline'][0]
        entry.update(title='<img src=x onerror="bad()">',source_name='<script>bad()</script>',source_url='javascript:bad()',timestamp_role='UNKNOWN')
        result=self.render(view=view)
        for markup in (result['en'],result['zh']):
            self.assertNotIn('<img',markup)
            self.assertNotIn('<script>',markup)
            self.assertNotIn('href="javascript:',markup)
            self.assertIn('&lt;img',markup)
        self.assertIn('href="https://www.eia.gov/todayinenergy/detail.php?id=68245"',result['en'])

    def test_timeline_summary_and_current_status_do_not_claim_event_verification(self):
        result=self.render()
        self.assertIn('2 Timeline entries',result['en'])
        self.assertIn('1 News reports',result['en'])
        self.assertIn('1 Official Evidence items',result['en'])
        self.assertIn('Event remains UNVERIFIED_NEWS;',result['en'])
        self.assertIn('事件仍為未驗證新聞',result['zh'])
        self.assertIn('data-timeline-presentation-only="true"',result['zh'])
        self.assertNotIn('Event verified',result['en'])

    def test_live_and_fallback_timelines_are_derived_from_the_same_event_data(self):
        for status in ('LIVE','SNAPSHOT_FALLBACK'):
            view=copy.deepcopy(self.view)
            view['live_ingestion']={'enabled':True,'status':status,'last_success_at':None}
            result=self.render(view=view)
            self.assertEqual(result['en'].count('class="event-timeline"'),5)
            self.assertEqual(result['en'].count('data-timeline-type="OFFICIAL_EVIDENCE"'),1)


if __name__ == '__main__':
    unittest.main()
