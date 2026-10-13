import copy,json,tempfile,unittest,hashlib
from pathlib import Path
from unittest.mock import patch
from tools.stage1b_historical_campaign.radar_news_intelligence import (
    project,is_ecb_decision,capture_snapshot,attach_recording_status,metadata_hash,research_clocks)
from tools.stage1b_historical_campaign.radar_intelligence_store import IntelligenceStore,StoreError,canonical
from tools.stage1b_historical_campaign.radar_reality_replay import replay_event_as_of
from tools.stage1b_historical_campaign.radar_macroview_freeze import preview_macroview
from tools.stage1b_historical_campaign.global_event_radar_read_adapter import build_canonical_events

class ProspectiveResearchTests(unittest.TestCase):
    def setUp(self):
        self.ref='https://example.test/article'
        self.article=dict(article_reference=self.ref,title='ECB announces interest rate decision',
            news_source=dict(name='News Desk',url=self.ref),reported_at='2025-03-06T13:15:00Z',
            reported_time_kind='REPORTED_TIME',observed_at=None,discovered_at=None,verification_status='UNVERIFIED_NEWS')
        self.view=dict(status='AVAILABLE',items=[self.article],official_evidence=[],market_expectations=[],discovery_sources={})
        self.view.update(build_canonical_events(self.view['items']))
        self.event_id=self.view['events'][0]['event_id']
        self.data=json.dumps(self.view).encode()
        self.retrieval=dict(http_status=200,retrieved_at='2026-10-12T12:00:00Z',sha256=hashlib.sha256(self.data).hexdigest(),url='https://public.test/api/app/radar')
        self.clock='2026-10-12T13:00:00Z'
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/'new-capture'

    def capture(self):
        with patch('tools.stage1b_historical_campaign.radar_intelligence_store.now',return_value=self.clock):
            return capture_snapshot(self.data,self.retrieval,[self.ref],self.root)

    def test_historical_publication_does_not_create_historical_knowledge(self):
        result=self.capture();store=IntelligenceStore(self.root/'evidence.sqlite3')
        self.assertEqual(result['recorded_at'],self.clock)
        self.assertEqual(replay_event_as_of(store,self.event_id,'2025-12-31T23:59:59Z')['replay_status'],'NO_OBSERVATIONS')
        replay=replay_event_as_of(store,self.event_id,self.clock)
        row=replay['news_observations'][0]
        self.assertEqual(row['source_timestamp'],'2025-03-06T13:15:00.000000Z')
        self.assertEqual(row['observed_at'],'2026-10-12T13:00:00.000000Z')
        self.assertIsNone(row['payload']['observed_at'])

    def test_capture_receipt_content_address_and_no_authoritative_freeze(self):
        result=self.capture();r=json.loads(next(self.root.glob('prospective-news-*.json')).read_bytes())
        identity=r.pop('receipt_id')
        self.assertEqual(identity,'prospective-news-v1-'+hashlib.sha256(canonical(r).encode()).hexdigest())
        self.assertEqual(r['content_hash'],metadata_hash(self.article))
        self.assertEqual(r['hash_scope'],'TITLE_SOURCE_TIME_METADATA_ONLY')
        self.assertIsNone(r['first_observed_at'])
        self.assertEqual(r['publication_precision'],'UNKNOWN')
        self.assertEqual(r['publication_time_basis'],'REPORTED_TIME')
        self.assertFalse(r['authoritative_frozen_macroview'])
        self.assertEqual(result['persisted_frozen_macroviews'],0)
        with IntelligenceStore(self.root/'evidence.sqlite3').connection() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM macroview_freezes').fetchone()[0],0)

    def test_capture_rejects_existing_directory_without_writes(self):
        self.root.mkdir();(self.root/'sentinel').write_text('keep')
        with self.assertRaisesRegex(StoreError,'PILOT_NEW_EXTERNAL_DIRECTORY_REQUIRED'):self.capture()
        self.assertEqual([p.name for p in self.root.iterdir()],['sentinel'])

    def test_bad_retrieval_hash_is_rejected_before_directory_creation(self):
        self.retrieval['sha256']='0'*64
        with self.assertRaisesRegex(StoreError,'HASH_MISMATCH'):self.capture()
        self.assertFalse(self.root.exists())

    def test_future_retrieval_is_rejected(self):
        self.retrieval['retrieved_at']='2027-01-01T00:00:00Z'
        with self.assertRaisesRegex(StoreError,'FUTURE_RETRIEVAL'):self.capture()
        self.assertFalse(self.root.exists())

    def test_missing_timestamps_remain_unknown_not_zero_latency(self):
        clocks=research_clocks(self.article,{})
        self.assertIsNone(clocks['first_observed_at'])
        self.assertIsNone(clocks['recorded_at'])
        self.assertIsNone(clocks['discovery_latency_seconds'])
        self.assertEqual(clocks['discovery_latency_status'],'UNKNOWN')

    def test_upstream_observation_does_not_prove_detection_latency(self):
        a={**self.article,'observed_at':'2025-03-06T13:20:00Z'}
        self.assertIsNone(research_clocks(a,{})['discovery_latency_seconds'])
        self.assertIsNone(research_clocks(a,{})['first_observed_at'])
        self.assertEqual(research_clocks(a,{})['upstream_observed_at'],a['observed_at'])
        a['observation_time_basis']='FIRST_RECORDED_SOURCE_OBSERVATION'
        self.assertEqual(research_clocks(a,{})['discovery_latency_seconds'],300)
        self.assertEqual(research_clocks(a,{})['first_observed_at'],a['observed_at'])

    def test_proxy_publication_cannot_be_used_for_latency(self):
        a={**self.article,'reported_time_kind':'SOURCE_DATE_PROXY','observed_at':'2025-03-06T13:20:00Z','observation_time_basis':'FIRST_RECORDED_SOURCE_OBSERVATION'}
        self.assertIsNone(research_clocks(a,{})['source_published_at'])
        self.assertIsNone(research_clocks(a,{})['discovery_latency_seconds'])

    def test_later_official_evidence_cannot_upgrade_earlier_replay(self):
        self.capture();store=IntelligenceStore(self.root/'evidence.sqlite3')
        fact=dict(official_evidence_id='test-official',canonical_event_id=self.event_id,
            fact_proposition='A precise fixture proposition only.',authority_role='FACT_AUTHORITY',evidence_status='OFFICIAL_CONFIRMED',
            first_seen_at='2026-10-12T14:00:00Z',retrieved_at='2026-10-12T14:00:00Z',document_url='https://official.example.test/document')
        store.append([dict(observation_kind='OFFICIAL_EVIDENCE',entity_id='test-official',canonical_event_id=self.event_id,payload=fact)],observed_at='2026-10-12T14:00:00Z')
        earlier=replay_event_as_of(store,self.event_id,self.clock)
        later=replay_event_as_of(store,self.event_id,'2026-10-12T14:00:00Z')
        self.assertEqual(earlier['official_evidence_observations'],[])
        self.assertEqual(earlier['reconstructed_macroview']['fact_state'],'NEWS_ONLY')
        self.assertEqual(len(later['official_evidence_observations']),1)
        self.assertEqual(later['reconstructed_macroview']['fact_state'],'PARTIAL_OFFICIAL_EVIDENCE')

    def test_updated_content_adds_version_without_silent_rewrite(self):
        self.capture();store=IntelligenceStore(self.root/'evidence.sqlite3')
        changed={**self.article,'title':'ECB keeps interest rates unchanged'}
        store.append([dict(observation_kind='NEWS_ARTICLE',entity_id=self.ref,canonical_event_id=self.event_id,payload=changed)],observed_at='2026-10-12T14:00:00Z')
        before=replay_event_as_of(store,self.event_id,self.clock)
        after=replay_event_as_of(store,self.event_id,'2026-10-12T14:00:00Z')
        self.assertEqual(before['news_observations'][0]['payload']['title'],self.article['title'])
        self.assertEqual(len(after['news_observations']),2)
        self.assertNotEqual(after['news_observations'][0]['payload_sha256'],after['news_observations'][1]['payload_sha256'])

    def test_no_capture_as_of_before_registration(self):
        self.capture();store=IntelligenceStore(self.root/'evidence.sqlite3')
        output=attach_recording_status(self.view,store,as_of='2026-10-12T12:59:59Z')
        self.assertEqual(output['items'][0]['prospective_evidence']['status'],'NOT_RECORDED')

    def test_current_content_mismatch_is_labelled_earlier_version(self):
        self.capture();store=IntelligenceStore(self.root/'evidence.sqlite3')
        changed=copy.deepcopy(self.view);changed['items'][0]['title']='Updated title'
        output=attach_recording_status(changed,store,as_of=self.clock)
        self.assertEqual(output['items'][0]['prospective_evidence']['status'],'CAPTURED_EARLIER_VERSION')

    def test_existing_ledger_recording_does_not_require_a_parallel_pilot_receipt(self):
        store=IntelligenceStore(Path(self.temp.name)/'existing.sqlite3',create=True)
        store.ingest_projection(self.view,observed_at=self.clock)
        output=attach_recording_status(self.view,store,as_of=self.clock)
        state=output['items'][0]['prospective_evidence']
        self.assertEqual(state['status'],'RECORDED_EVIDENCE_LEDGER')
        self.assertEqual(state['recorded_at'],'2026-10-12T13:00:00.000000Z')
        self.assertIsNone(state['retrieval_time'])
        self.assertEqual(state['scope'],'EXISTING_INTELLIGENCE_LEDGER')
        self.assertTrue(state['replay_available'])

    def test_latest_existing_ledger_version_is_used_after_a_pilot_capture(self):
        self.capture();store=IntelligenceStore(self.root/'evidence.sqlite3')
        changed=copy.deepcopy(self.view);changed['items'][0]['title']='ECB keeps interest rates unchanged'
        store.ingest_projection(changed,observed_at='2026-10-12T14:00:00Z')
        output=attach_recording_status(changed,store,as_of='2026-10-12T14:00:00Z')
        self.assertEqual(output['items'][0]['prospective_evidence']['status'],'RECORDED_EVIDENCE_LEDGER')
        self.assertEqual(output['items'][0]['prospective_evidence']['recorded_at'],'2026-10-12T14:00:00.000000Z')

    def test_preview_is_deterministic_non_authoritative_and_nonpersisted(self):
        left=preview_macroview(self.view,self.event_id);right=preview_macroview(self.view,self.event_id)
        self.assertEqual(left,right);self.assertTrue(left['preview_only']);self.assertFalse(left['persisted'])
        self.assertEqual(left['contract_version'],'MACROVIEW_PREVIEW_V0')

    def test_meeting_and_non_rate_documents_never_receive_ecb_analogues(self):
        titles=['ECB interest rate meeting scheduled tomorrow','ECB monetary policy outlook','ECB rate decision preview','ECB may cut interest rates','ECB amends monetary policy implementation guidelines as part of regular review','Decisions taken by the Governing Council of the ECB (in addition to decisions setting interest rates)','Philip R. Lane: Diagnostic Challenges for ECB Monetary Policy']
        for title in titles:
            with self.subTest(title=title):self.assertFalse(is_ecb_decision({**self.article,'title':title},['ECB']))

    def test_only_explicit_rate_action_qualifies(self):
        for title in ['ECB cuts interest rates by 25 basis points','ECB keeps interest rates unchanged','ECB announces interest rate decision']:
            with self.subTest(title=title):self.assertTrue(is_ecb_decision({**self.article,'title':title}))
        self.assertFalse(is_ecb_decision({**self.article,'title':'Central bank news about rates'}))

    def test_global_voices_provider_health_uses_attribution_not_author_suffix(self):
        view=copy.deepcopy(self.view)
        view['items'][0]['news_source']={'name':'Global Voices · Writer','url':'https://globalvoices.org/story'}
        view['items'][0]['title']='Trade agreements affect tariffs'
        view['discovery_sources']={'Global Voices':{'status':'LIVE','last_attempt_at':'2026-10-12T12:00:00Z'}}
        bridge=project(view,research_library={'cases':[]})['cards'][self.ref]['event_triage']
        self.assertEqual(bridge['latest_provider_check_at'],'2026-10-12T12:00:00Z')
        self.assertEqual(bridge['latest_provider_status'],'LIVE')

    def test_missing_market_observation_remains_unavailable_with_history(self):
        bridge=project(self.view,research_library={'cases':[dict(status='AVAILABLE',receipt={'x':1},research_case_id='case')]})['cards'][self.ref]['event_triage']
        self.assertEqual(bridge['current_market_observation_status'],'MARKET_OBSERVATION_NOT_AVAILABLE')
        self.assertEqual(bridge['research_case_ids'],['case'])

    def test_history_does_not_enter_recent_news_counts(self):
        result=project(self.view,research_library={'cases':[dict(status='AVAILABLE',receipt={'x':1},research_case_id='case')]})
        self.assertEqual(result['eligible_article_count'],0)
        self.assertEqual(len(result['cards']),1)

    def test_ambiguous_identity_and_fake_timestamp_rejected_before_capture(self):
        v=copy.deepcopy(self.view);v['events'][0]['event_id']='canonical-event-v0-'+'0'*64
        data=json.dumps(v).encode();receipt={**self.retrieval,'sha256':hashlib.sha256(data).hexdigest()}
        with self.assertRaisesRegex(StoreError,'IDENTITY_MISMATCH'):
            capture_snapshot(data,receipt,[self.ref],self.root)
        self.assertFalse(self.root.exists())

if __name__=='__main__':unittest.main()
