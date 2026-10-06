"""Explicit presentation geography only. TEMP metadata; no geocoder/network."""
import copy
import hashlib
import http.client
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.stage1b_historical_campaign import global_event_radar_read_adapter as radar
from tools.stage1b_historical_campaign.eia_live_ingestion import EiaIngestion
from tools.stage1b_historical_campaign import radar_web_server
ROOT=Path(__file__).resolve().parents[1]
BUNDLE=ROOT/'demo/radar_public'

def point(**changes):
    # These coordinates are explicitly synthetic test input, never public demo facts.
    return {'place_name':'Synthetic test point (not a real event location)','country_code':None,
            'latitude':10,'longitude':20,'evidence_type':'CURATED_PRESENTATION',
            'evidence_reference':'https://example.test/curator-fixture',**changes}

def metadata(mapping):return {'schema':'EVENT_GEOGRAPHY_METADATA_V1','presentation_only':True,'events':mapping}

def event(identity='event-a'):
    return {'event_id':identity,'event_title':'A report mentions U.S. oil and Taiwan','verification_status':'UNVERIFIED_NEWS',
            'official_evidence_count':0,'timeline':[{'timeline_entry_id':'immutable-timeline-entry'}]}

class GeographyProjectionTests(unittest.TestCase):
    def project(self,events=None,data=None):return radar.build_event_geographies(events or [event()],data)
    def test_known_point_comes_only_from_explicit_metadata(self):
        view=self.project(data=metadata({'event-a':[point()]}));e=view['events'][0]
        self.assertEqual(e['geography_status'],'KNOWN');self.assertEqual(view['mapped_event_count'],1)
        self.assertEqual(e['geography'][0]['latitude'],10)
        self.assertEqual(e['geography'][0]['longitude'],20)
        self.assertIsNone(e['geography'][0]['country_code'])
        self.assertEqual(e['geography'][0]['evidence_type'],'CURATED_PRESENTATION')
    def test_no_title_country_publisher_or_instrument_inference(self):
        e=event();e.update(source_names=['U.S. Energy Information Administration'],instrument='US equities')
        result=self.project(events=[e])
        self.assertEqual(result['events'][0]['geography_status'],'UNKNOWN')
        self.assertIsNone(result['events'][0]['geography'])
        self.assertEqual((result['mapped_event_count'],result['unmapped_event_count']),(0,1))
    def test_unknown_event_id_never_attaches_by_title(self):
        result=self.project(data=metadata({'other-event':[point()]}))
        self.assertIsNone(result['events'][0]['geography'])
    def test_coordinates_missing_invalid_or_boolean_are_not_repaired(self):
        for change in [{'latitude':None},{'longitude':None},{'latitude':91},{'longitude':181},
                       {'latitude':True},{'latitude':'10'},{'latitude':float('nan')},{'longitude':float('inf')},
                       {'latitude':10**1000},{'country_code':'usa'},{'evidence_reference':'file:///private'},
                       {'place_name':None},{'evidence_type':'OFFICIAL_CONFIRMED'}]:
            with self.subTest(change=change):
                view=self.project(data=metadata({'event-a':[point(**change)]}))
                self.assertEqual(view['events'][0]['geography_status'],'UNKNOWN')
                self.assertIsNone(view['events'][0]['geography'])
    def test_invalid_metadata_contract_and_nonpresentation_flag_fail_unknown(self):
        for data in [None,{},metadata({'event-a':'bad'}),{'schema':'wrong','presentation_only':True,'events':{'event-a':[point()]}},
                     {'schema':'EVENT_GEOGRAPHY_METADATA_V1','presentation_only':False,'events':{'event-a':[point()]}}]:
            self.assertEqual(self.project(data=data)['mapped_event_count'],0)
    def test_identity_is_deterministic_and_bound_to_event(self):
        data=metadata({'event-a':[point()], 'event-b':[point(latitude=10.0,longitude=20.0)]})
        result=self.project(events=[event(),event('event-b')],data=data)
        first,second=[e['geography'][0]['geography_id'] for e in result['events']]
        self.assertNotEqual(first,second)
        again=self.project(data=metadata({'event-a':[point(latitude=10.0,longitude=20.0)]}))
        self.assertEqual(first,again['events'][0]['geography'][0]['geography_id'])
    def test_multiple_events_at_one_location_do_not_overwrite(self):
        result=self.project(events=[event(),event('event-b')],data=metadata({'event-a':[point()],'event-b':[point()]}))
        self.assertEqual(result['mapped_event_count'],2)
        self.assertEqual(len(result['events']),2)
        self.assertEqual([e['geography_status'] for e in result['events']],['KNOWN','KNOWN'])
    def test_multiple_locations_duplicate_points_and_maximum_bound(self):
        data=metadata({'event-a':[point(),point(),point(latitude=-10,longitude=-20)]})
        result=self.project(data=data)
        self.assertEqual(result['mapped_event_count'],1)
        self.assertEqual(len(result['events'][0]['geography']),2)
        too_many=self.project(data=metadata({'event-a':[point()]*17}))
        self.assertEqual(too_many['mapped_event_count'],0)
    def test_geography_never_changes_event_evidence_timeline_or_membership(self):
        events=[event()];events[0].update(official_evidence_count=1,official_evidence_ids=['unchanged-evidence'],article_references=['https://example.test/article'])
        before=copy.deepcopy(events);data=metadata({'event-a':[point()]});old=copy.deepcopy(data)
        result=self.project(events=events,data=data)
        self.assertEqual(events,before);self.assertEqual(data,old)
        for key,value in events[0].items():self.assertEqual(result['events'][0][key],value)

class GeographyInputTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='radar-geography-');self.root=Path(self.temp.name)
        self.base=radar.build_radar_view(radar.EvidencePaths(news=BUNDLE/'news',official=BUNDLE/'official-packet.json'))
        self.identity=self.base['events'][0]['event_id']
    def tearDown(self):self.temp.cleanup()
    def write(self,data):
        path=self.root/'geography.json';path.write_text(json.dumps(data));return path
    def view(self,path):return radar.build_radar_view(radar.EvidencePaths(news=BUNDLE/'news',official=BUNDLE/'official-packet.json',geography=path))
    def test_actual_optional_input_is_read_only_and_additive(self):
        path=self.write(metadata({self.identity:[point()]}));before=path.read_bytes()
        view=self.view(path)
        self.assertEqual(view['mapped_event_count'],1);self.assertEqual(view['unmapped_event_count'],4)
        self.assertEqual(view['official_evidence'],self.base['official_evidence'])
        self.assertEqual(view['items'],self.base['items'])
        self.assertEqual(view['events'][0]['timeline'],self.base['events'][0]['timeline'])
        self.assertEqual(view['events'][0]['verification_status'],'UNVERIFIED_NEWS')
        self.assertEqual(view['events'][0]['official_evidence_count'],1)
        self.assertEqual(path.read_bytes(),before)
    def test_malformed_missing_or_invalid_input_keeps_feed_available_unknown(self):
        for content in ('broken json','[]','{}'):
            path=self.root/'invalid.json';path.write_text(content)
            view=self.view(path)
            self.assertEqual(view['status'],'AVAILABLE')
            self.assertEqual(view['geography_metadata_status'],'UNAVAILABLE')
            self.assertEqual(view['mapped_event_count'],0)
        self.assertEqual(self.view(self.root/'missing.json')['mapped_event_count'],0)
    def test_unset_and_empty_env_disable_input_relative_path_uses_data_root(self):
        for value in ('','geography.json'):
            with patch.dict(os.environ,{'RADAR_DATA_ROOT':str(self.root),'GLOBAL_EVENT_RADAR_GEOGRAPHY_PATH':value}):
                paths=radar.EvidencePaths.from_environment()
                self.assertEqual(paths.geography,self.root/'geography.json' if value else None)
    def test_new_live_articles_remain_unmapped_unverified_and_timeline_unchanged(self):
        rss=(ROOT/'tests/fixtures/eia_live_rss.xml').read_bytes();path=self.write(metadata({self.identity:[point()]}))
        with tempfile.TemporaryDirectory() as tmp:
            engine=EiaIngestion(runtime_root=tmp,fetcher=lambda:rss)
            try:
                engine.refresh()
                paths=radar.EvidencePaths(official=BUNDLE/'official-packet.json',geography=path)
                view=engine.read_view(radar,paths)
                self.assertEqual(view['live_ingestion']['status'],'LIVE')
                self.assertEqual(view['mapped_event_count'],1)
                self.assertTrue(all(e['geography_status']=='UNKNOWN' for e in view['events'] if e['event_id']!=self.identity))
                self.assertTrue(all(e['verification_status']=='UNVERIFIED_NEWS' for e in view['events']))
                self.assertEqual(len(view['official_evidence']),1)
                self.assertTrue(all(e['timeline'] for e in view['events']))
            finally:engine.close()
    def test_snapshot_has_no_geographical_authority_and_hashes_stay_frozen(self):
        metadata_file=json.loads((BUNDLE/'metadata.json').read_text())
        for name,sha in metadata_file['data_sha256'].items():self.assertEqual(hashlib.sha256((BUNDLE/name).read_bytes()).hexdigest(),sha)
        self.assertEqual(self.base['mapped_event_count'],0)
        self.assertEqual(self.base['unmapped_event_count'],5)
        self.assertTrue(all(e['geography'] is None for e in self.base['events']))
    def test_empty_or_unavailable_news_still_has_zero_map_counts(self):
        empty=self.root/'news.json';empty.write_text('[]')
        for path in (empty,self.root/'missing-news.json'):
            view=radar.build_radar_view(radar.EvidencePaths(news=path))
            self.assertEqual(view['mapped_event_count'],0);self.assertEqual(view['unmapped_event_count'],0)
            self.assertEqual(view['geography_contract'],'EVENT_GEOGRAPHY_V1')

    def api_view(self,path):
        env={k:v for k,v in os.environ.items() if not k.startswith('GLOBAL_EVENT_RADAR_')}
        env.update(RADAR_DATA_ROOT=str(BUNDLE),GLOBAL_EVENT_RADAR_NEWS_PATH='news',
                   GLOBAL_EVENT_RADAR_OFFICIAL_PATH='official-packet.json',GLOBAL_EVENT_RADAR_GEOGRAPHY_PATH=str(path))
        with patch.dict(os.environ,env,clear=True),patch.object(radar_web_server,'HOST','127.0.0.1'),patch.object(radar_web_server,'PORT',0):
            server=radar_web_server.bind_server();thread=threading.Thread(target=server.serve_forever)
            thread.start()
            try:
                connection=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5)
                try:
                    connection.request('GET','/api/app/radar');response=connection.getresponse()
                    self.assertEqual(response.status,200);return json.loads(response.read())
                finally:connection.close()
            finally:server.shutdown();thread.join(timeout=5);server.server_close()
    def test_actual_http_api_accepts_optional_metadata_without_source_writes(self):
        path=self.write(metadata({self.identity:[point()]}));before=path.read_bytes()
        view=self.api_view(path)
        self.assertEqual((view['mapped_event_count'],view['unmapped_event_count']),(1,4))
        self.assertEqual(view['events'][0]['event_id'],self.identity)
        self.assertEqual(view['events'][0]['timeline'],self.base['events'][0]['timeline'])
        self.assertEqual(view['official_evidence'],self.base['official_evidence'])
        self.assertEqual(path.read_bytes(),before)
    def test_actual_http_api_missing_metadata_keeps_feed_and_zero_map(self):
        view=self.api_view(self.root/'missing.json')
        self.assertEqual(len(view['events']),5)
        self.assertEqual(view['mapped_event_count'],0)
        self.assertEqual(view['geography_metadata_status'],'UNAVAILABLE')

if __name__=='__main__':unittest.main()
