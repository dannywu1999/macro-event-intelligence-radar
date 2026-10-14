"""Synthetic failure fixtures only; real provider evidence is a separate pilot."""
import copy, json, os, tempfile, unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
from urllib.error import HTTPError
from tools.stage1b_historical_campaign import radar_news_prospective as p
from tools.stage1b_historical_campaign.radar_reality_replay import replay_event_as_of

def rss(title='ECB cuts interest rates by 25 basis points',date='Tue, 13 Oct 2026 10:00:00 GMT',url='https://www.ecb.europa.eu/press/synthetic-test.html'):
 return ('<rss><channel><item><title>'+title+'</title><link>'+url.replace('&','&amp;')+'</link><pubDate>'+date+'</pubDate></item></channel></rss>').encode()

class Clock:
 def __init__(self):self.value=datetime(2026,10,13,10,0,10,tzinfo=timezone.utc)
 def __call__(self):
  self.value+=timedelta(microseconds=1)
  return self.value.isoformat().replace('+00:00','Z')
 def advance(self):self.value+=timedelta(seconds=1801)

class Prospective(unittest.TestCase):
 def setUp(self):
  base=Path(os.environ['V47_TEST_ROOT']);base.mkdir(parents=True,exist_ok=True)
  self.tmp=tempfile.TemporaryDirectory(dir=base);self.root=Path(self.tmp.name)/'pilot';self.clock=Clock();self.calls=0
  self.raw=rss();self.error=None
  def fetch(provider):
   self.calls+=1
   if self.error:raise self.error
   return self.raw
  self.fetch=fetch
  self.runner=p.ProspectiveRunner(self.root,providers=('ECB Press',),initialize=True,clock=self.clock,fetcher=fetch)
 def tearDown(self):self.tmp.cleanup()
 def rows(self):return p.ledger_rows(self.runner.store)
 def news(self):return [r for r in self.rows() if r['observation_kind']=='NEWS_ARTICLE']
 def again(self):
  self.clock.advance();return self.runner.run()
 def view(self):
  rows=self.rows();s=p.state_from_rows(rows);items=[copy.deepcopy(r['payload']) for r in s['articles'].values()]
  return dict(items=items,**p.build_canonical_events(items))
 def test_repeat_keeps_first_and_single_content_version(self):
  self.runner.run();first=self.news()[0];self.again()
  self.assertEqual(len(self.news()),1)
  view=p.attach_detection(self.view(),self.runner.store)
  d=view['items'][0]['detection_evidence']
  self.assertEqual(d['first_observed_at'],first['payload']['observed_at'])
  self.assertGreater(d['last_seen_at'],d['first_observed_at'])
  self.assertEqual(d['status'],'PREVIOUSLY_OBSERVED')
  self.assertEqual(len(p.state_from_rows(self.rows())['receipts']),2)
 def test_updated_content_and_return_to_old_content_are_real_versions(self):
  self.runner.run();first=self.news()[0]
  self.raw=rss('ECB raises interest rates by 25 basis points');self.again()
  self.raw=rss();self.again()
  news=self.news();self.assertEqual(len(news),3)
  self.assertEqual(news[0]['payload']['content_version_identity'],news[2]['payload']['content_version_identity'])
  self.assertEqual(news[2]['payload']['observed_at'],first['payload']['observed_at'])
  self.assertGreater(news[2]['observed_at'],news[1]['observed_at'])
 def test_restart_uses_ledger_and_honors_cadence(self):
  self.runner.run()
  other=p.ProspectiveRunner(self.root,providers=('ECB Press',),clock=self.clock,fetcher=self.fetch)
  self.assertEqual(other.run()[0]['status'],'NOT_DUE');self.assertEqual(self.calls,1)
 def test_budget_and_configuration_survive_restart(self):
  with self.assertRaises(p.StoreError):p.ProspectiveRunner(self.root,providers=('Global Voices',))
  self.runner.max_requests=1;self.runner.run();self.clock.advance()
  self.assertEqual(self.runner.run()[-1]['status'],'REQUEST_BUDGET_EXHAUSTED')
 def test_timeout_preserves_last_good_and_last_seen(self):
  self.runner.run();before=p.state_from_rows(self.rows());self.error=TimeoutError();self.again()
  after=p.state_from_rows(self.rows())
  self.assertEqual(len(self.news()),1);self.assertEqual(before['seen'],after['seen'])
  state=after['providers']['ECB Press']['payload']
  self.assertEqual(state['status'],'LAST_VALID_FALLBACK')
  self.assertEqual(state['last_success_at'],before['providers']['ECB Press']['payload']['last_success_at'])
 def test_http406_not_bypassed(self):
  self.error=HTTPError('https://www.ecb.europa.eu/',406,'test',{},None)
  self.assertEqual(self.runner.run()[0]['error'],'HTTP_406');self.assertEqual(self.calls,1)
 def test_malformed_and_empty_response_fail_without_news(self):
  for data in (b'<rss>',b''):
   self.raw=data;self.runner.run();self.clock.advance()
  self.assertEqual(self.news(),[])
 def test_valid_zero_selected_globalvoices_is_success(self):
  raw=b'<rss><channel><item><title>Community arts exhibition</title><link>https://globalvoices.org/synthetic</link><author>Example Test Author</author><pubDate>Tue, 13 Oct 2026 10:00:00 GMT</pubDate></item></channel></rss>'
  articles,diag=p.parse_source('Global Voices',raw,self.clock())
  self.assertEqual(articles,[]);self.assertEqual(diag['rejected_by_reason']['NOT_MACRO_RELEVANT'],1)
 def test_one_source_failure_does_not_block_next(self):
  root=Path(self.tmp.name)/'two'
  def fetch(source):
   if source=='Global Voices':raise TimeoutError()
   return rss()
  runner=p.ProspectiveRunner(root,providers=('Global Voices','ECB Press'),initialize=True,clock=self.clock,fetcher=fetch)
  self.assertEqual([r['status'] for r in runner.run()],['FAILED','SUCCESS'])
 def test_duplicate_os_owner_fails_before_fetch(self):
  with p.owner_lock(self.root):
   with self.assertRaises(p.StoreError):self.runner.run()
  self.assertEqual(self.calls,0)
 def test_reservation_interrupted_is_unknown_and_not_retried(self):
  checked=self.clock();a=dict(record_type='ATTEMPT',provider='ECB Press',provider_checked_at=checked,attempt_id='synthetic-reserved',outcome='RESERVED')
  self.runner.store.append([p.record('SOURCE_STATE','v47:attempt:synthetic-reserved',a)],observed_at=checked)
  self.runner.run()
  state=p.state_from_rows(self.rows())
  self.assertEqual(state['attempts']['synthetic-reserved']['payload']['outcome'],'INTERRUPTED_UNKNOWN')
  self.assertEqual(self.calls,0)
 def test_receipts_and_checkpoint_recover_after_postcommit_interruption(self):
  original=self.runner.publish_checkpoint;count=0
  def interrupted():
   nonlocal count
   count+=1
   if count==3:raise KeyboardInterrupt()
   return original()
  self.runner.publish_checkpoint=interrupted
  with self.assertRaises(KeyboardInterrupt):self.runner.run()
  self.assertEqual(len(self.news()),1)
  other=p.ProspectiveRunner(self.root,providers=('ECB Press',),clock=self.clock,fetcher=self.fetch);other.run()
  self.assertEqual(len(list((self.root/'receipts').glob('*.json'))),1)
 def test_corrupt_receipt_fails_closed(self):
  self.runner.run();path=next((self.root/'receipts').glob('*.json'));path.write_bytes(b'bad')
  with self.assertRaises(p.StoreError):self.runner.run()
  self.assertEqual(self.calls,1)
 def test_missing_storage_does_not_create_or_fetch(self):
  with self.assertRaises(p.StoreError):p.ProspectiveRunner(Path(self.tmp.name)/'missing',providers=('ECB Press',),fetcher=self.fetch)
  self.assertEqual(self.calls,0)
 def test_no_initialize_overwrite(self):
  with self.assertRaises(p.StoreError):p.ProspectiveRunner(self.root,initialize=True)
 def test_ephemeral_temp_rejected(self):
  with self.assertRaises(p.StoreError):p.ProspectiveRunner(Path(tempfile.gettempdir())/'v47-synthetic-test')
 def test_url_tracking_fragment_and_semantic_parameters(self):
  a='https://www.ecb.europa.eu/a?utm_source=x&kind=decision#part';b='https://www.ecb.europa.eu/a?kind=decision'
  self.assertEqual(p.article_identity(a),p.article_identity(b))
  self.assertNotEqual(p.article_identity(b),p.article_identity('https://www.ecb.europa.eu/a?kind=speech'))
 def test_punctuation_does_not_change_article_identity(self):
  first=p.parse_source('ECB Press',rss("ECB’s policy outlook"),self.clock())[0][0]
  second=p.parse_source('ECB Press',rss("ECB's policy outlook"),self.clock())[0][0]
  self.assertEqual(first['article_identity'],second['article_identity'])
  self.assertEqual(first['content_version_identity'],second['content_version_identity'])
 def test_out_of_order_inputs_have_same_events(self):
  a=p.parse_source('ECB Press',rss(),self.clock())[0][0]
  b={**a,'article_reference':'https://globalvoices.org/synthetic','news_source':{'name':'Global Voices · Test','url':'https://globalvoices.org/synthetic'}}
  self.assertEqual(p.build_canonical_events([a,b]),p.build_canonical_events([b,a]))
 def test_similar_speeches_do_not_merge(self):
  a=p.parse_source('ECB Press',rss('ECB monetary policy speech'),self.clock())[0][0]
  b={**a,'article_reference':'https://www.ecb.europa.eu/other-speech','title':'ECB monetary policy follow-up speech'}
  self.assertEqual(len(p.build_canonical_events([a,b])['events']),2)
 def test_precision_and_future_times_do_not_fake_latency(self):
  self.assertEqual(p.source_time('2026-10-13'),('2026-10-13','DATE_ONLY'))
  self.assertEqual(p.source_time('Tue, 13 Oct 2026 10:00 GMT')[1],'MINUTE')
  self.raw=rss(date='Tue, 13 Oct 2026 10:00 GMT');self.runner.run()
  d=p.attach_detection(self.view(),self.runner.store)['items'][0]['detection_evidence']
  self.assertIsNone(d['source_to_observation_delay_seconds'])
 def test_date_only_never_enters_breaking_count(self):
  self.raw=rss(date='2026-10-13');self.runner.run()
  a=self.news()[0]['payload'];self.assertIsNone(a['reported_at']);self.assertEqual(a['source_timestamp_precision'],'DATE_ONLY')
  self.assertEqual(p.triage(a,None,self.clock())['source_freshness'],'UNKNOWN')
 def test_before_capture_empty_and_after_capture_available(self):
  self.runner.run();n=self.news()[0];event=n['canonical_event_id']
  before=(p.timestamp(n['observed_at'])-timedelta(microseconds=1)).isoformat()
  self.assertEqual(p.research_as_of(self.runner.store,event,before)['status'],'NO_OBSERVATIONS')
  after=p.research_as_of(self.runner.store,event,n['observed_at'])
  self.assertEqual(after['status'],'AVAILABLE');self.assertEqual(len(after['news']),1)
  self.assertEqual(after['market_observation'],'MARKET_OBSERVATION_NOT_AVAILABLE')
  self.assertEqual(self.runner.store.freezes(event),[])
 def test_official_evidence_added_later_is_not_visible_earlier(self):
  self.runner.run();n=self.news()[0];eid=n['canonical_event_id'];first=n['observed_at']
  self.clock.advance();added=self.clock()
  fact=dict(official_evidence_id='synthetic-fact',canonical_event_id=eid,authority_role='FACT_AUTHORITY',evidence_status='OFFICIAL_CONFIRMED',
   fact_proposition='SYNTHETIC TEST proposition only',document_url='https://www.ecb.europa.eu/synthetic-official',published_at=first)
  self.runner.store.append([p.record('OFFICIAL_EVIDENCE','synthetic-fact',fact,eid,first)],observed_at=added)
  self.assertEqual(p.research_as_of(self.runner.store,eid,first)['official_propositions'],[])
  self.assertEqual(len(p.research_as_of(self.runner.store,eid,added)['official_propositions']),1)
 def test_stale_important_article_not_high_priority(self):
  a={'title':'ECB cuts interest rates by 25 basis points','reported_at':'2025-03-06T10:00:00Z','news_source':{'url':'https://www.ecb.europa.eu/a'}}
  d=p.triage(a,'id',self.clock(),{'first_observed_proven':True})
  self.assertEqual(d['event_importance'],'HIGH');self.assertEqual(d['priority'],'STALE_SOURCE_ARTICLE')
 def test_unknown_first_seen_cannot_be_high_priority(self):
  a={'title':'ECB cuts interest rates by 25 basis points','reported_at':'2026-10-13T10:00:00Z','news_source':{'url':'https://www.ecb.europa.eu/a'}}
  self.assertFalse(p.triage(a,'id',self.clock(),None)['high_priority_eligible'])
 def test_without_storage_does_not_claim_capture(self):
  v=p.attach_detection({'items':[{'article_reference':'https://www.ecb.europa.eu/a','title':'ECB policy','news_source':{'url':'https://www.ecb.europa.eu/a'}}],'events':[]})
  self.assertEqual(v['items'][0]['detection_evidence']['status'],'FIRST_SEEN_NOT_PROVEN')
 def test_conflicting_same_url_is_not_silently_selected(self):
  raw=b'<rss><channel><item><title>ECB policy speech</title><link>https://www.ecb.europa.eu/a</link></item><item><title>ECB cuts interest rates by 25 basis points</title><link>https://www.ecb.europa.eu/a</link></item></channel></rss>'
  with self.assertRaises(p.StoreError):p.parse_source('ECB Press',raw,self.clock())
 def test_unrecorded_updated_title_not_alert_eligible(self):
  a={'title':'ECB cuts interest rates by 25 basis points','reported_at':'2026-10-13T10:00:00Z','news_source':{'url':'https://www.ecb.europa.eu/a'}}
  self.assertFalse(p.triage(a,'event',self.clock(),{'first_observed_proven':True,'status':'CAPTURED_EARLIER_VERSION'})['high_priority_eligible'])
 def test_asof_http_route_is_readonly_and_validates_query(self):
  import threading,http.client
  from unittest.mock import patch
  from tools.stage1b_historical_campaign import radar_web_server as web
  self.runner.run();n=self.news()[0];event=n['canonical_event_id']
  with patch.dict(os.environ,{'RADAR_INTELLIGENCE_DB':str(self.root/'evidence.sqlite3')}):
   with patch.object(web,'HOST','127.0.0.1'),patch.object(web,'PORT',0):server=web.bind_server()
   thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
   try:
    conn=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5)
    conn.request('GET','/api/app/research?event_id='+event+'&as_of='+n['observed_at']);response=conn.getresponse()
    self.assertEqual(response.status,200);self.assertEqual(json.loads(response.read())['status'],'AVAILABLE')
    conn.request('GET','/api/app/research?event_id=bad&as_of=bad');response=conn.getresponse();self.assertEqual(response.status,400);response.read()
    conn.request('POST','/api/app/research');response=conn.getresponse();self.assertEqual(response.status,405);response.read();conn.close()
   finally:server.shutdown();server.server_close();thread.join(timeout=5)
 def test_corrupted_store_never_falls_back_to_claimed_proof(self):
  self.runner.run()
  original=self.runner.store.decode
  self.runner.store.decode=lambda row:(_ for _ in ()).throw(p.StoreError('OBSERVATION_INTEGRITY_FAILED'))
  with self.assertRaises(p.StoreError):p.attach_detection(self.view(),self.runner.store)
  self.runner.store.decode=original
 def test_semantic_repeated_query_order_remains_distinct(self):
  self.assertNotEqual(p.article_identity('https://www.ecb.europa.eu/a?part=1&part=2'),p.article_identity('https://www.ecb.europa.eu/a?part=2&part=1'))
 def test_write_failure_prevents_external_request(self):
  self.runner.store.append=lambda *args,**kwargs:(_ for _ in ()).throw(p.StoreError('STORE_WRITE_UNAVAILABLE'))
  with self.assertRaises(p.StoreError):self.runner.run()
  self.assertEqual(self.calls,0)

if __name__=='__main__':unittest.main()
