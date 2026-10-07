"""Actual expectation parser/projection and lifecycle; no real provider requests."""
import copy,json,os,subprocess,tempfile,threading,unittest
from pathlib import Path
from unittest.mock import Mock,patch
from email.message import Message
from tools.stage1b_historical_campaign import radar_market_expectations as market
from tools.stage1b_historical_campaign import global_event_radar_read_adapter as radar
from tools.stage1b_historical_campaign import radar_web_server as app
ROOT=Path(__file__).resolve().parents[1];BUNDLE=ROOT/'demo/radar_public';NOW='2026-10-07T03:00:00Z'
RAW=json.loads((ROOT/'tests/fixtures/polymarket_expectations.json').read_text('utf-8'))
class ExpectationTests(unittest.TestCase):
 def setUp(self):
  self.raw=copy.deepcopy(RAW);self.records=market.parse_markets(self.raw,NOW)
  self.base=radar.build_radar_view(radar.EvidencePaths(news=BUNDLE/'news',official=BUNDLE/'official-packet.json'));self.events=self.base['events'];self.eid=self.events[0]['event_id']
 def test_list_and_specific(self):self.assertEqual(len(self.records),2);self.assertEqual(market.parse_markets(self.raw[0],NOW),[self.records[0]])
 def test_provider_values_preserved(self):self.assertEqual(self.records[0]['probabilities'],['0.6200','0.3800']);self.assertEqual(self.records[0]['probability_semantics'],'PROVIDER_OUTCOME_PRICES')
 def test_missing_values_null(self):r=self.records[1];self.assertIsNone(r['probabilities']);self.assertIsNone(r['market_close_time']);self.assertIsNone(r['market_url']);self.assertIsNone(r['canonical_event_id'])
 def test_no_invented_binary_outcomes(self):self.raw[0].pop('outcomes');r=market.parse_markets(self.raw,NOW)[0];self.assertIsNone(r['outcomes']);self.assertIsNone(r['probabilities'])
 def test_missing_question(self):self.raw[0].pop('question');self.assertIsNone(market.parse_markets(self.raw,NOW)[0]['question'])
 def test_invalid_prices_remain_unknown(self):
  for value in [True,'NaN',float('inf'),-1,'1.1',None,{},'']:
   with self.subTest(value=value):self.raw[0]['outcomePrices']=[value,'0.38'];self.assertIsNone(market.parse_markets(self.raw,NOW)[0]['probabilities'][0])
 def test_no_renormalization(self):self.raw[0]['outcomePrices']=['0.20','0.20'];self.assertEqual(market.parse_markets(self.raw,NOW)[0]['probabilities'],['0.20','0.20'])
 def test_wrong_length(self):self.raw[0]['outcomePrices']=['0.5'];self.assertIsNone(market.parse_markets(self.raw,NOW)[0]['probabilities'])
 def test_invalid_close_time(self):self.raw[0]['endDate']='2026-12-31';self.assertIsNone(market.parse_markets(self.raw,NOW)[0]['market_close_time'])
 def test_observation_must_be_explicit(self):
  for time in [None,'bad','2026-01-01']:
   with self.subTest(time=time),self.assertRaises(market.ExpectationError):market.parse_markets(self.raw,time)
 def test_identity_stable(self):self.assertEqual(market.parse_markets(self.raw,NOW),self.records)
 def test_new_snapshot_new_id(self):self.assertNotEqual(market.parse_markets(self.raw,'2026-10-07T04:00:00Z')[0]['expectation_id'],self.records[0]['expectation_id'])
 def test_changed_value_new_id(self):self.raw[0]['outcomePrices']=['0.5','0.5'];self.assertNotEqual(market.parse_markets(self.raw,NOW)[0]['expectation_id'],self.records[0]['expectation_id'])
 def test_duplicate_dedup(self):self.assertEqual(market.parse_markets(self.raw+self.raw,NOW),self.records)
 def test_conflicting_market_copies_excluded(self):r=copy.deepcopy(self.raw[0]);r['question']='conflict';self.assertEqual(len(market.parse_markets(self.raw+[r],NOW)),1)
 def test_project_duplicate_dedup(self):self.assertEqual(len(market.project_expectations(self.events,self.records+self.records)['market_expectations']),2)
 def test_unlinked_is_not_error(self):p=market.project_expectations(self.events,self.records);self.assertTrue(all(r['link_status']=='UNLINKED' and r['canonical_event_id'] is None for r in p['market_expectations']));self.assertTrue(all(not e['market_expectation_ids'] for e in p['events']))
 def test_exact_link(self):p=market.project_expectations(self.events,self.records,{self.eid:'fixture-market-01'});self.assertEqual(p['market_expectations'][0]['canonical_event_id'],self.eid);self.assertEqual(p['events'][0]['market_expectation_ids'],[self.records[0]['expectation_id']])
 def test_wrong_mapping_rejected(self):
  for links in [{'wrong':'fixture-market-01'},{self.eid:'wrong'},[],{self.eid:'fixture-market-01',self.events[1]['event_id']:'fixture-market-01'}]:
   with self.subTest(links=links):p=market.project_expectations(self.events,self.records,links);self.assertEqual(p['expectation_link_status'],'INVALID_MAPPING');self.assertTrue(all(r['link_status']=='UNLINKED' for r in p['market_expectations']))
 def test_semantics_separate(self):
  p=market.project_expectations(self.events,self.records,{self.eid:'fixture-market-01'})
  for before,after in zip(self.events,p['events']):self.assertEqual({k:v for k,v in before.items() if k!='market_expectation_ids'},{k:v for k,v in after.items() if k!='market_expectation_ids'})
  self.assertTrue(all(r['authority_role']=='EXPECTATION_SENSOR' for r in p['market_expectations']))
 def test_input_not_mutated(self):before=copy.deepcopy((self.events,self.records));market.project_expectations(self.events,self.records,{self.eid:'fixture-market-01'});self.assertEqual(before,(self.events,self.records))
 def test_malformed_response(self):
  for payload in [b'<html>unavailable</html>',{},['bad']]:
   with self.subTest(payload=payload),self.assertRaises(market.ExpectationError):market.parse_markets(payload,NOW)
 def test_failure_no_retry(self):f=Mock(side_effect=OSError('offline'));s=market.MarketExpectationSensor(fetcher=f,clock=lambda:NOW);self.assertFalse(s.refresh());self.assertEqual(f.call_count,1);self.assertEqual(s.snapshot()[1]['status'],'UNAVAILABLE');s.close()
 def test_last_valid_outage_isolated(self):f=Mock(side_effect=[self.raw,OSError('offline')]);s=market.MarketExpectationSensor(fetcher=f,clock=lambda:NOW);self.assertTrue(s.refresh());old=s.snapshot()[0];self.assertFalse(s.refresh());self.assertEqual(s.snapshot()[0],old);self.assertEqual(s.snapshot()[1]['status'],'LAST_VALID_FALLBACK');s.close()
 def test_empty_cycle(self):s=market.MarketExpectationSensor(fetcher=lambda:[],clock=lambda:NOW);self.assertTrue(s.refresh());self.assertEqual(s.snapshot()[0],[]);self.assertEqual(s.snapshot()[1]['status'],'EMPTY');s.close()
 def test_snapshot_deep_copy(self):s=market.MarketExpectationSensor(fetcher=lambda:self.raw,clock=lambda:NOW);s.refresh();r,state=s.snapshot();r[0]['question']='changed';state['status']='changed';self.assertNotEqual(s.snapshot()[0],r);s.close()
 def test_one_owned_thread(self):f=Mock(return_value=self.raw);s=market.MarketExpectationSensor(fetcher=f,clock=lambda:NOW);s.start();worker=s.thread;s.start();self.assertIs(s.thread,worker);s.close();self.assertFalse(worker.is_alive());self.assertEqual(f.call_count,1)
 def test_invalid_interval(self):
  for interval in [1,True,999999]:
   with self.assertRaises(market.ExpectationError):market.MarketExpectationSensor(interval=interval)
 def test_market_url_from_provider_event_not_market_guess(self):self.assertEqual(self.records[0]['market_url'],'https://polymarket.com/event/synthetic-fixture-event');self.raw[0].pop('events');self.assertIsNone(market.parse_markets(self.raw,NOW)[0]['market_url'])
 def test_provider_failure_does_not_suppress_news(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t)/'bad.json';p.write_text('broken','utf-8');v=radar.build_radar_view(radar.EvidencePaths(news=BUNDLE/'news',official=BUNDLE/'official-packet.json',polymarket=p));self.assertEqual(v['item_count'],5);self.assertEqual(v['status'],'AVAILABLE');self.assertEqual(v['sources']['polymarket']['status'],'UNAVAILABLE');self.assertEqual(v['market_expectations'],[])
 def test_actual_adapter_reads_snapshot_and_links_readonly(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t)/'markets.json';links=Path(t)/'links.json';p.write_text(json.dumps([{**r,'observed_at':NOW} for r in self.raw]),'utf-8');links.write_text(json.dumps({'schema':'EXACT_MARKET_LINKS_V1','event_to_market':{self.eid:'fixture-market-01'}}),'utf-8');before=(p.read_bytes(),links.read_bytes());v=radar.build_radar_view(radar.EvidencePaths(news=BUNDLE/'news',official=BUNDLE/'official-packet.json',polymarket=p,expectation_links=links));self.assertEqual(v['market_expectations'][0]['link_status'],'LINKED');self.assertEqual(len(v['official_evidence']),1);self.assertEqual(before,(p.read_bytes(),links.read_bytes()))
 def test_disabled_server_does_not_fetch(self):
  with patch.dict(os.environ,{'RADAR_DATA_ROOT':str(BUNDLE),'GLOBAL_EVENT_RADAR_NEWS_PATH':'news','GLOBAL_EVENT_RADAR_OFFICIAL_PATH':'official-packet.json','RADAR_LIVE_POLYMARKET':'0'}),patch.object(market,'fetch_gamma',side_effect=AssertionError('NETWORK_FORBIDDEN')):
   self.assertEqual(app.feed_view()['expectation_provider']['status'],'DISABLED')
 def test_live_api_read_never_refreshes(self):
  sensor=market.MarketExpectationSensor(fetcher=Mock(return_value=self.raw),clock=lambda:NOW);sensor.refresh()
  with patch.dict(os.environ,{'RADAR_DATA_ROOT':str(BUNDLE),'GLOBAL_EVENT_RADAR_NEWS_PATH':'news','GLOBAL_EVENT_RADAR_OFFICIAL_PATH':'official-packet.json'}):v=app.feed_view(expectation_sensor=sensor)
  self.assertEqual(len(v['market_expectations']),2);self.assertEqual(sensor.fetcher.call_count,1);self.assertEqual(v['official_evidence'],self.base['official_evidence']);sensor.close()
 def test_verified_transport_one_request(self):
  headers=Message();headers['Content-Type']='application/json';response=Mock();response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False);response.status=200;response.geturl.return_value=market.ENDPOINT;response.headers=headers;response.read.return_value=b'[]';opener=Mock();opener.open.return_value=response
  with patch.object(market,'build_opener',return_value=opener),patch.object(market.ssl,'create_default_context',wraps=market.ssl.create_default_context) as tls:
   self.assertEqual(market.fetch_gamma(),b'[]');tls.assert_called_once();self.assertEqual(opener.open.call_count,1);self.assertEqual(opener.open.call_args.kwargs['timeout'],10)
 def test_actual_bilingual_frontend_expectation_and_xss(self):
  view=copy.deepcopy(self.base);view.update(market.project_expectations(self.events,self.records,{self.eid:'fixture-market-01'}));view['market_expectations'][0]['question']='<img src=x onerror=alert(1)>'
  node=Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe';payload=dict(view=view,html=(ROOT/'ui/radar_public_showcase_v1.html').read_text('utf-8'),translations=(ROOT/'ui/radar_demo_translations.js').read_text('utf-8'));r=subprocess.run([str(node),str(ROOT/'tests/ui_render_harness.cjs')],input=json.dumps(payload),text=True,encoding='utf-8',capture_output=True,check=True);ui=json.loads(r.stdout)
  self.assertIn('Market Expectations',ui['en']);self.assertIn('市場預期',ui['zh']);self.assertIn('do not verify facts',ui['en']);self.assertIn('不代表事實',ui['zh']);self.assertIn('0.6200',ui['en']);self.assertIn('&lt;img',ui['en']);self.assertNotIn('<img src=x',ui['en']);self.assertTrue(ui['unchanged'])
 def test_explicit_opt_in_owns_start_and_close(self):
  sensor=Mock()
  with patch.dict(os.environ,{'RADAR_LIVE_POLYMARKET':'1','RADAR_LIVE_EIA':'0','RADAR_LIVE_ECB':'0'}),patch.object(market,'MarketExpectationSensor',return_value=sensor) as factory,patch.object(app,'PORT',0),patch.object(app.ThreadingHTTPServer,'serve_forever',side_effect=KeyboardInterrupt):app.serve()
  factory.assert_called_once_with(interval=1800);sensor.start.assert_called_once();sensor.close.assert_called_once()
 def test_disabled_serve_does_not_construct_sensor(self):
  with patch.dict(os.environ,{'RADAR_LIVE_POLYMARKET':'0','RADAR_LIVE_EIA':'0','RADAR_LIVE_ECB':'0'}),patch.object(market,'MarketExpectationSensor') as factory,patch.object(app,'PORT',0),patch.object(app.ThreadingHTTPServer,'serve_forever',side_effect=KeyboardInterrupt):app.serve()
  factory.assert_not_called()
 def test_wrong_mapping_file_isolated(self):
  with tempfile.TemporaryDirectory() as t:
   path=Path(t)/'links.json';path.write_text('bad json','utf-8');p=radar.project_market_records(self.events,self.records,path);self.assertEqual(p['expectation_link_status'],'UNAVAILABLE');self.assertEqual(len(p['events']),5);self.assertTrue(all(r['link_status']=='UNLINKED' for r in p['market_expectations']))
 def test_redirect_not_allowed(self):
  with self.assertRaises(market.ExpectationError):market.NoRedirect().redirect_request(None)
if __name__=='__main__':unittest.main()
