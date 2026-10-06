"""Timeline V1: actual read projection, deterministic TEMP fixtures, no network."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.stage1b_historical_campaign import global_event_radar_read_adapter as radar
from tools.stage1b_historical_campaign import radar_web_server as app
from tools.stage1b_historical_campaign.eia_live_ingestion import EiaIngestion
ROOT=Path(__file__).resolve().parents[1]
BUNDLE=ROOT/'demo/radar_public'

def item(ref='https://news.example/a',reported='2026-10-05T14:00:00Z',observed='2026-10-05T15:00:00Z',kind='REPORTED_TIME'):
    return {'article_reference':ref,'title':'Source report','reported_at':reported,'reported_time_kind':kind,
            'observed_at':observed,'discovered_at':observed,'verification_status':'UNVERIFIED_NEWS',
            'news_source':{'name':'Fixture News','url':ref}}

def event(refs=None,ids=None):
    return {'event_id':'fixture-event','event_title':'Source report','article_references':refs or ['https://news.example/a'],
            'verification_status':'UNVERIFIED_NEWS','official_evidence_ids':ids or [],'first_detected_at':'2026-10-05T15:00:00Z'}

def evidence(**changes):
    return {'official_evidence_id':'official-fixture','canonical_event_id':'fixture-event','evidence_status':'OFFICIAL_CONFIRMED',
            'fact_proposition':'One supported fact','authority_name':'Fixture Authority','document_url':'https://agency.example/document',
            'published_at':None,'first_seen_at':'2026-10-06T01:00:00Z','retrieved_at':'2026-10-06T01:00:01Z',**changes}

class TimelineProjectionTests(unittest.TestCase):
    def project(self,items=None,records=None,events=None):
        return radar.build_event_timelines(items if items is not None else [item()],records or [],events or [event()])[0]
    def test_singleton_uses_reported_time_and_preserves_detection(self):
        result=self.project();entry=result['timeline'][0]
        self.assertEqual(result['timeline_count'],1)
        self.assertEqual((entry['entry_type'],entry['timestamp_role'],entry['timestamp']),('NEWS_DISCOVERED','REPORTED_AT','2026-10-05T14:00:00Z'))
        self.assertEqual(entry['observed_at'],'2026-10-05T15:00:00Z')
        self.assertEqual(result['status_summary']['verification_status'],'UNVERIFIED_NEWS')
    def test_four_explicit_articles_sort_chronologically_not_by_input_order(self):
        items=[item(ref='https://news.example/'+str(i),reported=f'2026-10-05T{10+i}:00:00Z') for i in range(4)]
        result=self.project(items=list(reversed(items)),events=[event([i['article_reference'] for i in items])])
        self.assertEqual([e['article_reference'] for e in result['timeline']],[i['article_reference'] for i in items])
        self.assertEqual(result['status_summary']['news_article_count'],4)
    def test_news_proxy_and_missing_reported_time_use_labeled_observation(self):
        for data in [item(kind='SOURCE_DATE_PROXY'),item(reported=None),item(reported='bad'),item(reported='2026-10-05T14:00:00')]:
            with self.subTest(data=data):
                entry=self.project(items=[data])['timeline'][0]
                self.assertEqual((entry['timestamp'],entry['timestamp_role']),(data['observed_at'],'OBSERVED_AT'))
    def test_unknown_time_is_null_and_after_known_entries(self):
        items=[item(),item(ref='https://news.example/b',reported=None,observed=None)]
        result=self.project(items=items,events=[event([i['article_reference'] for i in items])])
        self.assertEqual(result['timeline'][-1]['timestamp'],None)
        self.assertEqual(result['timeline'][-1]['timestamp_role'],'UNKNOWN')
    def test_official_null_publication_uses_first_seen_never_publication(self):
        result=self.project(records=[evidence()],events=[event(ids=['official-fixture'])])
        entry=result['timeline'][1]
        self.assertEqual(entry['timestamp_role'],'EVIDENCE_FIRST_SEEN_AT')
        self.assertEqual(entry['timestamp'],'2026-10-06T01:00:00Z')
        self.assertIsNone(entry['published_at'])
        self.assertEqual(result['status_summary'],{'verification_status':'UNVERIFIED_NEWS','news_article_count':1,'official_evidence_count':1})
    def test_official_valid_publication_and_retrieval_have_distinct_roles(self):
        for record,role in [(evidence(published_at='2026-10-05T16:00:00Z'),'EVIDENCE_PUBLISHED_AT'),
                            (evidence(first_seen_at=None),'EVIDENCE_RETRIEVED_AT'),
                            (evidence(first_seen_at=None,retrieved_at=None),'UNKNOWN')]:
            result=self.project(records=[record],events=[event(ids=['official-fixture'])])
            entry=next(e for e in result['timeline'] if e['entry_type']=='OFFICIAL_EVIDENCE')
            self.assertEqual(entry['timestamp_role'],role)
            if role=='UNKNOWN':self.assertIsNone(entry['timestamp'])
    def test_exact_article_membership_ignores_similar_global_news(self):
        result=self.project(items=[item(),item(ref='https://news.example/not-a-member')])
        self.assertEqual(result['timeline_count'],1)
        missing=self.project(items=[],events=[event()])
        self.assertEqual(missing['timeline'],[])
    def test_official_link_requires_both_existing_id_and_exact_event(self):
        for records,events in [([evidence()],[event()]),([evidence(canonical_event_id='other')],[event(ids=['official-fixture'])]),
                               ([evidence(evidence_status='INCOMPLETE')],[event(ids=['official-fixture'])])]:
            result=self.project(records=records,events=events)
            self.assertEqual(result['status_summary']['official_evidence_count'],0)
    def test_duplicate_and_conflicting_records_do_not_choose_a_convenient_copy(self):
        result=self.project(items=[item(),copy.deepcopy(item())],records=[evidence(),copy.deepcopy(evidence())],events=[event(ids=['official-fixture'])])
        self.assertEqual(result['timeline_count'],2)
        result=self.project(records=[evidence(),evidence(fact_proposition='Conflicting fact')],events=[event(ids=['official-fixture'])])
        self.assertEqual(result['timeline_count'],1)
        changed=item();changed['title']='Conflicting title'
        self.assertEqual(self.project(items=[item(),changed])['timeline_count'],0)
    def test_id_and_order_are_deterministic_without_mutating_source_objects(self):
        items=[item(),item(ref='https://news.example/b')];events=[event([i['article_reference'] for i in items],['official-fixture'])];records=[evidence()]
        before=copy.deepcopy((items,records,events))
        a=self.project(items=items,records=records,events=events)
        b=self.project(items=list(reversed(items)),records=records,events=events)
        self.assertEqual(a,b);self.assertEqual((items,records,events),before)
        self.assertEqual(len({e['timeline_entry_id'] for e in a['timeline']}),3)
    def test_entry_identity_does_not_depend_on_timestamp_but_is_bound_to_event(self):
        a=self.project()['timeline'][0]['timeline_entry_id']
        b=self.project(items=[item(reported='2026-10-06T14:00:00Z')])['timeline'][0]['timeline_entry_id']
        self.assertEqual(a,b)
        other=event();other['event_id']='different-event'
        self.assertNotEqual(a,self.project(events=[other])['timeline'][0]['timeline_entry_id'])
    def test_equal_timestamps_use_stable_type_order(self):
        record=evidence(published_at='2026-10-05T14:00:00Z')
        result=self.project(records=[record],events=[event(ids=['official-fixture'])])
        self.assertEqual([e['entry_type'] for e in result['timeline']],['NEWS_DISCOVERED','OFFICIAL_EVIDENCE'])
    def test_timezone_order_uses_real_instants_preserving_exact_api_strings(self):
        items=[item(reported='2026-10-05T15:00:00+02:00'),item(ref='https://news.example/b',reported='2026-10-05T14:00:00Z')]
        result=self.project(items=items,events=[event([i['article_reference'] for i in items])])
        self.assertEqual(result['timeline'][0]['timestamp'],'2026-10-05T15:00:00+02:00')
    def test_multiple_evidence_propositions_supported_without_event_upgrade(self):
        records=[evidence(),evidence(official_evidence_id='second',fact_proposition='Second proposition')]
        result=self.project(records=records,events=[event(ids=['official-fixture','second'])])
        self.assertEqual(result['timeline_count'],3)
        self.assertEqual(result['status_summary']['official_evidence_count'],2)
        self.assertEqual(result['verification_status'],'UNVERIFIED_NEWS')

class ActualTimelineTests(unittest.TestCase):
    def test_bundled_eia_real_projection_order_and_source_bytes_unchanged(self):
        paths=radar.EvidencePaths(news=BUNDLE/'news',official=BUNDLE/'official-packet.json')
        files=[BUNDLE/'news/rss_headlines_eia_snapshot.csv',BUNDLE/'official-packet.json']
        before={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
        view=radar.build_radar_view(paths)
        linked=next(e for e in view['events'] if e['official_evidence_count'])
        self.assertEqual([e['entry_type'] for e in linked['timeline']],['NEWS_DISCOVERED','OFFICIAL_EVIDENCE'])
        self.assertEqual(linked['timeline'][1]['timestamp_role'],'EVIDENCE_FIRST_SEEN_AT')
        self.assertIsNone(linked['timeline'][1]['published_at'])
        self.assertEqual(linked['verification_status'],'UNVERIFIED_NEWS')
        self.assertTrue(all(e['timeline_count']==1 for e in view['events'] if e!=linked))
        self.assertEqual(view,radar.build_radar_view(paths))
        self.assertEqual(before,{p:hashlib.sha256(p.read_bytes()).hexdigest() for p in files})
    def test_actual_normalization_and_canonical_membership_for_multi_article_event(self):
        rows=[{'title':'Fed cuts rates by 25 basis points','article_reference':f'https://news.example/{i}',
               'source_url':f'https://news.example/{i}','source_name':'Fixture News','source_published_at':f'2026-10-05T{10+i}:00:00Z',
               'observed_time':'2026-10-05T16:00:00Z'} for i in range(4)]
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'news.json';path.write_text(json.dumps(rows))
            view=radar.build_radar_view(radar.EvidencePaths(news=path))
        self.assertEqual(len(view['events']),1)
        self.assertEqual(view['events'][0]['timeline_count'],4)
        self.assertEqual([e['timestamp'] for e in view['events'][0]['timeline']],sorted(r['source_published_at'] for r in rows))
    def test_live_and_fallback_timelines_work_without_external_request(self):
        rss=(ROOT/'tests/fixtures/eia_live_rss.xml').read_bytes()
        with tempfile.TemporaryDirectory() as tmp:
            engine=EiaIngestion(bundle=BUNDLE,runtime_root=tmp,fetcher=lambda:rss)
            try:
                self.assertTrue(engine.refresh())
                view=engine.read_view(radar,radar.EvidencePaths(official=BUNDLE/'official-packet.json'))
                self.assertEqual(view['live_ingestion']['status'],'LIVE')
                self.assertTrue(all(e['timeline'] for e in view['events']))
                self.assertTrue(all(e['verification_status']=='UNVERIFIED_NEWS' for e in view['events']))
                engine.fetcher=lambda:b'invalid';engine.refresh()
                fallback=engine.read_view(radar,radar.EvidencePaths(official=BUNDLE/'official-packet.json'))
                self.assertEqual(fallback['live_ingestion']['status'],'SNAPSHOT_FALLBACK')
                self.assertEqual(view['events'],fallback['events'])
            finally:engine.close()
    def test_radar_api_keeps_live_status_and_existing_fields(self):
        with patch.dict('os.environ',{'RADAR_DATA_ROOT':str(BUNDLE),'GLOBAL_EVENT_RADAR_NEWS_PATH':'news','GLOBAL_EVENT_RADAR_OFFICIAL_PATH':'official-packet.json','RADAR_LIVE_EIA':'0'}):
            view=app.feed_view()
        self.assertEqual(view['live_ingestion']['status'],'DISABLED')
        self.assertEqual((view['news_item_count'],view['distinct_event_count'],len(view['official_evidence'])),(5,5,1))
        self.assertTrue(all(e['timeline_contract']=='EVENT_TIMELINE_V1' for e in view['events']))

if __name__=='__main__':unittest.main()
