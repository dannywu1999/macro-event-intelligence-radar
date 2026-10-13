import copy
import tempfile
import unittest
from pathlib import Path

from tools.stage1b_historical_campaign.radar_news_intelligence import project
from tools.stage1b_historical_campaign.radar_intelligence_store import IntelligenceStore
import test_bilingual_visual_ui as bilingual


class NewsResearchBridgeTests(unittest.TestCase):
    def setUp(self):
        self.ref = 'https://news.example.test/story/1'
        self.event_id = 'canonical-event-v0-' + 'a' * 64
        self.evidence_id = 'official-evidence-1'
        self.article = {
            'article_reference': self.ref,
            'title': 'ECB announces interest rate decision',
            'verification_status': 'UNVERIFIED_NEWS',
            'reported_at': '2026-10-12T08:00:00Z',
            'reported_time_kind': 'SOURCE_REPORTED_TIME',
            'observed_at': '2026-10-12T08:03:00Z',
            'observation_time_basis': 'FIRST_RECORDED_SOURCE_OBSERVATION',
            'news_source': {'name': 'News Desk', 'url': self.ref},
        }
        self.event = {
            'event_id': self.event_id,
            'article_references': [self.ref],
            'institution_context': [{'institution_id': 'ECB'}],
            'official_evidence_ids': [self.evidence_id],
        }
        self.fact = {
            'official_evidence_id': self.evidence_id,
            'canonical_event_id': self.event_id,
            'evidence_status': 'OFFICIAL_CONFIRMED',
            'authority_name': 'European Central Bank',
            'fact_proposition': 'The Governing Council decided to lower the three key ECB interest rates.',
            'document_title': 'Monetary policy decisions',
            'document_url': 'https://www.ecb.europa.eu/press/pr/date/2026/html/decision.en.html',
            'published_at': None,
            'first_seen_at': '2026-10-12T08:04:00Z',
            'retrieved_at': '2026-10-12T08:04:00Z',
            'link_status': 'LINKED',
        }
        self.library = {'cases': [{
            'status': 'AVAILABLE', 'research_case_id': 'ecb-2025-03-06',
            'receipt': {'event_id': 'historical-event', 'event_date': '2025-03-06'},
        }]}
        self.view = {
            'items': [self.article], 'events': [self.event], 'official_evidence': [self.fact],
            'discovery_sources': {'News Desk': {'status': 'LIVE', 'last_attempt_at': '2026-10-12T08:05:00Z'}},
            'news_freshness': {
                'as_of': '2026-10-12T08:06:00Z', 'window_hours': 48,
                'published_at': {self.ref: '2026-10-12T08:00:00Z'},
                'article_recency': {self.ref: 'LAST_24H'},
                'source_checks': {},
            },
        }

    def test_ecb_policy_article_links_specific_official_facts_and_same_topic_cases(self):
        card = project(copy.deepcopy(self.view), research_library=self.library)['cards'][self.ref]
        bridge = card['event_triage']
        self.assertEqual(bridge['event_identity_status'], 'CANONICAL_EVENT')
        self.assertEqual(bridge['verification_status'], 'OFFICIAL_PARTIAL')
        self.assertEqual(bridge['official_scope'], 'PARTIAL_ARTICLE_COVERAGE;EACH_FACT_PROPOSITION_SCOPED')
        self.assertEqual(bridge['official_propositions'][0]['match_rationale'],
                         'DIRECT_CANONICAL_EVENT_AND_EVIDENCE_ID_LINK')
        self.assertEqual(bridge['research_relation'], 'SAME_POLICY_TOPIC')
        self.assertEqual(bridge['research_case_ids'], ['ecb-2025-03-06'])
        self.assertEqual(bridge['market_observation_status'], 'HISTORICAL_ECB_DAILY_REFERENCE_AVAILABLE')
        self.assertEqual(bridge['causality_status'], 'NOT_ESTABLISHED')
        self.assertEqual(bridge['point_in_time_status'], 'REQUIRES_GENUINE_RECORDED_HISTORY')
        self.assertEqual(bridge['first_observed_at'], '2026-10-12T08:03:00Z')
        self.assertEqual(bridge['latest_provider_check_at'], '2026-10-12T08:05:00Z')

    def test_unrelated_article_never_receives_ecb_history_or_fx_observation(self):
        view = copy.deepcopy(self.view)
        view['items'][0]['title'] = 'Shipping route disruption reported in the Gulf'
        view['events'][0]['institution_context'] = []
        bridge = project(view, research_library=self.library)['cards'][self.ref]['event_triage']
        self.assertEqual(bridge['research_relation'], 'NO_VALID_HISTORICAL_ANALOGUE')
        self.assertEqual(bridge['research_case_ids'], [])
        self.assertEqual(bridge['market_observation_status'], 'MARKET_OBSERVATION_NOT_AVAILABLE')

    def test_official_match_requires_event_and_explicit_evidence_identity(self):
        view = copy.deepcopy(self.view)
        view['events'][0]['official_evidence_ids'] = []
        bridge = project(view, research_library=self.library)['cards'][self.ref]['event_triage']
        self.assertEqual(bridge['verification_status'], 'SOURCE_REPORTED_ONLY')
        self.assertEqual(bridge['official_propositions'], [])

    def test_conflicting_evidence_copy_is_not_summarized_as_confirmed(self):
        view = copy.deepcopy(self.view)
        view['official_evidence'][0]['link_status'] = 'CONFLICTING_EVIDENCE_COPIES'
        bridge = project(view, research_library=self.library)['cards'][self.ref]['event_triage']
        self.assertEqual(bridge['verification_status'], 'CONFLICTING_EVIDENCE')

    def test_ambiguous_event_membership_blocks_historical_link(self):
        view = copy.deepcopy(self.view)
        view['events'].append({**self.event, 'event_id': 'canonical-event-v0-' + 'b' * 64})
        bridge = project(view, research_library=self.library)['cards'][self.ref]['event_triage']
        self.assertEqual(bridge['event_identity_status'], 'NO_UNAMBIGUOUS_CANONICAL_EVENT')
        self.assertIsNone(bridge['canonical_event_id'])
        self.assertEqual(bridge['research_case_ids'], [])

    def test_history_is_not_added_to_news_counts(self):
        output = project(copy.deepcopy(self.view), research_library=self.library)
        self.assertEqual(output['eligible_article_count'], 1)
        self.assertEqual(output['eligible_development_count'], 1)
        self.assertEqual(len(self.view['items']), 1)

    def test_historical_import_is_recorded_now_not_as_past_knowledge(self):
        view = copy.deepcopy(self.view)
        view['status'] = 'AVAILABLE'
        view['items'][0]['observed_at'] = '2025-03-01T10:00:00Z'
        view['items'][0]['reported_at'] = '2025-02-28T08:00:00Z'
        with tempfile.TemporaryDirectory() as directory:
            store = IntelligenceStore(Path(directory) / 'prospective.sqlite3', create=True)
            store.ingest_projection(view, observed_at='2026-10-12T09:00:00Z')
            before = store.read_as_of(self.event_id, '2025-12-31T23:59:59Z')
            at_recording = store.read_as_of(self.event_id, '2026-10-12T09:00:00Z')
        self.assertEqual(before, [])
        article = next(row for row in at_recording if row['observation_kind'] == 'NEWS_ARTICLE')
        self.assertEqual(article['observed_at'], '2026-10-12T09:00:00.000000Z')
        self.assertEqual(article['source_timestamp'], '2025-02-28T08:00:00.000000Z')


class NewsResearchBridgeUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        bilingual.BilingualVisualTests.setUpClass()
        cls.ui = bilingual.BilingualVisualTests()
        cls.ui.html = bilingual.BilingualVisualTests.html
        cls.ui.translations = bilingual.BilingualVisualTests.translations
        cls.base_view = bilingual.BilingualVisualTests.view

    @classmethod
    def tearDownClass(cls):
        bilingual.BilingualVisualTests.tearDownClass()

    def test_news_card_renders_bilingual_bridge_and_historical_case_action(self):
        view = copy.deepcopy(self.base_view)
        item = view['items'][0]
        card = view['news_intelligence']['cards'][item['article_reference']]
        case = next(c for c in view['market_research_library']['cases'] if c['status'] == 'AVAILABLE')
        card['event_triage']['research_case_ids'] = [case['research_case_id']]
        result = self.ui.render(view=view)
        self.assertIn('Event research path', result['en'])
        self.assertIn('事件研究路徑', result['zh'])
        self.assertIn('Official documents support only these linked propositions', result['en'])
        self.assertIn('官方文件只支持以下已連結的具體命題', result['zh'])
        self.assertIn(f'data-news-research-case="{case["research_case_id"]}"', result['en'])
        self.assertIn('ECB EXR.D.USD.EUR.SP00.A', result['en'])
        self.assertIn(f'href="{case["receipt"]["market_data_source"].replace("&", "&amp;")}"', result['en'])
        self.assertIn('EX_POST', result['zh'])


if __name__ == '__main__':
    unittest.main()
