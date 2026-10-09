"""Production JS with mocked DOM/MapLibre boundary and actual local static routes."""
import http.client,json,os,shutil,subprocess,unittest
from pathlib import Path
import test_public_root_route as http_fixture
ROOT=Path(__file__).resolve().parents[1]
NODE=os.environ.get('RADAR_TEST_NODE') or str(Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe')
class InteractiveMapTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  events=[]
  for i in range(4):
   events.append(dict(event_id='event-'+str(i),event_title='<img src=x onerror=bad()> '+str(i),source_names=['Synthetic'],event_geography={'status':'UNKNOWN','geography':[]},context_geography=dict(status='INFERRED',region_id='europe',display_name='Europe',display_name_zh='歐洲',centroid_lat=50,centroid_lon=12,confidence='HIGH',method='EXPLICIT_REGION_TERM'),institution_context=[dict(institution_id='ecb',short_name='ECB',headquarters='Frankfurt',headquarters_zh='法蘭克福',context_lat=50,context_lon=8)]))
  events+= [dict(event_id='global',context_geography=dict(status='INFERRED',region_id='global',centroid_lat=None,centroid_lon=None)),dict(event_id='multi',context_geography=dict(status='MULTI_REGION',centroid_lat=None,centroid_lon=None))]
  r=subprocess.run([NODE,str(ROOT/'tests/ui_interactive_map_harness.cjs')],input=json.dumps(dict(client=str(ROOT/'ui/radar_interactive_map.js'),events=events)),capture_output=True,text=True,encoding='utf8',timeout=15)
  assert r.returncode==0,r.stderr
  cls.result=json.loads(r.stdout)
 def test_semantic_region_aggregation(self):
  r=self.result;self.assertEqual(len(r['groups']),2);self.assertTrue(all(len(g['members'])==4 for g in r['groups']));self.assertEqual(r['data']['name'],'Europe');self.assertEqual(r['data']['name_zh'],'歐洲')
 def test_institution_dedup_separate_role(self):self.assertEqual([g['kind'] for g in self.result['groups']],['context','institution'])
 def test_global_and_multi_not_pinned(self):self.assertFalse(any(e['event_id'] in ('global','multi') for g in self.result['groups'] for e in g['members']))
 def test_three_events_and_remaining_count(self):self.assertEqual(len(self.result['data']['events']),3);self.assertEqual(self.result['data']['more'],1)
 def test_hover_focus_tap_actual_handlers(self):self.assertEqual(self.result['ready'],'READY');self.assertEqual(self.result['clicked'],'event-0');self.assertEqual(self.result['popupEventId'],'event-0');self.assertTrue(self.result['clickStopped']);self.assertIn('4 相關事件',self.result['hovered'])
 def test_untrusted_popup_is_text_not_html(self):self.assertNotIn('img',self.result['popupTags']);self.assertIn('<img src=x onerror=bad()> 0',self.result['hovered'])
 def test_single_tile_error_keeps_loaded_map_visible(self):
  self.assertEqual(self.result['degraded'],'DEGRADED');self.assertTrue(self.result['stillVisible']);self.assertEqual(self.result['removedAfterTileError'],0)
 def test_failure_fallback_no_retry_storm(self):self.assertEqual(self.result['state'],'FALLBACK');self.assertEqual(self.result['markerCount'],2);self.assertEqual(self.result['removed'],2);self.assertTrue(self.result['fallback'])
 def test_projection_source_not_mutated(self):self.assertTrue(self.result['unchanged'])
class MapStaticRoutes(unittest.TestCase):
 @classmethod
 def setUpClass(cls):http_fixture.PublicRootRouteTests.setUpClass();cls.http=http_fixture.PublicRootRouteTests()
 @classmethod
 def tearDownClass(cls):http_fixture.PublicRootRouteTests.tearDownClass()
 def test_explicit_assets_and_no_traversal(self):
  for path in ['radar_interactive_map.js','vendor/maplibre-gl.js','vendor/maplibre-gl.css','vendor/MAPLIBRE-LICENSE.txt']:
   self.assertEqual(self.http.request('/ui/'+path)[0],200)
  # Unknown document routes use the existing SPA fallback, never filesystem lookup.
  status,_,body=self.http.request('/ui/vendor/../../README.md')
  self.assertEqual(status,200);self.assertEqual(body,self.http.request('/')[2])
 def test_map_controller_revalidates_after_candidate_update(self):
  connection=http.client.HTTPConnection('127.0.0.1',self.http.port,timeout=5)
  try:
   connection.request('GET','/ui/radar_interactive_map.js');response=connection.getresponse()
   self.assertEqual(response.status,200);self.assertEqual(response.getheader('Cache-Control'),'no-cache');response.read()
  finally:connection.close()
if __name__=='__main__':unittest.main()
