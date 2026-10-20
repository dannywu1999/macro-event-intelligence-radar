import copy,hashlib,html,json,re,socket,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from html.parser import HTMLParser
import build_gateway as g,build_event_case as c,build_workbench as w,build_global_radar as r
ROOT=Path(__file__).resolve().parents[1]
class Text(HTMLParser):
 def __init__(self):super().__init__();self.parts=[];self.tags=[]
 def handle_data(self,data):self.parts.append(data)
 def handle_starttag(self,tag,attrs):self.tags.append((tag,dict(attrs)))
def readable(raw):
 p=Text();p.feed(raw.decode());return '\n'.join(p.parts),p.tags
class GlobalRadar(unittest.TestCase):
 def setUp(self):
  self.d=r.derive();self.out=r.render(self.d)
  self.s=json.loads((ROOT/'source_snapshot.json').read_bytes())['snapshot']
 def test_original_article_records_preserved(self):
  articles=[a for e in self.d['events'] for a in e['articles']]
  self.assertEqual({a['source_url']:a for a in articles},{a['source_url']:a for a in self.s['articles']})
 def test_candidate_ids_exact_and_no_merges(self):
  self.assertEqual({e['candidate_id'] for e in self.d['events']},{e['event_id'] for e in self.s['event_candidates']})
  for e in self.d['events']:
   old=next(x for x in self.s['event_candidates'] if x['event_id']==e['candidate_id'])
   self.assertEqual(e['article_references'],old['article_references']);self.assertEqual(len(e['articles']),1)
   self.assertIn('NOT_PROVEN_DISTINCT_WORLD_EVENT',e['candidate_identity_type'])
 def test_all_articles_still_unverified(self):
  self.assertTrue(all(e['article_verification_status']=='UNVERIFIED_NEWS' and e['original_official_evidence_status']=='NO_OFFICIAL_EVIDENCE_LINKED' for e in self.d['events']))
 def test_cpi_exact_join_and_propositions(self):
  rows=[e for e in self.d['events'] if e['propositions']];self.assertEqual(len(rows),1)
  row=rows[0];old=w.derive()['case']
  self.assertEqual(row['candidate_id'],old['canonical_event']['event_id'])
  self.assertEqual(row['article_references'],old['canonical_event']['article_references'])
  self.assertEqual(row['propositions'],old['propositions']);self.assertEqual(row['evidence_links'],old['official_evidence'])
  self.assertEqual(row['supported_proposition_count'],4)
 def test_cpi_join_ambiguous_or_mismatch_rejected(self):
  data=w.derive();data['case']['canonical_event']['article_references']=['https://www.eia.gov/unrelated']
  with patch.object(w,'derive',return_value=data),self.assertRaisesRegex(ValueError,'AMBIGUOUS_CPI_JOIN'):r.derive()
 def test_energy_and_trade_generic_details(self):
  for family in ('ENERGY','TRADE_POLICY'):
   e=next(x for x in self.d['events'] if x['original_event_family']==family)
   text=self.out[r.path(e)+'index.html'].decode()
   for section in ('id="discovery"','id="official"','id="timeline"','id="expectations"','id="macroview"','id="export"'):self.assertIn(section,text)
   self.assertIn('尚未連結官方命題核實證據',text);self.assertIn('尚無通過證據門檻',text)
   self.assertNotIn('class="metrics"',text);self.assertNotIn('SCHEDULED_EMBARGO',text)
   self.assertIsNone(e['macroview']);self.assertEqual(e['evidence_links'],[])
 def test_taxonomy_and_empty_categories_honest(self):
  counts={x['id']:x['candidate_count'] for x in self.d['categories']}
  self.assertEqual(counts,{'central_banks':0,'geopolitics':0,'trade':1,'energy':3,'economic_data':1,'expectations':0,'context':2})
  self.assertEqual(self.d['counts']['empty_product_categories'],3)
  self.assertIn('目前公開快照無此類資料',self.out['index.html'].decode())
 def test_no_fake_score_region_or_future_data(self):
  for e in self.d['events']:
   self.assertIsNone(e['importance_assessment']);self.assertIsNone(e['event_occurred_at'])
   self.assertIsNone(e['market_expectations']['value']);self.assertIsNone(e['market_reaction']['value'])
   self.assertEqual(e['causality'],'NOT_ESTABLISHED');self.assertEqual(e['detection_latency'],'UNKNOWN')
   self.assertNotIn('region',e);self.assertNotIn('impact_score',e)
 def test_clocks_distinct_and_cpi_unchanged(self):
  for e in self.d['events']:
   a=e['articles'][0]
   self.assertEqual((e['source_published_at'],e['observed_at'],e['recorded_at']),(a['source_reported_at'],a['observed_at'],a['recorded_at']))
   self.assertEqual(e['first_observed_scope'],'SAVED_LOCAL_OBSERVATION_NOT_GLOBAL_FIRST_SEEN')
   self.assertEqual(e['snapshot_as_of'],w.derive()['case']['as_of'])
  e=next(x for x in self.d['events'] if x['propositions'])
  self.assertEqual(e['timeline'],w.derive()['case']['timeline']);self.assertIsNone(e['official_document']['published_at'])
  self.assertEqual(e['official_document']['publication_precision'],'DATE_ONLY')
 def test_missing_time_stays_unknown_in_renderer_and_export(self):
  e=copy.deepcopy(self.d['events'][0]);e['source_published_at']=None;e['observed_at']=None;e['recorded_at']=None
  e['timeline']=[{'role':'UNKNOWN','value':None,'meaning_zh':'未知'}]
  self.assertIn('UNKNOWN',r.event_detail(e).decode());self.assertIn('UTC: UNKNOWN',r.citation(e))
  self.assertIsNone(json.loads(r.enc(e))['observed_at']);self.assertNotIn('1970',r.event_detail(e).decode())
 def test_rights_and_attribution_exact(self):
  rights=json.loads((ROOT/'source_snapshot.json').read_bytes())['rights']
  for e in self.d['events']:
   self.assertEqual(e['rights'],[x for x in rights if x['source_url']==e['source_urls'][0]])
   text=self.out[r.path(e)+'index.html'].decode()
   for record in e['rights']:
    self.assertIn(record['policy_url'],text)
    if record['author']:self.assertIn(html.escape(record['author'],quote=True),text)
    if record['license_url']:self.assertIn(record['license_url'],text)
 def test_static_html_has_real_readable_content(self):
  text,tags=readable(self.out['index.html'])
  self.assertIn('先看事件，再查證據',text);self.assertIn('7 個保守文章集合候選',text)
  for e in self.d['events']:
   self.assertIn(e['original_title'],text);self.assertIn(e['translated_title'],text)
   self.assertIn(e['source_urls'][0],[a.get('href') for t,a in tags if t=='a'])
   self.assertIn('/radar/'+r.path(e),[a.get('href') for t,a in tags if t=='a'])
 def test_json_text_html_agree(self):
  d=json.loads(self.out['events.json']);self.assertEqual(d,self.d)
  plain=self.out['events.txt'].decode()
  for e in d['events']:
   text,_=readable(self.out[r.path(e)+'index.html'])
   for k in ('candidate_id','original_title','source_published_at','observed_at','recorded_at'):
    self.assertIn(e[k],plain);self.assertIn(e[k],text)
   self.assertEqual(json.loads(self.out[r.path(e)+'event.json'])['event'],e)
 def test_exports_preserve_unknowns_and_provenance(self):
  for e in self.d['events']:
   export=json.loads(self.out[r.path(e)+'event.json'])
   self.assertEqual(export['source_inputs'],self.d['source_inputs'])
   self.assertIsNone(export['event']['event_occurred_at']);self.assertEqual(export['event']['article_verification_status'],'UNVERIFIED_NEWS')
   self.assertIn('FIRST_SEEN_NOT_PROVEN',self.out[r.path(e)+'citation.txt'].decode())
 def test_escape_hostile_headline_and_attribution(self):
  e=copy.deepcopy(self.d['events'][0]);bad='<img src=x onerror=alert(1)>'
  e['translated_title']=bad;e['original_title']=bad;e['source_names']=[bad]
  for raw in (r.event_detail(e),r.card(e).encode()):
   text,tags=readable(raw)
   self.assertIn(bad,text);self.assertNotIn('img',[t for t,a in tags])
   self.assertTrue(all(not any(k.startswith('on') for k in a) for t,a in tags))
 def test_deterministic_fresh_and_existing_build_no_network(self):
  with tempfile.TemporaryDirectory() as tmp,patch.object(socket.socket,'connect',side_effect=AssertionError('NO_NETWORK')),patch('socket.getaddrinfo',side_effect=AssertionError('NO_DNS')):
   p=Path(tmp);g.build(p);c.build(ROOT,p);w.build(ROOT,p)
   one=r.build(ROOT,p);two=r.build(ROOT,p)
   self.assertEqual(one,two);self.assertEqual(one,self.out)
   g.build(p) # existing new subtree accepted without bypassing inventory
 def test_23_archives_exact(self):
  pin=r.archive(ROOT/'public')
  self.assertEqual(len(pin['files']),23)
  self.assertEqual(sum(k.startswith('workbench/') for k in pin['files']),6)
 def test_manifest_inventory_hash_bytes(self):
  self.assertEqual(set(self.out),r.files_for(r.source_ids(ROOT)))
  manifest=json.loads(self.out['v1/manifest.json'])
  self.assertEqual(set(manifest['files']),set(self.out)-{'v1/manifest.json'})
  for n,v in manifest['files'].items():
   self.assertEqual(g.digest(self.out[n]),v['sha256']);self.assertEqual(len(self.out[n]),v['bytes'])
  actual={p.relative_to(ROOT/'public').as_posix() for p in (ROOT/'public').rglob('*') if p.is_file()}
  self.assertEqual(actual,set(r.archive(ROOT/'public')['files'])|{'radar/'+x for x in self.out})
 def test_unknown_asset_rejected(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp);(p/'private.sqlite').write_bytes(b'SYNTHETIC_ONLY')
   with self.assertRaises(ValueError):r.inventory(p)
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp);(p/'radar').mkdir();(p/'radar/secret.txt').write_text('SYNTHETIC_ONLY')
   with self.assertRaises(ValueError):g.build(p)
 def test_source_url_and_rights_fail_closed_existing_contract(self):
  source=json.loads((ROOT/'source_snapshot.json').read_bytes());release=json.loads((ROOT/'release.json').read_bytes())
  source['snapshot']['articles'][0]['source_url']='javascript:alert(1)'
  with self.assertRaises(ValueError):g.validate(source,release)
  source=json.loads((ROOT/'source_snapshot.json').read_bytes());source['rights'][0]['policy_status']='UNKNOWN'
  with self.assertRaises(ValueError):g.validate(source,release)
 def test_no_runtime_sideeffects_or_external_network(self):
  js=(ROOT/'radar_src/radar.js').read_text(encoding='utf-8')
  for forbidden in ('fetch(','XMLHttpRequest','WebSocket','localStorage','indexedDB','setInterval','innerHTML','eval('):self.assertNotIn(forbidden,js)
  for raw in self.out.values():
   for forbidden in (b'C:\\Users\\',b'SYNTHETIC_LAB',b'.sqlite',b'API_KEY=',b'localhost:',b'BBC',b'CNBC'):self.assertNotIn(forbidden,raw)
  self.assertTrue(all(e['live_feed'] is False and e['trading_signal'] is False for e in self.d['events']))
 def test_semantic_csp_and_optional_javascript(self):
  for name in ['index.html',r.path(self.d['events'][0])+'index.html']:
   raw=self.out[name].decode()
   self.assertIn("connect-src 'none'",raw);self.assertIn('<main',raw);self.assertIn('href="#main"',raw)
   _,tags=readable(self.out[name]);self.assertTrue(all(a.get('src')=='/radar/v1/radar.js' for t,a in tags if t=='script'))
  self.assertIn('id="filters"',self.out['index.html'].decode());self.assertIn('<noscript>',self.out['index.html'].decode())
 def test_sort_transparent_without_materiality(self):
  ordered=sorted(self.d['events'],key=lambda e:(g.utc(e['observed_at']),g.utc(e['source_published_at']),e['candidate_id']),reverse=True)
  self.assertEqual(self.d['events'],ordered);self.assertIn('不是重要性或市場影響評分',self.out['index.html'].decode())
if __name__=='__main__':unittest.main()

