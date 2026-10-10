"""Actual V4 production functions with offline transport, TEMP state and served JS."""
import copy, csv, io, os, tempfile, threading, unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from email.message import Message
from tools.stage1b_historical_campaign import broad_news_ingestion as news
from tools.stage1b_historical_campaign import radar_news_freshness as freshness
from tools.stage1b_historical_campaign.live_source_ingestion import DiscoveryIngestion, FIELDS
from tools.stage1b_historical_campaign import global_event_radar_read_adapter as radar
from tools.stage1b_historical_campaign import radar_web_server as server
from test_radar_v3_intelligence import project
import test_bilingual_visual_ui as bilingual
NOW=datetime(2026,10,10,6,tzinfo=timezone.utc)
RSS=b"""<rss xmlns:dc="http://purl.org/dc/elements/1.1/"><channel><item><title>Tariffs &amp; policy</title><link>https://globalvoices.org/2026/10/10/policy/</link><pubDate>Sat, 10 Oct 2026 04:00:00 GMT</pubDate><dc:creator>Writer A</dc:creator><description>Do not republish this body</description></item></channel></rss>"""
ROOT=Path(__file__).resolve().parents[1]
BUNDLE=ROOT/'demo/radar_public'

class V4Sources(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.fetch=Mock(return_value=RSS)
  self.source=news.BroadNewsIngestion('Global Voices',runtime_root=self.temp.name,fetcher=self.fetch)
  self.clock=[100.0];self.engine=DiscoveryIngestion([self.source],bundle=BUNDLE,runtime_root=self.temp.name,clock=lambda:self.clock[0],request_triggered=True)
  self.paths=radar.EvidencePaths(official=BUNDLE/'official-packet.json')
  self.before={p:p.read_bytes() for p in BUNDLE.rglob('*') if p.is_file()}
 def tearDown(self):
  self.engine.close();self.assertEqual(self.before,{p:p.read_bytes() for p in self.before});self.temp.cleanup()
 def view(self):return self.engine.read_view(radar,self.paths)
 def test_request_triggered_ttl_no_background(self):
  self.engine.start();self.assertIsNone(self.engine.thread)
  self.view();self.view();self.assertEqual(self.fetch.call_count,1)
  self.clock[0]+=1800;self.view();self.assertEqual(self.fetch.call_count,2)
 def test_singleflight_cached_read_during_fetch(self):
  entered,release=threading.Event(),threading.Event()
  def fetch():entered.set();release.wait(3);return RSS
  self.source.fetcher=fetch
  t=threading.Thread(target=self.view);t.start();self.assertTrue(entered.wait(1))
  try:self.assertEqual(self.view()['news_item_count'],5)
  finally:release.set();t.join(3)
  self.assertFalse(t.is_alive());self.assertEqual(self.view()['news_item_count'],6)
 def test_failure_preserves_cache_no_retry(self):
  self.view();self.fetch.side_effect=HTTPError('https://globalvoices.org/feed/',429,'limited',None,None)
  self.clock[0]+=1800;v=self.view();self.assertEqual(v['news_item_count'],6)
  self.assertEqual(v['discovery_sources']['Global Voices']['status'],'LAST_VALID_FALLBACK')
  self.view();self.assertEqual(self.fetch.call_count,2)
 def test_csv_schema_dedup_and_observation_retained(self):
  self.view();before=list(csv.DictReader(self.source.news_path.read_text(encoding='utf-8').splitlines()))
  self.clock[0]+=1800;self.view();after=list(csv.DictReader(self.source.news_path.read_text(encoding='utf-8').splitlines()))
  self.assertEqual(tuple(before[0]),FIELDS);self.assertEqual(before,after);self.assertEqual(len(after),1)
 def test_author_attribution_title_only_and_status(self):
  v=self.view();a=next(a for a in v['items'] if 'globalvoices.org' in a['article_reference'])
  self.assertEqual(a['title'],'Tariffs & policy');self.assertIn('Writer A',a['news_source']['name']);self.assertEqual(a['verification_status'],'UNVERIFIED_NEWS');self.assertIsNone(a['event_occurred_at'])
 def test_missing_author_not_republished(self):
  with self.assertRaises(news.IngestionError):news.parse_rss(RSS.replace(b'<dc:creator>Writer A</dc:creator>',b''),'x',source='Global Voices')
 def test_missing_publication_never_observed_fallback(self):
  rows=news.parse_rss(RSS.replace(b'<pubDate>Sat, 10 Oct 2026 04:00:00 GMT</pubDate>',b''),'2026-10-10T06:00:00Z',source='Global Voices');self.assertEqual(rows[0]['event_time'],'')
 def test_malformed_external_entities_and_wrong_host(self):
  for data in [b'<rss>',b'<!DOCTYPE rss>'+RSS,RSS.replace(b'https://globalvoices.org/',b'https://evil.example/')]:
   with self.subTest(data=data[:30]),self.assertRaises(news.IngestionError):news.parse_rss(data,'x',source='Global Voices')
 def test_guardian_requires_explicit_noncommercial_scope(self):
  with patch.dict(os.environ,{},clear=True),self.assertRaisesRegex(news.IngestionError,'NONCOMMERCIAL'):news.BroadNewsIngestion.from_environment('Guardian World')
 def test_environment_factory_request_triggered(self):
  with patch.dict(os.environ,{'RADAR_LIVE_NEWS':'1','RADAR_RUNTIME_ROOT':self.temp.name},clear=True):
   e=DiscoveryIngestion.from_environment()
   try:self.assertTrue(e.request_triggered);self.assertEqual(list(e.sources),['Global Voices'])
   finally:e.close()
 def test_new_sources_failure_isolation(self):
  bad=news.BroadNewsIngestion('Guardian World',runtime_root=self.temp.name,fetcher=Mock(return_value=b'<broken>'))
  e=DiscoveryIngestion([self.source,bad],bundle=BUNDLE,runtime_root=self.temp.name)
  try:
   self.assertFalse(e.refresh());v=e.read_view(radar,self.paths)
   self.assertEqual(v['news_item_count'],6);self.assertEqual(v['discovery_sources']['Global Voices']['status'],'LIVE');self.assertEqual(v['discovery_sources']['Guardian World']['status'],'UNAVAILABLE')
  finally:e.close()
 def test_zero_article_success_is_not_fabricated(self):
  self.fetch.return_value=b'<rss><channel/></rss>';v=self.view()
  self.assertEqual(v['news_item_count'],5);self.assertEqual(v['discovery_sources']['Global Voices']['status'],'UNAVAILABLE');self.assertIsNone(v['discovery_sources']['Global Voices']['last_success_at'])
 def test_transport_invalid_headers_host_size_rejected_without_retry(self):
  for url,kind,status,data in [('https://evil.example/feed','text/xml',200,RSS),(news.PROFILES['Global Voices'][0],'text/html',200,RSS),(news.PROFILES['Global Voices'][0],'text/xml',503,RSS),(news.PROFILES['Global Voices'][0],'text/xml',200,b'x'*(news.MAX_BYTES+1))]:
   response=Mock();response.status=status;response.geturl.return_value=url;response.headers=Message();response.headers['Content-Type']=kind;response.read.return_value=data;response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False)
   opener=Mock();opener.open.return_value=response
   with patch.object(news,'build_opener',return_value=opener),self.assertRaises(news.IngestionError):news.fetch_rss('Global Voices')
   opener.open.assert_called_once()
 def test_macro_titles_admitted_general_news_not_counted(self):
  for title in ['Trump reciprocal trade agreements threaten internet access','Subsea cables and oil pipelines','Alibaba sues Pentagon over Chinese military affiliate classification','Central bank interest rate decision','Inflation and unemployment increase','Energy supply disrupted','Presidential election results','Earthquake disrupts regional infrastructure']:
   with self.subTest(title=title):self.assertTrue(news.macro_relevant_title(title))
  for title in ['How Ecuador is fighting to keep industrial trans fats off the food shelf','The sound of resistance','When radio finds a new digital voice','Waterlily discovered in jungle','Three men convicted of murder','Company opens a new cafe','Trading off a fashion brand reputation']:
   with self.subTest(title=title):self.assertFalse(news.macro_relevant_title(title))
 def test_relevance_does_not_create_official_authority(self):
  v=self.view();self.assertTrue(all(e['verification_status']=='UNVERIFIED_NEWS' for e in v['events']));self.assertEqual(len(v['official_evidence']),1)
 def test_valid_feed_with_zero_macro_selection_is_success_not_fake_rows(self):
  self.fetch.return_value=RSS.replace(b'Tariffs &amp; policy',b'A local music performance')
  v=self.view();self.assertEqual(v['news_item_count'],5);self.assertEqual(v['discovery_sources']['Global Voices']['status'],'LIVE');self.assertEqual(v['discovery_sources']['Global Voices']['article_count'],0);self.fetch.assert_called_once()
 def test_fetch_one_bounded_verified_transport(self):
  response=Mock();response.status=200;response.geturl.return_value=news.PROFILES['Global Voices'][0];response.headers=Message();response.headers['Content-Type']='application/rss+xml';response.read.return_value=RSS
  response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False)
  opener=Mock();opener.open.return_value=response
  with patch.object(news,'build_opener',return_value=opener),patch.object(news.ssl,'create_default_context',wraps=news.ssl.create_default_context) as tls:
   self.assertEqual(news.fetch_rss('Global Voices'),RSS);tls.assert_called_once();opener.open.assert_called_once();response.read.assert_called_once_with(news.MAX_BYTES+1)

 def test_v41_geopolitical_and_policy_false_negatives(self):
  # First example is a real rejected title from the bounded BBC evaluation;
  # BBC metadata is not admitted to the public candidate without permission.
  admitted=['Ethiopia warns Eritrea it will defend itself after troops cross border',
   'Ukrainian strikes disrupt regional infrastructure', 'Houthi attacks on Saudi airport',
   'Fed holds rates', 'Powell discusses jobs report', 'Trader convicted of rigging rates',
   'Government internet shutdown during protests', 'White House announces tax policy']
  rejected=['Local workers strike at a cafe', 'Music star cancels show due to security threat',
   'Ukraine football team wins match', 'Dating advice about your salary', 'Film wins award', 'Fed up with street fashion', 'Powell stars in a new film',
   'Trader launches fashion brand', 'Internet radio celebrates local culture']
  for title in admitted:
   with self.subTest(title=title):self.assertTrue(news.macro_relevant_title(title))
  for title in rejected:
   with self.subTest(title=title):self.assertFalse(news.macro_relevant_title(title))
 def test_v41_cycle_metrics_account_for_rejections_and_duplicates(self):
  item=RSS.split(b'<channel>')[1].split(b'</channel>')[0]
  items=[item,item,item.replace(b'Tariffs &amp; policy',b'Local music performance'),
   item.replace(b'https://globalvoices.org/',b'https://evil.example/'),
   item.replace(b'<dc:creator>Writer A</dc:creator>',b''),item.replace(b'<title>Tariffs &amp; policy</title>',b'')]
  data=b'<rss xmlns:dc="http://purl.org/dc/elements/1.1/"><channel>'+b''.join(items)+b'</channel></rss>'
  rows=news.parse_rss(data,NOW.isoformat(),source='Global Voices');d=rows.diagnostics
  self.assertEqual(len(rows),1);self.assertEqual(tuple(rows[0]),FIELDS)
  self.assertEqual(d['input_item_count'],6);self.assertEqual(d['accepted_item_count'],1)
  self.assertEqual(d['rejected_by_reason'],dict(DUPLICATE_URL=1,NOT_MACRO_RELEVANT=1,UNSAFE_SOURCE_URL=1,MISSING_ATTRIBUTION=1,MISSING_TITLE=1))
  self.assertEqual(d['last_24h_selected_count'],1);self.assertEqual(d['last_48h_selected_count'],1)
  self.assertEqual(d['input_item_count'],d['accepted_item_count']+sum(d['rejected_by_reason'].values()))
 def test_v41_cycle_survives_failure_without_claiming_new_success(self):
  v=self.view();state=v['discovery_sources']['Global Voices'];cycle=copy.deepcopy(state['last_successful_cycle']);success=state['last_success_at']
  self.fetch.side_effect=TimeoutError();self.clock[0]+=1800;v=self.view();state=v['discovery_sources']['Global Voices']
  self.assertEqual(state['status'],'LAST_VALID_FALLBACK');self.assertEqual(state['reason'],'REQUEST_TIMEOUT')
  self.assertEqual(state['last_successful_cycle'],cycle);self.assertEqual(state['last_success_at'],success)
  self.assertEqual(state['new_article_count'],0);self.view();self.assertEqual(self.fetch.call_count,2)
 def test_v41_disabled_general_news_source_visible_without_acquisition(self):
  v=self.view();self.assertFalse(v['discovery_sources']['Guardian World']['enabled']);self.assertEqual(v['discovery_sources']['Guardian World']['status'],'DISABLED')
  v=server.feed_view();self.assertEqual(v['discovery_sources']['Global Voices']['status'],'DISABLED')
 def test_v41_unknown_and_future_publications_not_recent_in_metrics(self):
  for date in [b'not a date',b'Sun, 11 Oct 2026 04:00:00 GMT']:
   rows=news.parse_rss(RSS.replace(b'Sat, 10 Oct 2026 04:00:00 GMT',date),NOW.isoformat(),source='Global Voices')
   self.assertEqual(rows.diagnostics['last_24h_selected_count'],0);self.assertEqual(rows.diagnostics['last_48h_selected_count'],0)

 def test_v41_un_source_credit_notification_gate_and_default_no_fetch(self):
  with patch.dict(os.environ,{},clear=True),self.assertRaisesRegex(news.IngestionError,'CREDIT_AND_NOTIFICATION'):
   news.BroadNewsIngestion.from_environment('UN News')
  with patch.dict(os.environ,{'RADAR_LIVE_UN_NEWS':'1','RADAR_UN_NEWS_REUSE_ACKNOWLEDGED':'1','RADAR_RUNTIME_ROOT':self.temp.name},clear=True):
   e=DiscoveryIngestion.from_environment()
   try:self.assertEqual(list(e.sources),['UN News']);self.assertTrue(e.request_triggered);self.assertIsNone(e.thread)
   finally:e.close()
 def test_v41_un_news_original_url_five_columns_and_unverified(self):
  feed=RSS.replace(b'https://globalvoices.org/2026/10/10/policy/',b'https://news.un.org/feed/view/en/story/2026/10/123').replace(b'<dc:creator>Writer A</dc:creator>',b'<guid isPermaLink="true">https://news.un.org/en/story/2026/10/123</guid>')
  rows=news.parse_rss(feed,NOW.isoformat(),source='UN News');self.assertEqual(tuple(rows[0]),FIELDS);self.assertEqual(rows[0]['source_url'],'https://news.un.org/en/story/2026/10/123')
  source=news.BroadNewsIngestion('UN News',runtime_root=self.temp.name,fetcher=Mock(return_value=feed))
  e=DiscoveryIngestion([self.source,source],bundle=BUNDLE,runtime_root=self.temp.name,request_triggered=True)
  try:
   v=e.read_view(radar,self.paths);a=next(a for a in v['items'] if a['news_source']['name']=='UN News')
   self.assertEqual(a['verification_status'],'UNVERIFIED_NEWS');self.assertIsNone(a['event_occurred_at'])
   event=next(e for e in v['events'] if a['article_reference'] in e['article_references']);self.assertEqual(event['official_evidence_count'],0)
   self.assertEqual(freshness.project(v,now=NOW)['attribution'][a['article_reference']]['source'],'UN News')
  finally:e.close()
 def test_v41_un_guid_substitution_not_used(self):
  feed=RSS.replace(b'https://globalvoices.org/2026/10/10/policy/',b'https://news.un.org/feed/view/en/story/2026/10/123').replace(b'<dc:creator>Writer A</dc:creator>',b'<guid>https://news.un.org/en/story/2026/10/other</guid>')
  self.assertEqual(news.parse_rss(feed,NOW.isoformat(),source='UN News')[0]['source_url'],'https://news.un.org/feed/view/en/story/2026/10/123')
 def test_v41_no_new_endpoint_or_guardian_implicitly_enabled(self):
  with patch.dict(os.environ,{'RADAR_LIVE_NEWS':'1','RADAR_RUNTIME_ROOT':self.temp.name},clear=True):
   e=DiscoveryIngestion.from_environment()
   try:self.assertEqual(set(e.sources),{'Global Voices'});self.assertFalse(e.statuses['UN News']['enabled']);self.assertFalse(e.statuses['Guardian World']['enabled'])
   finally:e.close()

class V4Freshness(unittest.TestCase):
 def view(self):
  articles=[]
  for i,hours in enumerate([1,30,60,None,-1]):
   date=(NOW-timedelta(hours=hours)).isoformat() if hours is not None else None
   articles.append(dict(article_reference=str(i),reported_at=date,reported_time_kind='REPORTED_TIME',observed_at=NOW.isoformat(),news_source={}))
  return dict(items=articles,events=[dict(event_id='ongoing',article_references=['0','1']),dict(event_id='old',article_references=['2'])])
 def test_publication_buckets_and_ongoing_event_count(self):
  v=self.view();before=copy.deepcopy(v);f=freshness.project(v,now=NOW)
  self.assertEqual(f['last_24h_article_count'],1);self.assertEqual(f['last_48h_article_count'],2);self.assertEqual(f['last_48h_event_count'],1);self.assertEqual(f['older_article_count'],1);self.assertEqual(f['unknown_article_count'],2);self.assertEqual(v,before)
 def test_old_newly_imported_snapshot_never_recent(self):
  v=self.view();v['items']=v['items'][2:3];self.assertEqual(freshness.project(v,now=NOW)['last_24h_article_count'],0)
 def test_proxy_invalid_naive_and_missing_dates_never_recent(self):
  for value,kind in [('2026-10-10T05:00:00Z','SOURCE_DATE_PROXY'),('bad','REPORTED_TIME'),('2026-10-10T05:00:00','REPORTED_TIME'),(None,'REPORTED_TIME')]:
   v=self.view();v['items']=[dict(article_reference='x',reported_at=value,reported_time_kind=kind)];self.assertEqual(freshness.project(v,now=NOW)['last_48h_article_count'],0)
 def test_no_health_or_fetch_fabricated(self):
  f=freshness.project(self.view(),now=NOW);self.assertNotIn('health_status',f);self.assertNotIn('last_success_at',f)
 def test_source_fetch_freshness_uses_fetch_clock_not_publication(self):
  v=self.view();v['discovery_sources']={'recent':dict(last_success_at=(NOW-timedelta(seconds=10)).isoformat(),refresh_interval_seconds=300,status='LIVE'),'old':dict(last_success_at=(NOW-timedelta(seconds=301)).isoformat(),refresh_interval_seconds=300,status='LIVE'),'unknown':dict(last_success_at=None,refresh_interval_seconds=300,status='STARTING')}
  f=freshness.project(v,now=NOW)
  self.assertEqual([f['source_checks'][name]['cache_freshness'] for name in ['recent','old','unknown']],['FRESH_CACHE','STALE_CACHE','UNKNOWN']);self.assertNotIn('health_status',f)
 def test_future_not_counted(self):self.assertEqual(freshness.project(self.view(),now=NOW)['article_recency']['4'],'INVALID_FUTURE')

class V4Translation(unittest.TestCase):
 def test_actual_new_current_market_patterns(self):
  rows=[dict(market_id=i,question=q) for i,q in [('3399459','Israel x Iran ceasefire continues through October 31?'),('3399468','Israel x Iran ceasefire continues through December 31?'),('3902370','Israel x Iran ceasefire continues through November 30?')]]
  for x in project(rows):self.assertEqual(x['projection']['mode'],'VALIDATED_QUESTION_TEMPLATE');self.assertIn('以色列與伊朗',x['projection']['summary']);self.assertIn('持續到並涵蓋',x['projection']['summary']);self.assertNotIn('2026',x['projection']['summary'])
 def test_dynamic_fidelity_numeric_relation_and_no_change(self):
  rows=[dict(market_id='new',question=q) for q in ['Will the Fed increase interest rates by 50+ bps after the December 2027 meeting?','Will there be no change in Fed interest rates after the June 2028 meeting?','Will WTI Crude Oil (WTI) hit (HIGH) $123.45 in November?']]
  result=project(rows);self.assertIn('2027 年 12 月會議之後升息至少 50',result[0]['projection']['summary']);self.assertIn('維持不變',result[1]['projection']['summary']);self.assertIn('123.45',result[2]['projection']['summary'])
 def test_unsupported_semantics_dates_negation_never_template(self):
  questions=['Israel x Iran ceasefire continues before October 31?','Israel x Iran ceasefire does not continue through October 31?','Israel x Iran ceasefire continues through February 30?','Israel x Iran ceasefire continues through November 31?','Israel x Iran ceasefire continues through October 31? extra','Will the Fed increase interest rates by more than 50 bps after the December 2027 meeting?','Will the Fed increase interest rates by 50+ bps before the December 2027 meeting?','Will WTI Crude Oil (WTI) hit (LOW) $150 in October?']
  for x in project([dict(market_id='new',question=q) for q in questions]):self.assertIsNone(x['projection']['summary']);self.assertNotEqual(x['projection']['mode'],'VALIDATED_QUESTION_TEMPLATE')
 def test_drift_cannot_reuse_reviewed_translation(self):
  r=project([dict(market_id='2589810',question='Will the Fed increase interest rates by 25 bps after the November 2027 meeting?')])[0]['projection'];self.assertEqual(r['mode'],'VALIDATED_QUESTION_TEMPLATE');self.assertIn('2027 年 11 月會議之後升息 25',r['summary'])

class V4Render(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  bilingual.BilingualVisualTests.setUpClass();cls.ui=bilingual.BilingualVisualTests();cls.ui.html=bilingual.BilingualVisualTests.html;cls.ui.translations=bilingual.BilingualVisualTests.translations;cls.ui.view=bilingual.BilingualVisualTests.view
 @classmethod
 def tearDownClass(cls):bilingual.BilingualVisualTests.tearDownClass()
 def test_freshness_section_actual_bilingual_render(self):
  v=copy.deepcopy(self.ui.view);v['news_freshness']=freshness.project(v,now=NOW)
  result=self.ui.render(view=v);self.assertIn('Latest developments',result['en']);self.assertIn('最新動態',result['zh']);self.assertIn('Older report',result['en']);self.assertIn('較早報導',result['zh']);self.assertTrue(result['unchanged'])
 def test_source_health_stays_unknown_and_map_watch_preserved(self):
  v=copy.deepcopy(self.ui.view);v['news_freshness']=freshness.project(v,now=NOW);r=self.ui.render(view=v)
  self.assertIn('Source health (no current connectivity probe)</dt><dd>Unknown',r['en']);self.assertLess(r['en'].index('id="world-map"'),r['en'].index('id="prediction-market-watch"'))
 def test_attribution_in_both_languages_without_body_or_image_reuse(self):
  v=copy.deepcopy(self.ui.view);a=v['items'][0];a['news_source']={'name':'Global Voices · Credited Author','url':'https://globalvoices.org/2026/10/10/trade/'};v['news_freshness']=freshness.project(v,now=NOW)
  r=self.ui.render(view=v)
  for lang in ['en','zh']:
   self.assertIn('Credited Author',r[lang]);self.assertIn('https://globalvoices.org/2026/10/10/trade/',r[lang]);self.assertIn('https://creativecommons.org/licenses/by/3.0/',r[lang]);self.assertIn('class="news-attribution"',r[lang])
  self.assertIn('whitespace normalized',r['en']);self.assertIn('第三方影音',r['zh']);self.assertTrue(r['unchanged'])
 def test_untrusted_news_escape_in_new_section(self):
  v=copy.deepcopy(self.ui.view);v['items'][0]['title']='<img src=x onerror=alert(1)>';v['news_freshness']=freshness.project(v,now=NOW);r=self.ui.render(view=v);self.assertNotIn('<img src=x',r['en']);self.assertIn('&lt;img',r['en'])

 def test_v41_disabled_and_failed_source_diagnostics_render_safely(self):
  v=copy.deepcopy(self.ui.view);v['discovery_sources']={'Global Voices':dict(enabled=False,status='DISABLED',last_success_at=None,new_article_count=0),
   'EIA Today in Energy':dict(enabled=True,status='SNAPSHOT_FALLBACK',last_success_at=None,new_article_count=0,reason='REQUEST_TIMEOUT',last_successful_cycle=None)}
  v['news_freshness']=freshness.project(v,now=NOW);r=self.ui.render(view=v)
  self.assertIn('Enabled: false',r['en']);self.assertIn('Latest acquisition error: REQUEST_TIMEOUT',r['en'])
  self.assertIn('已啟用: false',r['zh']);self.assertIn('最近取得錯誤: REQUEST_TIMEOUT',r['zh'])
  v['discovery_sources']['EIA Today in Energy']['reason']='<img src=x onerror=alert(1)>'
  r=self.ui.render(view=v);self.assertNotIn('<img src=x',r['en']);self.assertIn('&lt;img',r['en'])

 def test_v41_un_attribution_visible_in_both_languages(self):
  v=copy.deepcopy(self.ui.view);v['items'][0]['news_source']={'name':'UN News','url':'https://news.un.org/en/story/2026/10/123'};v['news_freshness']=freshness.project(v,now=NOW)
  r=self.ui.render(view=v);self.assertIn('Headline discovery from UN News (United Nations)',r['en']);self.assertIn('不自動構成官方事實確認',r['zh']);self.assertTrue(r['unchanged'])

 def test_v41_selection_metrics_have_human_labels_not_raw_json(self):
  v=copy.deepcopy(self.ui.view);v['discovery_sources']={'UN News':dict(enabled=True,status='LIVE',new_article_count=1,last_success_at=NOW.isoformat(),last_successful_cycle=dict(input_item_count=30,accepted_item_count=9,publication_unknown_count=0,rejected_by_reason={'NOT_MACRO_RELEVANT':21}))}
  v['news_freshness']=freshness.project(v,now=NOW);r=self.ui.render(view=v)
  self.assertIn('Received feed items: 30',r['en']);self.assertIn('Selected items: 9',r['en']);self.assertIn('No matched macro topic in title: 21',r['en'])
  self.assertIn('收到的 Feed 項目: 30',r['zh']);self.assertIn('選入項目: 9',r['zh']);self.assertNotIn('input_item_count',r['en'])
