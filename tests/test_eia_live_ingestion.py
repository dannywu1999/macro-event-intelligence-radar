"""Bounded EIA ingestion contract; fake transport, TEMP writes, loopback only."""
import csv
import hashlib
import http.client
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
from email.message import Message
from urllib.error import HTTPError, URLError
import ssl
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.stage1b_historical_campaign import eia_live_ingestion as live
from tools.stage1b_historical_campaign import global_event_radar_read_adapter as radar
from tools.stage1b_historical_campaign import radar_web_server as app
ROOT=Path(__file__).resolve().parents[1]
RSS=(ROOT/'tests/fixtures/eia_live_rss.xml').read_bytes()
BUNDLE=ROOT/'demo/radar_public'

class IngestionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='eia-offline-')
        self.fetch=Mock(return_value=RSS)
        self.before={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in [BUNDLE/'news/rss_headlines_eia_snapshot.csv',BUNDLE/'official-packet.json']}
        self.engine=live.EiaIngestion(bundle=BUNDLE,runtime_root=self.temp.name,fetcher=self.fetch)
        self.paths=radar.EvidencePaths(official=BUNDLE/'official-packet.json')
        self.baseline=radar.build_radar_view(radar.EvidencePaths(news=BUNDLE/'news',official=BUNDLE/'official-packet.json'))
    def tearDown(self):
        self.engine.close()
        self.assertEqual(self.before,{p:hashlib.sha256(p.read_bytes()).hexdigest() for p in self.before})
        self.temp.cleanup()
    def view(self):return self.engine.read_view(radar,self.paths)
    def test_startup_serves_five_five_one_before_network(self):
        view=self.view()
        self.assertEqual((view['news_item_count'],view['distinct_event_count'],len(view['official_evidence'])),(5,5,1))
        self.assertEqual(view['live_ingestion']['status'],'STARTING')
        self.fetch.assert_not_called()
    def test_success_is_one_fetch_adds_articles_and_repeat_is_deduplicated(self):
        self.assertTrue(self.engine.refresh())
        self.assertEqual(self.fetch.call_count,1)
        view=self.view()
        self.assertEqual(view['news_item_count'],7)
        self.assertEqual(view['live_ingestion']['new_article_count'],2)
        self.assertTrue(self.engine.refresh())
        self.assertEqual(self.fetch.call_count,2)
        self.assertEqual(self.view()['live_ingestion']['new_article_count'],0)
        self.assertEqual(self.view()['news_item_count'],7)
    def test_url_fragment_or_host_case_does_not_duplicate_source_reference(self):
        self.fetch.return_value=RSS.replace(b'id=68245</link>',b'id=68245#section</link>').replace(b'https://www.eia.gov',b'https://WWW.EIA.GOV')
        self.assertTrue(self.engine.refresh())
        self.assertEqual(self.view()['news_item_count'],7)
        self.assertEqual(len(self.engine.rows),7)
        self.assertEqual(self.view()['official_evidence'],self.baseline['official_evidence'])

    def test_no_publication_fallback_no_fabricated_title_or_unexpected_host(self):
        rows=live.parse_rss(RSS,'2026-10-06T20:00:00Z')
        undated=next(row for row in rows if row['source_url'].endswith('99902'))
        self.assertEqual(undated['event_time'],'')
        self.assertTrue(all(row['headline_or_text'] for row in rows))
        self.assertFalse(any(row['source_url'].endswith('99903') for row in rows))
        self.assertTrue(all(live.eia_url(row['source_url']) for row in rows))
        for date in ('not a date','2026-10-06T12:00:00'):
            self.assertEqual(live.publication(date),'')
    def test_snapshot_and_existing_event_identity_win_over_new_title(self):
        self.engine.refresh()
        view=self.view()
        old={e['event_id']:e for e in self.baseline['events']}
        for event in view['events']:
            if event['event_id'] in old:self.assertEqual(event,old[event['event_id']])
        self.assertTrue(set(old)<={e['event_id'] for e in view['events']})
        self.assertEqual(view['official_evidence'],self.baseline['official_evidence'])
    def test_new_news_never_becomes_official_and_health_unchanged(self):
        self.engine.refresh();view=self.view()
        self.assertTrue(all(e['verification_status']=='UNVERIFIED_NEWS' for e in view['events']))
        self.assertEqual(sum(e['official_evidence_count'] for e in view['events']),1)
        self.assertIsNone(view['official_evidence'][0]['published_at'])
        self.assertEqual(view['health_status'],self.baseline['health_status'])
        old={e['event_id'] for e in self.baseline['events']}
        self.assertTrue(all(e['official_evidence_count']==0 for e in view['events'] if e['event_id'] not in old))
    def test_retention_pins_all_five_snapshot_articles_and_evidence(self):
        engine=live.EiaIngestion(bundle=BUNDLE,runtime_root=self.temp.name,max_articles=6,fetcher=self.fetch)
        try:
            self.assertTrue(engine.refresh())
            view=engine.read_view(radar,self.paths)
            self.assertEqual(view['news_item_count'],6)
            self.assertEqual(len(view['official_evidence']),1)
            self.assertTrue(set(engine.pinned)<=set(engine.rows))
        finally:engine.close()
    def test_malformed_rss_preserves_last_valid_state_and_success_time(self):
        self.engine.refresh();before=self.engine.news_path.read_bytes();success=self.view()['live_ingestion']['last_success_at']
        self.fetch.return_value=b'<rss><broken>'
        self.assertFalse(self.engine.refresh())
        self.assertEqual(self.engine.news_path.read_bytes(),before)
        status=self.view()['live_ingestion']
        self.assertEqual(status['status'],'SNAPSHOT_FALLBACK')
        self.assertEqual(status['last_success_at'],success)
        self.assertEqual(status['reason'],'MALFORMED_RSS')
    def test_http_tls_dns_timeout_failures_keep_snapshot_without_retry(self):
        for error in [HTTPError(live.ENDPOINT,503,'failure',{},None),URLError(ssl.SSLError('tls')),URLError(OSError('dns')),TimeoutError()]:
            with self.subTest(error=type(error).__name__):
                self.fetch.reset_mock();self.fetch.side_effect=error
                self.assertFalse(self.engine.refresh());self.fetch.assert_called_once()
                self.assertEqual(self.view()['news_item_count'],5)
                self.assertEqual(self.view()['live_ingestion']['status'],'SNAPSHOT_FALLBACK')
                self.assertNotIn('https://',self.view()['live_ingestion']['reason'])
    def test_invalid_empty_unsafe_and_nonrss_responses(self):
        for xml in (b'',b'<rss><channel/></rss>',b'<html/>',b'<!DOCTYPE rss [<!ENTITY x "boom">]><rss><channel/></rss>'):
            with self.subTest(xml=xml):
                self.fetch.return_value=xml
                self.assertFalse(self.engine.refresh())
                self.assertEqual(self.view()['news_item_count'],5)
    def test_exact_csv_header_and_atomic_publish_failure(self):
        self.engine.refresh()
        self.assertEqual(self.engine.news_path.read_text().splitlines()[0],','.join(live.FIELDS))
        before=self.engine.news_path.read_bytes()
        with patch.object(live.os,'replace',side_effect=PermissionError('fixture')):
            self.assertFalse(self.engine.refresh())
        self.assertEqual(self.engine.news_path.read_bytes(),before)
        self.assertEqual(len(list(self.engine.session.iterdir())),1)
    def test_one_worker_start_stop_and_no_overlapping_refresh(self):
        completed=threading.Event()
        self.fetch.side_effect=lambda:(completed.set() or RSS)
        self.engine.start();first=self.engine.thread;self.engine.start()
        self.assertIs(self.engine.thread,first)
        self.assertTrue(completed.wait(2))
        self.engine.close();self.assertFalse(first.is_alive())
        self.assertEqual(self.fetch.call_count,1)
    def test_concurrent_refresh_is_rejected(self):
        entered,release=threading.Event(),threading.Event()
        def fetch():entered.set();release.wait(2);return RSS
        self.fetch.side_effect=fetch
        worker=threading.Thread(target=self.engine.refresh)
        worker.start()
        try:
            self.assertTrue(entered.wait(2));self.assertFalse(self.engine.refresh())
            self.assertEqual(self.fetch.call_count,1)
        finally:release.set();worker.join(3)
        self.assertFalse(worker.is_alive())
    def test_periodic_loop_waits_configured_safe_interval_without_retry_storm(self):
        self.engine.interval=300
        self.engine.stop_event=Mock()
        self.engine.stop_event.is_set.return_value=False
        self.engine.stop_event.wait.side_effect=[False,True]
        self.engine._loop()
        self.assertEqual(self.fetch.call_count,2)
        self.assertEqual(self.engine.stop_event.wait.call_args_list,[unittest.mock.call(300),unittest.mock.call(300)])

    def test_configuration_bounds_and_bundle_write_rejection(self):
        for env in ({'RADAR_EIA_REFRESH_SECONDS':'299'},{'RADAR_EIA_REFRESH_SECONDS':'oops'},{'RADAR_EIA_MAX_ARTICLES':'4'}):
            with self.subTest(env=env),patch.dict(os.environ,env):
                with self.assertRaises(live.IngestionError):live.EiaIngestion.from_environment()
        with self.assertRaises(live.IngestionError):live.EiaIngestion(bundle=BUNDLE,runtime_root=BUNDLE)
    def test_transport_is_verified_one_request_and_content_type_bounded(self):
        response=Mock();response.status=200;response.geturl.return_value=live.ENDPOINT
        headers=Message();headers['Content-Type']='application/rss+xml';response.headers=headers
        response.read.return_value=RSS
        response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False)
        opener=Mock();opener.open.return_value=response
        with patch.object(live,'build_opener',return_value=opener),patch.object(live.ssl,'create_default_context',wraps=ssl.create_default_context) as tls:
            self.assertEqual(live.fetch_eia(),RSS);opener.open.assert_called_once();tls.assert_called_once()
            self.assertEqual(opener.open.call_args.kwargs['timeout'],10)
            response.read.assert_called_once_with(live.MAX_BYTES+1)
        for url,kind,data in [('https://evil.example/rss','application/rss+xml',RSS),(live.ENDPOINT,'text/html',RSS)]:
            response.geturl.return_value=url;headers['Content-Type']=kind
            # Message allows duplicates; replace the original header instead.
            response.headers=Message();response.headers['Content-Type']=kind
            with patch.object(live,'build_opener',return_value=opener):
                with self.assertRaises(live.IngestionError):live.fetch_eia()
    def test_redirect_rejected_before_second_request(self):
        with self.assertRaises(live.IngestionError):live.NoRedirect().redirect_request(None,None,302,'redirect',{},'https://other.example/')
    def test_disabled_static_feed_has_no_worker_and_no_writes(self):
        with patch.dict(os.environ,{'RADAR_DATA_ROOT':str(BUNDLE),'GLOBAL_EVENT_RADAR_NEWS_PATH':'news','GLOBAL_EVENT_RADAR_OFFICIAL_PATH':'official-packet.json','RADAR_LIVE_EIA':'0'}),patch.object(live,'fetch_eia',side_effect=AssertionError('network')):
            view=app.feed_view()
        self.assertEqual(view['live_ingestion']['status'],'DISABLED')
        self.assertEqual(view['news_item_count'],5)

class LocalDeploymentTests(unittest.TestCase):
    def test_real_http_api_health_and_snapshot_during_refresh_then_live_fallback(self):
        with tempfile.TemporaryDirectory(prefix='eia-http-') as tmp,patch.object(app,'HOST','127.0.0.1'),patch.object(app,'PORT',0),patch.dict(os.environ,{'RADAR_DEMO_MODE':'1','RADAR_DATA_ROOT':str(BUNDLE),'GLOBAL_EVENT_RADAR_NEWS_PATH':'news','GLOBAL_EVENT_RADAR_OFFICIAL_PATH':'official-packet.json'}):
            fetch_started=threading.Event();release_fetch=threading.Event()
            def fake_fetch():
                fetch_started.set();release_fetch.wait(3);return RSS
            fetch=Mock(side_effect=fake_fetch)
            engine=live.EiaIngestion(bundle=BUNDLE,runtime_root=tmp,fetcher=fetch)
            server=app.bind_server();server.live_ingestion=engine
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            def request(path,method='GET'):
                connection=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=3)
                try:
                    connection.request(method,path);response=connection.getresponse();return response.status,response.read()
                finally:connection.close()
            try:
                self.assertEqual(request('/')[0],200);self.assertEqual(request('/healthz')[0],200)
                self.assertEqual(json.loads(request('/api/app/radar')[1])['live_ingestion']['status'],'STARTING')
                engine.start();self.assertTrue(fetch_started.wait(2))
                self.assertEqual(request('/healthz')[0],200)
                self.assertEqual(json.loads(request('/api/app/radar')[1])['news_item_count'],5)
                release_fetch.set();engine.close()
                view=json.loads(request('/api/app/radar')[1]);self.assertEqual(view['news_item_count'],7)
                self.assertEqual(view['live_ingestion']['status'],'LIVE')
                fetch.side_effect=HTTPError(live.ENDPOINT,503,'failure',{},None);engine.refresh()
                view=json.loads(request('/api/app/radar')[1]);self.assertEqual(view['news_item_count'],7)
                self.assertEqual(view['live_ingestion']['status'],'SNAPSHOT_FALLBACK')
                self.assertEqual(request('/healthz')[0],200)
                for method in ('POST','PUT','PATCH','DELETE'):self.assertEqual(request('/api/app/radar',method)[0],405)
                self.assertEqual(request('/api/app/status')[0],404)
            finally:
                release_fetch.set();server.shutdown();server.server_close();thread.join(3);engine.close()
            self.assertFalse(engine.thread.is_alive());self.assertFalse(thread.is_alive())

    def test_enabled_canonical_serve_starts_one_worker_and_shutdown_closes_it(self):
        with tempfile.TemporaryDirectory(prefix='eia-serve-') as tmp,patch.object(app,'HOST','127.0.0.1'),patch.object(app,'PORT',0),patch.dict(os.environ,{'RADAR_LIVE_EIA':'1'}):
            ready=threading.Event();errors=[]
            def fetch():ready.set();return RSS
            engine=live.EiaIngestion(bundle=BUNDLE,runtime_root=tmp,fetcher=fetch)
            server=app.bind_server()
            def run():
                try:app.serve()
                except BaseException as error:errors.append(error)
            with patch.object(app,'bind_server',return_value=server),patch.object(live.EiaIngestion,'from_environment',return_value=engine) as factory:
                thread=threading.Thread(target=run,daemon=True);thread.start()
                try:
                    self.assertTrue(ready.wait(2))
                    factory.assert_called_once()
                    self.assertIs(server.live_ingestion,engine)
                finally:
                    server.shutdown();thread.join(3);engine.close()
            self.assertEqual(errors,[])
            self.assertFalse(thread.is_alive());self.assertFalse(engine.thread.is_alive())

if __name__=='__main__':unittest.main()
