"""Offline A5.4 fixtures, real product functions and localhost HTTP only."""
import csv
from email.message import Message
import hashlib
import http.client
import json
import os
from pathlib import Path
import ssl
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.stage1b_historical_campaign import eia_live_ingestion as eia
from tools.stage1b_historical_campaign import ecb_live_ingestion as ecb
from tools.stage1b_historical_campaign import live_source_ingestion as sources
from tools.stage1b_historical_campaign import global_event_radar_read_adapter as radar
from tools.stage1b_historical_campaign import radar_web_server as app
ROOT=Path(__file__).resolve().parents[1]
BUNDLE=ROOT/'demo/radar_public'
EIA_RSS=(ROOT/'tests/fixtures/eia_live_rss.xml').read_bytes()
ECB_RSS=(ROOT/'tests/fixtures/ecb_live_rss.xml').read_bytes()


class DiscoverySourceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='discovery-offline-')
        self.eia_fetch,self.ecb_fetch=Mock(return_value=EIA_RSS),Mock(return_value=ECB_RSS)
        self.eia=eia.EiaIngestion(runtime_root=self.temp.name,fetcher=self.eia_fetch)
        self.ecb=ecb.EcbIngestion(runtime_root=self.temp.name,fetcher=self.ecb_fetch)
        self.engine=sources.DiscoveryIngestion([self.eia,self.ecb],bundle=BUNDLE,runtime_root=self.temp.name)
        self.paths=radar.EvidencePaths(news=BUNDLE/'news',official=BUNDLE/'official-packet.json')
        self.before={name:hashlib.sha256((BUNDLE/name).read_bytes()).hexdigest() for name in
                     ['news/rss_headlines_eia_snapshot.csv','official-packet.json','metadata.json']}
        self.baseline=radar.build_radar_view(self.paths)
    def tearDown(self):
        self.engine.close()
        self.assertEqual(self.before,{name:hashlib.sha256((BUNDLE/name).read_bytes()).hexdigest() for name in self.before})
        self.temp.cleanup()
    def view(self):return self.engine.read_view(radar,self.paths)
    def test_static_default_disabled_without_any_fetch_or_store_creation(self):
        env={k:v for k,v in os.environ.items() if not k.startswith('GLOBAL_EVENT_RADAR_') and k not in ('RADAR_LIVE_EIA','RADAR_LIVE_ECB')}
        env.update(RADAR_DATA_ROOT=str(BUNDLE),GLOBAL_EVENT_RADAR_NEWS_PATH='news',GLOBAL_EVENT_RADAR_OFFICIAL_PATH='official-packet.json')
        with patch.dict(os.environ,env,clear=True),patch.object(eia,'fetch_eia') as fetch1,patch.object(ecb,'fetch_ecb') as fetch2,patch.object(sources.tempfile,'mkdtemp') as mktemp:
            view=app.feed_view()
        self.assertFalse(view['discovery_sources'][ecb.SOURCE]['enabled'])
        self.assertEqual(view['discovery_sources'][ecb.SOURCE]['status'],'DISABLED')
        fetch1.assert_not_called();fetch2.assert_not_called();mktemp.assert_not_called()
    def test_startup_separate_statuses_and_no_fetch_until_refresh(self):
        view=self.view()
        self.assertEqual(view['news_item_count'],5)
        self.assertEqual([state['status'] for state in view['discovery_sources'].values()],['STARTING','STARTING'])
        self.eia_fetch.assert_not_called();self.ecb_fetch.assert_not_called()
        self.assertEqual(view['live_ingestion']['source'],eia.SOURCE)
    def test_combined_fixture_same_normal_contract_and_counts(self):
        self.assertTrue(self.engine.refresh())
        view=self.view()
        self.assertEqual(view['news_item_count'],10)
        self.assertEqual(view['distinct_event_count'],10)
        self.assertEqual(view['live_ingestion']['article_count'],7)
        self.assertEqual(view['discovery_sources'][ecb.SOURCE]['article_count'],3)
        with self.engine.news_path.open(newline='',encoding='utf-8') as file:
            self.assertEqual(tuple(csv.DictReader(file).fieldnames),eia.FIELDS)
    def test_repeat_refresh_deduplicates_and_preserves_first_observation(self):
        self.engine.refresh();old=self.view()['items'];old_ecb=dict(self.ecb.rows)
        self.engine.refresh()
        self.assertEqual(self.view()['items'],old)
        self.assertEqual(self.ecb.rows,old_ecb)
        self.assertEqual(self.view()['discovery_sources'][ecb.SOURCE]['new_article_count'],0)
        self.assertEqual(self.eia_fetch.call_count,2);self.assertEqual(self.ecb_fetch.call_count,2)
    def test_missing_publication_stays_null_and_observed_is_independent(self):
        self.engine.refresh()
        item=next(i for i in self.view()['items'] if i['news_source']['url'].endswith('fixture002.en.html'))
        self.assertIsNone(item['reported_at']);self.assertIsNone(item['event_occurred_at'])
        self.assertIsNotNone(item['observed_at'])
        self.assertEqual(item['timeline'] if 'timeline' in item else None,None)
        row=next(r for r in self.ecb.rows.values() if r['source_url'].endswith('fixture002.en.html'))
        self.assertEqual(row['event_time'],'')
    def test_malformed_ecb_keeps_last_valid_ecb_and_eia_live(self):
        self.engine.refresh();before=dict(self.ecb.rows);success=self.ecb.status['last_success_at']
        self.ecb_fetch.return_value=b'<rss><broken>'
        self.assertFalse(self.engine.refresh())
        view=self.view()
        self.assertEqual(view['live_ingestion']['status'],'LIVE')
        self.assertEqual(view['discovery_sources'][ecb.SOURCE]['status'],'LAST_VALID_FALLBACK')
        self.assertEqual(view['discovery_sources'][ecb.SOURCE]['last_success_at'],success)
        self.assertEqual(self.ecb.rows,before);self.assertEqual(view['news_item_count'],10)
    def test_initial_ecb_failure_is_unavailable_not_eia_fallback(self):
        self.ecb_fetch.side_effect=TimeoutError()
        self.assertFalse(self.engine.refresh())
        view=self.view()
        self.assertEqual(view['live_ingestion']['status'],'LIVE')
        self.assertEqual(view['discovery_sources'][ecb.SOURCE]['status'],'UNAVAILABLE')
        self.assertEqual(view['news_item_count'],7)
        self.eia_fetch.assert_called_once();self.ecb_fetch.assert_called_once()
    def test_eia_failure_never_erases_ecb_success(self):
        self.engine.refresh();self.eia_fetch.side_effect=TimeoutError()
        self.assertFalse(self.engine.refresh())
        view=self.view()
        self.assertEqual(view['live_ingestion']['status'],'SNAPSHOT_FALLBACK')
        self.assertEqual(view['discovery_sources'][ecb.SOURCE]['status'],'LIVE')
        self.assertEqual(view['news_item_count'],10)
    def test_initial_eia_failure_still_admits_ecb(self):
        self.eia_fetch.side_effect=TimeoutError();self.engine.refresh()
        self.assertEqual(self.view()['news_item_count'],8)
        self.assertEqual(self.view()['discovery_sources'][ecb.SOURCE]['status'],'LIVE')
    def test_identical_titles_across_sources_are_separate_articles(self):
        self.engine.refresh();items=[i for i in self.view()['items'] if i['title']=='New energy supply report - Fixture discovery only.']
        self.assertEqual(len(items),2)
        self.assertEqual({i['news_source']['name'] for i in items},{eia.SOURCE,ecb.SOURCE})
        self.assertEqual(len({i['article_reference'] for i in items}),2)
    def test_ecb_news_is_never_auto_official_or_frankfurt_mapped(self):
        self.engine.refresh();view=self.view()
        events=[event for event in view['events'] if ecb.SOURCE in event['source_names']]
        self.assertEqual(len(events),3)
        for event in events:
            self.assertEqual(event['verification_status'],'UNVERIFIED_NEWS')
            self.assertEqual(event['official_evidence_count'],0)
            self.assertEqual(event['official_evidence_ids'],[])
            self.assertEqual(event['geography_status'],'UNKNOWN');self.assertIsNone(event['geography'])
            self.assertEqual([entry['entry_type'] for entry in event['timeline']],['NEWS_DISCOVERED'])
        self.assertEqual(view['mapped_event_count'],0)
    def test_pinned_eia_ids_timeline_and_proposition_unchanged(self):
        self.engine.refresh();view=self.view()
        new={event['event_id']:event for event in view['events']}
        for event in self.baseline['events']:self.assertEqual(new[event['event_id']],event)
        self.assertEqual(view['official_evidence'],self.baseline['official_evidence'])
        self.assertEqual(len(view['official_evidence']),1)
        self.assertEqual(view['official_evidence'][0]['evidence_status'],'OFFICIAL_CONFIRMED')
        self.assertIsNone(view['official_evidence'][0]['published_at'])
    def test_ecb_retention_never_evicts_pinned_eia(self):
        self.ecb.max_articles=1;self.eia.max_articles=5;self.engine.refresh()
        view=self.view()
        self.assertEqual(view['news_item_count'],6)
        self.assertTrue(set(self.eia.pinned)<=set(self.eia.rows))
        self.assertEqual(len(view['official_evidence']),1)
    def test_read_view_never_writes_and_state_contains_no_paths_or_tracebacks(self):
        self.engine.refresh();before=self.engine.news_path.read_bytes()
        with patch.object(self.engine,'_write',side_effect=AssertionError('read must not write')):
            view=self.view()
        self.assertEqual(self.engine.news_path.read_bytes(),before)
        states=json.dumps(view['discovery_sources'])
        self.assertNotIn(self.temp.name,states);self.assertNotIn('Traceback',states)
        self.assertNotIn('endpoint',states)
    def test_publish_error_keeps_previous_combined_view(self):
        before=self.engine.news_path.read_bytes()
        with patch.object(self.engine,'_write',side_effect=PermissionError('fixture')):
            self.assertFalse(self.engine.refresh(ecb.SOURCE))
        self.assertEqual(self.engine.news_path.read_bytes(),before)
        self.assertEqual(self.view()['news_item_count'],5)
        self.assertEqual(self.view()['discovery_sources'][ecb.SOURCE]['reason'],'RUNTIME_PUBLISH_FAILED')
    def test_manager_prevents_overlapping_source_refresh(self):
        entered,release=threading.Event(),threading.Event()
        self.ecb_fetch.side_effect=lambda:(entered.set(),release.wait(2),ECB_RSS)[2]
        worker=threading.Thread(target=lambda:self.engine.refresh(ecb.SOURCE));worker.start()
        try:
            self.assertTrue(entered.wait(2));self.assertFalse(self.engine.refresh(ecb.SOURCE))
            self.ecb_fetch.assert_called_once()
        finally:release.set();worker.join(3)
        self.assertFalse(worker.is_alive())
    def test_one_owned_worker_start_idempotent_and_clean_shutdown(self):
        done=threading.Event();self.ecb_fetch.side_effect=lambda:(done.set() or ECB_RSS)
        self.engine.start();worker=self.engine.thread;self.engine.start()
        self.assertIs(worker,self.engine.thread);self.assertTrue(done.wait(3))
        self.engine.close();self.assertFalse(worker.is_alive())
        self.assertIsNone(self.eia.thread);self.assertIsNone(self.ecb.thread)
        self.eia_fetch.assert_called_once();self.ecb_fetch.assert_called_once()
    def test_independent_deadlines_without_auto_retry(self):
        clock=[0];self.engine.clock=lambda:clock[0]
        self.eia.interval=300;self.ecb.interval=600
        self.engine.stop_event=Mock();self.engine.stop_event.is_set.return_value=False
        def wait(delay):clock[0]+=delay;return clock[0]>=600
        self.engine.stop_event.wait.side_effect=wait;self.engine._loop()
        self.assertEqual(self.eia_fetch.call_count,2);self.assertEqual(self.ecb_fetch.call_count,1)
        self.assertEqual(self.engine.stop_event.wait.call_args_list,[unittest.mock.call(300),unittest.mock.call(300)])
    def test_ecb_only_keeps_eia_snapshot_and_legacy_eia_disabled_status(self):
        engine=sources.DiscoveryIngestion([self.ecb],bundle=BUNDLE,runtime_root=self.temp.name)
        try:
            engine.refresh();view=engine.read_view(radar,self.paths)
            self.assertEqual(view['news_item_count'],8)
            self.assertEqual(view['live_ingestion']['status'],'DISABLED')
            self.assertEqual(view['discovery_sources'][ecb.SOURCE]['status'],'LIVE')
            self.eia_fetch.assert_not_called()
        finally:engine.close()
    def test_actual_http_combined_api_and_read_only_routes(self):
        self.engine.refresh()
        with patch.object(app,'HOST','127.0.0.1'),patch.object(app,'PORT',0):server=app.bind_server()
        server.live_ingestion=self.engine;worker=threading.Thread(target=server.serve_forever);worker.start()
        def request(path,method='GET'):
            client=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5)
            try:
                client.request(method,path);response=client.getresponse();return response.status,response.read()
            finally:client.close()
        try:
            self.assertEqual(request('/')[0],200);self.assertEqual(request('/healthz')[0],200)
            status,body=request('/api/app/radar');self.assertEqual(status,200)
            self.assertEqual(json.loads(body)['news_item_count'],10)
            for method in ('POST','PUT','PATCH','DELETE'):self.assertEqual(request('/api/app/radar',method)[0],405)
            self.assertEqual(request('/api/app/refresh')[0],404)
        finally:server.shutdown();worker.join(5);server.server_close()
        self.assertFalse(worker.is_alive())
    def test_canonical_ecb_optin_launch_uses_one_coordinator_and_closes_it(self):
        done=threading.Event();self.ecb_fetch.side_effect=lambda:(done.set() or ECB_RSS)
        with patch.object(app,'HOST','127.0.0.1'),patch.object(app,'PORT',0):server=app.bind_server()
        errors=[]
        def run():
            try:app.serve()
            except BaseException as error:errors.append(error)
        with patch.dict(os.environ,{'RADAR_LIVE_EIA':'1','RADAR_LIVE_ECB':'1'}),patch.object(app,'bind_server',return_value=server),patch.object(sources.DiscoveryIngestion,'from_environment',return_value=self.engine) as factory:
            worker=threading.Thread(target=run);worker.start()
            try:
                self.assertTrue(done.wait(3));factory.assert_called_once()
                self.assertIs(server.live_ingestion,self.engine)
                self.assertIsNone(self.eia.thread);self.assertIsNone(self.ecb.thread)
            finally:server.shutdown();worker.join(5);self.engine.close()
        self.assertEqual(errors,[]);self.assertFalse(worker.is_alive())
        self.assertFalse(self.engine.thread.is_alive())
    def test_environment_optins_are_independent_and_factory_never_fetches(self):
        with patch.dict(os.environ,{'RADAR_LIVE_EIA':'0','RADAR_LIVE_ECB':'1','RADAR_RUNTIME_ROOT':self.temp.name}),patch.object(eia,'fetch_eia') as first,patch.object(ecb,'fetch_ecb',return_value=ECB_RSS) as second:
            engine=sources.DiscoveryIngestion.from_environment()
            try:
                self.assertEqual(set(engine.sources),{ecb.SOURCE})
                first.assert_not_called();second.assert_not_called()  # factory itself does not acquire
                self.assertTrue(engine.request_triggered)
                self.assertEqual(engine.read_view(radar,self.paths)['news_item_count'],8)
                first.assert_not_called();second.assert_called_once()
                self.assertIsNone(engine.thread)
            finally:engine.close()


class EcbContractTests(unittest.TestCase):
    def test_endpoint_name_exactly_match_existing_a1_profile_when_available(self):
        profile=ROOT/'event_sources/a1_rss_sources.json'
        if profile.is_file():
            source=next(s for s in json.loads(profile.read_text()) if s['name']==ecb.SOURCE)
            self.assertEqual(source['url'],ecb.ENDPOINT)
        self.assertEqual(ecb.SOURCE,'ECB Press')
        self.assertEqual(ecb.ENDPOINT,'https://www.ecb.europa.eu/rss/press.html')
    def test_invalid_source_urls_and_missing_publications_are_not_repaired(self):
        for url in ['http://www.ecb.europa.eu/a','https://ecb.europa.eu/a','https://www.ecb.europa.eu.evil/a',
                    'https://user@www.ecb.europa.eu/a','https://www.ecb.europa.eu:444/a','javascript:bad()']:
            self.assertFalse(ecb.ecb_url(url))
        rows=ecb.parse_rss(ECB_RSS,'2026-10-07T00:00:00Z')
        self.assertEqual(len(rows),3)
        self.assertTrue(all(r['source_name']==ecb.SOURCE for r in rows))
        self.assertTrue(all(r['observed_time']=='2026-10-07T00:00:00Z' for r in rows))
    def test_invalid_feeds_are_fail_closed_no_fake_rows(self):
        for data in (b'',b'<rss/>',b'<html/>',b'<rss><channel/></rss>',b'<rss><',b'<!DOCTYPE rss><rss><channel/></rss>',b'x'*(ecb.MAX_BYTES+1)):
            with self.assertRaises(eia.IngestionError):ecb.parse_rss(data,'2026-10-07T00:00:00Z')
    def test_one_verified_transport_no_redirect_or_retry(self):
        response=Mock(status=200);response.geturl.return_value=ecb.ENDPOINT
        headers=Message();headers['Content-Type']='application/rss+xml';response.headers=headers
        response.read.return_value=ECB_RSS;response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False)
        opener=Mock();opener.open.return_value=response
        with patch.object(ecb,'build_opener',return_value=opener),patch.object(ecb.ssl,'create_default_context',wraps=ssl.create_default_context) as tls:
            self.assertEqual(ecb.fetch_ecb(),ECB_RSS)
        opener.open.assert_called_once();tls.assert_called_once()
        self.assertEqual(opener.open.call_args.kwargs['timeout'],10)
        response.read.assert_called_once_with(ecb.MAX_BYTES+1)
        self.assertEqual(opener.open.call_args.args[0].full_url,ecb.ENDPOINT)
        with self.assertRaises(eia.IngestionError):ecb.NoRedirect().redirect_request(None,None,302,'redirect',{},ecb.ENDPOINT)
    def test_wrong_response_host_content_type_size_or_http_are_rejected(self):
        for url,content,status,data in [('https://other.example/feed','application/rss+xml',200,ECB_RSS),
            (ecb.ENDPOINT,'text/html',200,ECB_RSS),(ecb.ENDPOINT,'text/xml',503,ECB_RSS),
            (ecb.ENDPOINT,'text/xml',200,b'x'*(ecb.MAX_BYTES+1))]:
            response=Mock(status=status);response.geturl.return_value=url;response.headers=Message();response.headers['Content-Type']=content
            response.read.return_value=data;response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False)
            opener=Mock();opener.open.return_value=response
            with patch.object(ecb,'build_opener',return_value=opener),self.assertRaises(eia.IngestionError):ecb.fetch_ecb()
            opener.open.assert_called_once()
    def test_environment_bounds_and_snapshot_write_protection(self):
        for env in ({'RADAR_ECB_REFRESH_SECONDS':'299'},{'RADAR_ECB_MAX_ARTICLES':'0'},{'RADAR_ECB_MAX_ARTICLES':'oops'}):
            with patch.dict(os.environ,env),self.assertRaises(eia.IngestionError):ecb.EcbIngestion.from_environment()
        with self.assertRaises(eia.IngestionError):ecb.EcbIngestion(runtime_root=BUNDLE)


if __name__=='__main__':unittest.main()
