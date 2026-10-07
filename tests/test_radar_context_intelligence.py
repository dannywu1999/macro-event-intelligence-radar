"""Offline A7 contracts and A6 relationship/append-only regressions."""
import copy,json,sqlite3,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
from tools.stage1b_historical_campaign import radar_context_intelligence as context
from tools.stage1b_historical_campaign import global_event_radar_read_adapter as radar
from tools.stage1b_historical_campaign.radar_intelligence_store import IntelligenceStore,IntelligenceRecorder,StoreError
from tools.stage1b_historical_campaign.radar_reality_replay import replay_event_as_of
from tools.stage1b_historical_campaign.radar_macroview_freeze import freeze_macroview
ROOT=Path(__file__).resolve().parents[1]
def event(title,sources=None):
 return dict(event_id='canonical-event-v0-'+'a'*64,event_title=title,source_names=sources or [],article_references=['https://example.test/a'],verification_status='UNVERIFIED_NEWS',geography_status='UNKNOWN',geography=None)
def inferred(title,sources=None):return context.enrich_events([event(title,sources)],[dict(article_reference='https://example.test/a',title=title)])[0]
def at(t):return '2026-10-07T'+t+':00Z'
class ContextTests(unittest.TestCase):
 def test_fixture_matrix(self):
  data=json.loads((ROOT/'tests/fixtures/context_intelligence_v1.json').read_text());self.assertTrue(data['synthetic'])
  for row in data['cases']:
   with self.subTest(row=row['name']):
    e=inferred(row['headline']);self.assertEqual(e['context_geography']['region_id'],row['region']);self.assertEqual(e['event_geography']['status'],'UNKNOWN');self.assertEqual(e['verification_status'],'UNVERIFIED_NEWS')
 def test_ecb_identity_and_separate_hq(self):
  e=inferred('ECB reviews framework');i=e['institution_context'][0];self.assertEqual(i['official_name'],'European Central Bank');self.assertEqual(i['official_name_zh'],'歐洲中央銀行');self.assertEqual(i['headquarters'],'Frankfurt, Germany');self.assertEqual(i['jurisdiction'],'Euro Area');self.assertEqual(i['relevant_currency'],'EUR / Euro');self.assertEqual(e['context_geography']['method'],'INSTITUTION_JURISDICTION');self.assertIn(e['context_geography']['confidence'],['LOW','MEDIUM']);self.assertIsNone(e['event_geography']['geography'])
 def test_eia_registry(self):
  e=inferred('EIA crude oil inventory');i=e['institution_context'][0];self.assertEqual(i['official_name_zh'],'美國能源資訊署');self.assertEqual(i['relevant_domain'],'Energy');self.assertIsNone(i['relevant_currency']);self.assertFalse(i['active_integration_claim'])
 def test_source_agency_context_is_low_confidence(self):
  e=inferred('New report', ['EIA Today in Energy']);self.assertEqual(e['context_geography']['confidence'],'LOW');self.assertEqual(e['institution_context'][0]['recognition_method'],'SOURCE_INSTITUTION_REFERENCE')
 def test_publisher_does_not_map_event(self):
  e=inferred('New report',['BBC London']);self.assertEqual(e['context_geography']['status'],'UNKNOWN')
 def test_explicit_region_high(self):
  for title,identity in [('Taiwan exports rise','taiwan'),('Red Sea shipping','red-sea'),('Persian Gulf disruption','persian-gulf')]:
   c=inferred(title)['context_geography'];self.assertEqual(c['region_id'],identity);self.assertEqual(c['confidence'],'HIGH');self.assertEqual(c['coordinate_role'],'CONTEXT_ANCHOR')
 def test_longest_phrase(self):self.assertEqual(inferred('South China Sea shipping')['context_geography']['region_id'],'south-china-sea')
 def test_specific_sea_wins_tied_country(self):self.assertEqual(inferred('US shipping in Red Sea')['context_geography']['region_id'],'red-sea')
 def test_taiwan_strait(self):self.assertEqual(inferred('Taiwan Strait shipping')['context_geography']['region_id'],'taiwan-strait')
 def test_euro_area_beats_broad_europe(self):self.assertEqual(inferred('European Central Bank reviews euro area rules')['context_geography']['region_id'],'euro-area')
 def test_aliases(self):
  for title in ['U.S. energy','US energy','United States energy','America energy']:
   self.assertEqual(inferred(title)['context_geography']['region_id'],'united-states')
 def test_pronoun_not_country(self):self.assertEqual(inferred('Tell us about policy')['context_geography']['status'],'UNKNOWN')
 def test_false_positive_names(self):
  for title in ['Georgia reports results','Turkey prices rise','Jordan comments on policy','Amazon reports earnings']:
   self.assertEqual(inferred(title)['context_geography']['status'],'UNKNOWN')
 def test_ambiguous_multi_region(self):
  c=inferred('US and China discuss trade')['context_geography'];self.assertEqual(c['status'],'MULTI_REGION');self.assertEqual(set(c['candidates']),{'united-states','china'});self.assertIsNone(c['centroid_lat'])
 def test_global_has_no_fake_anchor(self):
  c=inferred('Global energy markets')['context_geography'];self.assertEqual(c['region_id'],'global');self.assertIsNone(c['centroid_lat'])
 def test_body_weaker_than_headline(self):
  e=event('Taiwan exports');c,_,_=context.infer_context(e,[{'title':'Taiwan exports','summary':'China trade'}]);self.assertEqual(c['region_id'],'taiwan')
 def test_market_question_not_used(self):
  e=event('Unknown procedure');e['market_question']='Will Iran respond?';c,_,_=context.infer_context(e,[]);self.assertEqual(c['status'],'UNKNOWN')
 def test_registry_and_input_not_mutated(self):
  before=copy.deepcopy(context.INSTITUTIONS);e=inferred('ECB policy');e['institution_context'][0]['official_name']='mutation';self.assertEqual(context.INSTITUTIONS,before)
 def test_deterministic(self):self.assertEqual(inferred('Taiwan exports'),inferred('Taiwan exports'))
 def test_ecb_specific_explanation_guarded(self):
  e=inferred('ECB amends monetary policy implementation guidelines as part of regular review');self.assertIn('not an interest-rate decision',e['headline_explanation']['explanation_en']);self.assertNotEqual(inferred('ECB cuts interest rates')['headline_explanation']['method'],'CURATED_ECB_IMPLEMENTATION_GUIDELINES')
 def test_existing_curated_geo_not_factual_event_geo(self):
  e=event('ECB reviews');e.update(geography_status='KNOWN',geography=[{'evidence_type':'CURATED_PRESENTATION','latitude':50.11,'longitude':8.68,'evidence_reference':'https://example.test'}]);a=context.enrich_events([e],[])[0];self.assertEqual(a['event_geography']['status'],'UNKNOWN');self.assertEqual(a['geography'],e['geography'])
 def test_thousand_headlines(self):
  start=time.perf_counter()
  for i in range(1000):self.assertEqual(inferred('Shipping disrupted in Red Sea '+str(i))['context_geography']['region_id'],'red-sea')
  elapsed=time.perf_counter()-start;print('A7_THOUSAND_HEADLINE_SECONDS=%.3f'%elapsed);self.assertLess(elapsed,10)
class CorrectionRegressions(unittest.TestCase):
 def assert_region(self,title,source,region):
  e=inferred(title,[source] if source else [])
  self.assertEqual(e['context_geography']['region_id'],region)
  self.assertEqual(e['event_geography'],{'status':'UNKNOWN','geography':None})
  self.assertEqual(e['verification_status'],'UNVERIFIED_NEWS')
  if source:self.assertTrue(e['institution_context'])
  return e
 def assert_multi(self,source):
  c=inferred('US and China discuss trade',[source])['context_geography']
  self.assertEqual(c['status'],'MULTI_REGION');self.assertEqual(c['method'],'MULTI_REGION')
  self.assertEqual(set(c['candidates']),{'united-states','china'})
  self.assertEqual(c['confidence'],'LOW');self.assertTrue(c['reason']);self.assertTrue(c['supporting_mentions'])
  self.assertIsNone(c['centroid_lat']);self.assertIsNone(c['centroid_lon']);self.assertIsNone(c['region_id'])
 def test_01_ecb_europe(self):self.assert_region('European energy markets','ECB','europe')
 def test_02_eia_global(self):self.assert_region('Global energy supplies tighten','EIA','global')
 def test_03_eia_us_china(self):self.assert_multi('EIA')
 def test_04_ecb_us_china(self):self.assert_multi('ECB')
 def test_05_eia_china(self):self.assert_region('China crude oil imports','EIA','china')
 def test_06_ecb_us(self):self.assert_region('US economic developments','ECB','united-states')
 def test_07_ecb_institution_only(self):
  e=self.assert_region('ECB amends monetary policy implementation guidelines as part of regular review','ECB','euro-area')
  self.assertEqual(e['context_geography']['method'],'INSTITUTION_JURISDICTION')
  self.assertIn(e['context_geography']['confidence'],('LOW','MEDIUM'))
  self.assertEqual(e['institution_context'][0]['headquarters'],'Frankfurt, Germany')
  self.assertIn('not an interest-rate decision',e['headline_explanation']['explanation_en'])
 def test_08_taiwan_alias_spam(self):
  e=event('Taiwan exports rise',['EIA']);body='US U.S. USA United States America '*100
  c,_,_=context.infer_context(e,[{'title':e['event_title'],'summary':body}])
  self.assertEqual(c['region_id'],'taiwan');self.assertEqual(c['confidence'],'HIGH')
  self.assertEqual(sum(m['evidence_role']=='BODY' and m['region_id']=='united-states' for m in c['supporting_mentions']),1)
 def test_09_european_union(self):self.assert_region('European Union sanctions','ECB','european-union')
 def test_10_euro_area(self):self.assert_region('Euro area inflation','ECB','euro-area')
 def test_11_europe(self):self.assert_region('European banking','ECB','europe')
 def test_12_global(self):
  for term in ('global','worldwide','world'):
   for source in ('ECB','EIA'):
    with self.subTest(term=term,source=source):self.assert_region(term+' energy markets',source,'global')
 def test_13_unknown(self):self.assertEqual(inferred('Unspecified development')['context_geography']['status'],'UNKNOWN')
 def test_14_georgia(self):self.assertEqual(inferred('Georgia reports results')['context_geography']['status'],'UNKNOWN')
 def test_15_turkey(self):self.assertEqual(inferred('Turkey prices rise')['context_geography']['status'],'UNKNOWN')
 def test_16_jordan(self):self.assertEqual(inferred('Jordan comments')['context_geography']['status'],'UNKNOWN')
 def test_17_amazon(self):self.assertEqual(inferred('Amazon reports earnings')['context_geography']['status'],'UNKNOWN')
 def test_18_lowercase_us(self):self.assertEqual(inferred('Tell us about policy')['context_geography']['status'],'UNKNOWN')
 def test_alias_spam_cannot_break_headline_tie(self):
  c=inferred('US U.S. USA United States America and China discuss trade',['EIA'])['context_geography']
  self.assertEqual(c['status'],'MULTI_REGION');self.assertEqual(set(c['candidates']),{'united-states','china'})
 def test_body_only_alias_spam_cannot_break_tie(self):
  e=event('Trade discussion',['EIA']);c,_,_=context.infer_context(e,[{'summary':'US U.S. USA United States America and China'}])
  self.assertEqual(c['status'],'MULTI_REGION')
 def test_body_only_geography_outranks_institution(self):
  for source,body,region in [('ECB','European energy markets','europe'),('EIA','Global oil supplies','global'),('EIA','China imports','china')]:
   with self.subTest(source=source):
    c,ins,_=context.infer_context(event('New report',[source]),[{'summary':body}])
    self.assertEqual(c['region_id'],region);self.assertEqual(c['confidence'],'MEDIUM');self.assertEqual(c['method'],'EXPLICIT_CONTEXT_MENTION');self.assertTrue(ins)
 def test_body_cannot_break_headline_ambiguity(self):
  c,_,_=context.infer_context(event('US and China discuss trade',['EIA']),[{'summary':'US U.S. USA United States America '*40}])
  self.assertEqual(c['status'],'MULTI_REGION')
 def test_headline_taiwan_outranks_eia(self):self.assert_region('Taiwan exports rise','EIA','taiwan')
 def test_two_institutions_without_text_remain_ambiguous(self):
  c=inferred('New report',['ECB','EIA'])['context_geography'];self.assertEqual(c['status'],'MULTI_REGION');self.assertIsNone(c['centroid_lat'])

class HardeningTests(unittest.TestCase):
 def setUp(self):self.temp=tempfile.TemporaryDirectory(prefix='a6h-test-');self.store=IntelligenceStore(Path(self.temp.name)/'ledger.db',create=True)
 def tearDown(self):self.temp.cleanup()
 def views(self):
  refs=['https://example.test/a','https://example.test/b'];items=[dict(article_reference=r,title='Unchanged '+r,verification_status='UNVERIFIED_NEWS',observed_at=at('09:00')) for r in refs]
  def ev(i,rs):return dict(event_id='canonical-event-v0-'+i*64,event_title='Synthetic unchanged',article_references=rs,verification_status='UNVERIFIED_NEWS',geography_status='UNKNOWN',geography=None)
  old=dict(status='AVAILABLE',contract_version='fixture',items=items,events=[ev('a',[refs[0]]),ev('b',[refs[1]])]);new=copy.deepcopy(old);new['events']=[ev('c',refs)];return old,new
 def test_relationship_merge_replay_append_only(self):
  old,new=self.views();self.store.ingest_projection(old,observed_at=at('09:00'))
  with self.store.connection() as db:before=[tuple(r) for r in db.execute('SELECT * FROM observations')]
  self.store.ingest_projection(new,observed_at=at('10:00'))
  for e in old['events']:self.assertEqual(len(replay_event_as_of(self.store,e['event_id'],at('09:30'))['news_observations']),1)
  r=replay_event_as_of(self.store,new['events'][0]['event_id'],at('10:30'));self.assertEqual(r['replay_status'],'AVAILABLE');self.assertEqual(len(r['news_observations']),2)
  with self.store.connection() as db:after=[tuple(r) for r in db.execute('SELECT * FROM observations')]
  self.assertTrue(set(before)<=set(after))
 def test_recorder_stays_available_after_merge(self):
  old,new=self.views();views=iter([old,new]);clock=iter([at('09:00'),at('10:00')]);rec=IntelligenceRecorder(self.store.path,lambda:next(views),clock=lambda:next(clock));self.assertTrue(rec.record_once());self.assertTrue(rec.record_once());self.assertEqual(rec.status,'AVAILABLE');rec.close()
 def test_replace_blocked_through_supported_connection(self):
  old,_=self.views();self.store.ingest_projection(old,observed_at=at('09:00'))
  with self.store.connection() as db:row=tuple(db.execute('SELECT * FROM observations LIMIT 1').fetchone())
  with self.assertRaises(StoreError),self.store.connection(write=True) as db:db.execute('INSERT OR REPLACE INTO observations VALUES (?,?,?,?,?,?,?,?,?,?,?)',row)
 def test_known_and_legacy_mapped_not_unknown(self):
  v,_=self.views()
  for token in ('KNOWN','MAPPED'):
   v['events'][0]['geography_status']=token;v['events'][0]['geography']=[{'explicit':'fixture'}];f=freeze_macroview(v,v['events'][0]['event_id'],freeze_key='fixture');self.assertNotIn('GEOGRAPHY_UNKNOWN',f['unknowns'])
 def test_context_not_added_to_old_ledger_by_current_registry(self):
  old,_=self.views();self.store.ingest_projection(old,observed_at=at('09:00'));r=replay_event_as_of(self.store,old['events'][0]['event_id'],at('09:30'));self.assertIsNone(r['reconstructed_macroview']['snapshot']['event']['context_geography']);self.assertEqual(r['context_observations'],[])
 def test_context_changes_are_historical_versions(self):
  old,_=self.views();e=old['events'][0];e['event_title']='Taiwan exports';old['events']=context.enrich_events(old['events'],old['items']);self.store.ingest_projection(old,observed_at=at('09:00'));later=copy.deepcopy(old);later['events'][0]['event_title']='Red Sea shipping';later['events']=context.enrich_events(later['events'],later['items']);self.store.ingest_projection(later,observed_at=at('10:00'))
  first=replay_event_as_of(self.store,e['event_id'],at('09:30'));last=replay_event_as_of(self.store,e['event_id'],at('10:30'));self.assertEqual(first['reconstructed_macroview']['snapshot']['event']['context_geography']['region_id'],'taiwan');self.assertEqual(last['reconstructed_macroview']['snapshot']['event']['context_geography']['region_id'],'red-sea');self.assertEqual(len(last['context_observations']),2);self.assertEqual([r['active_at_as_of'] for r in last['context_observations']],[False,True]);self.assertTrue(last['context_observations'][0]['payload']['derived_from'])

 def test_context_without_provenance_rejected(self):
  old,_=self.views();old['events']=context.enrich_events(old['events'],old['items']);self.store.ingest_projection(old,observed_at=at('09:00'))
  with self.store.connection() as db:row=self.store.decode(db.execute("SELECT * FROM observations WHERE observation_kind='CONTEXT_GEOGRAPHY' LIMIT 1").fetchone())
  record={k:copy.deepcopy(row[k]) for k in ('observation_kind','entity_id','canonical_event_id','payload','provenance')};record['payload']['derived_from']=[]
  self.assertRaises(StoreError,self.store.append,[record],observed_at=at('10:00'))
 def test_context_wrong_event_binding_rejected(self):
  old,_=self.views();old['events']=context.enrich_events(old['events'],old['items']);self.store.ingest_projection(old,observed_at=at('09:00'))
  with self.store.connection() as db:row=self.store.decode(db.execute("SELECT * FROM observations WHERE observation_kind='CONTEXT_GEOGRAPHY' LIMIT 1").fetchone())
  record={k:copy.deepcopy(row[k]) for k in ('observation_kind','entity_id','canonical_event_id','payload','provenance')};record['canonical_event_id']='canonical-event-v0-'+'f'*64
  self.assertRaises(StoreError,self.store.append,[record],observed_at=at('10:00'))

 def test_corrected_inference_appends_without_rewriting_prior_context(self):
  old,_=self.views();old['events']=[event('European energy markets',['ECB'])]
  old['items']=[{**old['items'][0],'article_reference':'https://example.test/a','title':'European energy markets'}]
  old['events']=context.enrich_events(old['events'],old['items']);corrected=copy.deepcopy(old)
  # Explicitly labeled prior-algorithm fixture: emulate the audited bad state.
  prior,_,_=context.infer_context(event('New report',['ECB']),[])
  old['events'][0]['context_geography']=prior
  self.store.ingest_projection(old,observed_at=at('09:00'))
  eid=old['events'][0]['event_id'];f=self.store.freeze_event(eid,freeze_key='PRIOR_ALGORITHM_FIXTURE',as_of=at('09:30'),created_at=at('09:30'))
  with self.store.connection() as db:before=[tuple(r) for r in db.execute('SELECT * FROM observations')]
  self.store.ingest_projection(corrected,observed_at=at('10:00'))
  with patch.object(context,'infer_context',side_effect=AssertionError('REPLAY_REINFERENCE_FORBIDDEN')):
   early=replay_event_as_of(self.store,eid,at('09:30'));late=replay_event_as_of(self.store,eid,at('10:30'))
  self.assertEqual(early['reconstructed_macroview']['snapshot']['event']['context_geography']['region_id'],'euro-area')
  self.assertEqual(late['reconstructed_macroview']['snapshot']['event']['context_geography']['region_id'],'europe')
  self.assertEqual(len(late['context_observations']),2);self.assertEqual(self.store.freezes(eid),[f])
  with self.store.connection() as db:after=[tuple(r) for r in db.execute('SELECT * FROM observations')]
  self.assertTrue(set(before)<=set(after))

if __name__=='__main__':unittest.main()
