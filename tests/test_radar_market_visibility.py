"""Public-safe contract tests, no provider adapter, real values or credentials."""
import copy, http.client, json, os, subprocess, tempfile, threading, unittest
from pathlib import Path
from unittest.mock import Mock, patch
from tools.stage1b_historical_campaign import radar_market_reality as market
from tools.stage1b_historical_campaign import radar_web_server as app
from tools.stage1b_historical_campaign.radar_intelligence_store import IntelligenceStore
from tools.stage1b_historical_campaign.radar_reality_replay import replay_event_as_of
from radar_replay_fixture import projection, at

class VisibilityTests(unittest.TestCase):
    def test_unknown_scope_not_public(self):self.assertFalse(market.public_observation({'price_or_level':12345}))
    def test_explicit_public_noncommercial(self):self.assertTrue(market.public_observation({'data_usage_scope':'PUBLIC_REDISTRIBUTABLE','provider':'Authorized fixture'}))
    def test_tiingo_scope_cannot_be_promoted(self):
        for row in [{'provider':'Tiingo'}, {'source':{'name':'Tiingo IEX'}}, {'source':{'url':'https://api.tiingo.com/iex/spy/prices'}}]:
            self.assertFalse(market.public_observation({**row,'data_usage_scope':'PUBLIC_REDISTRIBUTABLE'}))
    def test_malformed_source_fail_closed(self):self.assertFalse(market.public_observation({'data_usage_scope':'PUBLIC_REDISTRIBUTABLE','source':[]}))
    def test_synthetic_not_public(self):self.assertFalse(market.public_observation({'data_usage_scope':'PUBLIC_REDISTRIBUTABLE','synthetic':True}))
    def private_view(self):
        v,eid=projection();private={'contract_version':market.CONTRACT,'data_usage_scope':'PRIVATE_RESEARCH_ONLY',
            'instruments':[{'symbol':'SPY','price_or_level':987654.125,'open':987654.125,'close':987654.125,'provider':'Tiingo','data_usage_scope':'PRIVATE_RESEARCH_ONLY'}]}
        v['events'][0]['market_reality']=private
        v['market_reality_observations']=[dict(price_or_level=987654.125,provider='Tiingo',data_usage_scope='PRIVATE_RESEARCH_ONLY')]
        v['private_market_observations']=[private];v['market_reality_windows']={'T0':private}
        return v,eid
    def test_recursive_private_export_filtered(self):
        v,_=self.private_view();before=copy.deepcopy(v);r=market.public_market_view(v)
        self.assertEqual(v,before);self.assertNotIn('987654.125',json.dumps(r));self.assertNotIn('Tiingo',json.dumps(r))
        self.assertNotIn('private_market_observations',r);self.assertNotIn('market_reality_windows',r)
    def test_untagged_meaningful_snapshot_filtered(self):
        v,_=self.private_view();v['events'][0]['market_reality'].pop('data_usage_scope');v['events'][0]['market_reality']['instruments'][0].pop('data_usage_scope')
        self.assertIsNone(market.public_market_view(v)['events'][0]['market_reality'])
    def test_null_generic_snapshot_preserved(self):
        r=market.project_snapshot('unknown',None,[],as_of=at('10:00'));self.assertEqual(market.public_market_view(r),r)
    def test_private_replay_event_and_freeze_payload_not_serialized(self):
        with tempfile.TemporaryDirectory(prefix='a81-visibility-') as temp:
            s=IntelligenceStore(Path(temp)/'ledger.db',create=True);v,eid=self.private_view();v['market_reality_observations']=[]
            s.ingest_projection(v,observed_at=at('10:00'));before=s.path.read_bytes()
            result=replay_event_as_of(s,eid,at('10:07'))
            self.assertNotIn('987654.125',json.dumps(result));self.assertNotIn('Tiingo',json.dumps(result));self.assertEqual(before,s.path.read_bytes())
    def test_private_source_state_not_replayed(self):
        with tempfile.TemporaryDirectory(prefix='a81-source-') as temp:
            s=IntelligenceStore(Path(temp)/'ledger.db',create=True);v,eid=projection();s.ingest_projection(v,observed_at=at('10:00'))
            s.append([dict(observation_kind='SOURCE_STATE',entity_id='private_market:fixture',payload={'status':'PRIVATE'})],observed_at=at('10:01'))
            self.assertNotIn('private_market:',json.dumps(replay_event_as_of(s,eid,at('10:07'))))
    def test_real_http_api_and_actual_renderer_no_private_values(self):
        # Poison the actual cached feed boundary, not only the lower projector.
        v,_=self.private_view();ingestion=Mock();ingestion.read_view.return_value=v
        with patch.dict(os.environ,{'RADAR_DEMO_MODE':'1'}),patch.object(app,'PORT',0):server=app.bind_server()
        server.live_ingestion=ingestion;thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        def request(path):
            c=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5)
            try:c.request('GET',path);response=c.getresponse();return response.status,response.read()
            finally:c.close()
        try:
            status,body=request('/api/app/radar');self.assertEqual(status,200)
            self.assertNotIn(b'987654.125',body);self.assertNotIn(b'Tiingo',body)
            with patch.dict(os.environ,{'RADAR_DEMO_MODE':'1'}):_,html=request('/')
            root=Path(__file__).resolve().parents[1]
            node=os.environ.get('RADAR_TEST_NODE') or str(Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe')
            result=subprocess.run([node,str(root/'tests/ui_render_harness.cjs')],input=json.dumps(dict(html=html.decode(),view=json.loads(body),translations=(root/'ui/radar_demo_translations.js').read_text(encoding='utf8'))),text=True,encoding='utf8',capture_output=True,check=True,timeout=10)
            markup=json.loads(result.stdout)['en']
            self.assertNotIn('987654.125',markup);self.assertNotIn('Tiingo',markup);self.assertIn('UNVERIFIED_NEWS',markup)
        finally:server.shutdown();server.server_close();thread.join(5)
        self.assertFalse(thread.is_alive())
    def test_default_public_replay_database_disabled(self):
        from tools.stage1b_historical_campaign.radar_intelligence_store import configured_db
        with patch.dict(os.environ,{},clear=True):self.assertIsNone(configured_db())

if __name__=='__main__':unittest.main()
