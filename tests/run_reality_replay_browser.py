"""A6 offline real-data ingestion and real-browser replay acceptance. Starts only its own loopback server.

Arguments name the explicit product tree and TEMP captured News/market inputs.
No public fetch, provider refresh, or existing runtime inspection is performed.
"""
import argparse,hashlib,http.client,json,os,queue,subprocess,sys,tempfile,threading
from pathlib import Path

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True);parser.add_argument('--news-view',type=Path,required=True);parser.add_argument('--markets',type=Path,required=True);args=parser.parse_args();root=args.root.resolve()
 original=json.loads(args.news_view.read_bytes());rows=[dict(observed_time=i['observed_at'],event_time=i['reported_at'],headline_or_text=i['raw_title'],source_name=i['news_source']['name'],source_url=i['article_reference']) for i in original['items']]
 bound=json.loads((root/'PUBLIC_RELEASE_MANIFEST.json').read_text())['files'] if (root/'PUBLIC_RELEASE_MANIFEST.json').is_file() else ['tools/stage1b_historical_campaign/radar_web_server.py','tools/stage1b_historical_campaign/global_event_radar_read_adapter.py','ui/radar_public_showcase_v1.html','demo/radar_public/official-packet.json','demo/radar_public/ecb-official-packet.json','demo/radar_public/news/rss_headlines_eia_snapshot.csv']
 before={n:(root/n).read_bytes() for n in bound};market_before=args.markets.read_bytes()
 with tempfile.TemporaryDirectory(prefix='radar-evidence-browser-') as temp:
  data=Path(temp);news=data/'news.json';news.write_text(json.dumps(rows),'utf-8');news_before=news.read_bytes()
  env={k:v for k,v in os.environ.items() if not k.startswith(('GLOBAL_EVENT_RADAR_','RADAR_')) and k not in {'HOST','PORT','PYTHONPATH'}}
  env.update(HOST='127.0.0.1',PORT='0',RADAR_DATA_ROOT=str(data),RADAR_DEMO_MODE='1',GLOBAL_EVENT_RADAR_NEWS_PATH=str(news),GLOBAL_EVENT_RADAR_OFFICIAL_PATH=str(root/'demo/radar_public/official-packet.json'),GLOBAL_EVENT_RADAR_POLYMARKET_PATH=str(args.markets))
  sys.path.insert(0,str(root))
  from tools.stage1b_historical_campaign import global_event_radar_read_adapter as adapter
  from tools.stage1b_historical_campaign.radar_intelligence_store import IntelligenceStore,now,time_value
  from tools.stage1b_historical_campaign.radar_reality_replay import replay_event_as_of
  from datetime import datetime,timedelta,timezone
  view=adapter.build_radar_view(adapter.EvidencePaths(news=news,official=root/'demo/radar_public/official-packet.json',polymarket=args.markets))
  store=IntelligenceStore(data/'intelligence.sqlite3',create=True);recorded=now();store.ingest_projection(view,observed_at=recorded)
  assert len(view['items'])==28 and len(view['events'])==28 and len(view['official_evidence'])==2
  for event in view['events']:
   replay=replay_event_as_of(store,event['event_id'],recorded);assert replay['reconstructed_macroview']['snapshot']['event']['geography']==event['geography'];assert replay['reconstructed_macroview']['expectation_state']=='NONE'
  event_id=next(e['event_id'] for e in view['events'] if e['official_evidence_count'] and 'EIA' in str(e['source_names']))
  store.freeze_event(event_id,freeze_key='REAL_LOCAL_ACCEPTANCE',as_of=recorded,created_at=now())
  # Deliberate, labeled synthetic text in TEMP ledger only tests HTML escaping.
  original_news=next(i for i in view['items'] if i['article_reference'] in next(e['article_references'] for e in view['events'] if e['event_id']==event_id));evil={**original_news,'title':'Synthetic XSS fixture <img src=x onerror="window.BAD=1">'};test_time=now()
  store.append([dict(observation_kind='NEWS_ARTICLE',entity_id=evil['article_reference'],canonical_event_id=event_id,payload=evil,provenance={'synthetic_test_only':True})],observed_at=test_time)
  before_time=(datetime.fromisoformat(recorded.replace('Z','+00:00'))-timedelta(seconds=1)).isoformat().replace('+00:00','Z')
  env['RADAR_INTELLIGENCE_DB']=str(data/'intelligence.sqlite3')
  code="import sys,runpy;sys.path.insert(0,sys.argv[1]);sys.argv=['radar','--serve','--radar-only'];runpy.run_module('tools.stage1b_historical_campaign.radar_web_server',run_name='__main__')"
  process=subprocess.Popen([sys.executable,'-I','-B','-X','utf8','-c',code,str(root)],env=env,cwd=root,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8');lines=queue.Queue()
  reader=threading.Thread(target=lambda:[lines.put(line.strip()) for line in process.stdout],daemon=True);reader.start()
  error_lines=[]
  error_reader=threading.Thread(target=lambda:[error_lines.append(line) for line in process.stderr],daemon=True);error_reader.start()
  try:
   port=None
   for _ in range(10):
    line=lines.get(timeout=10)
    if line.startswith('RADAR_LISTENING='):port=int(line.rsplit(':',1)[1]);break
   assert port and port!=8765
   def request(path,method='GET'):
    conn=http.client.HTTPConnection('127.0.0.1',port,timeout=10)
    try:conn.request(method,path);response=conn.getresponse();return response.status,response.read()
    finally:conn.close()
   for path in ['/','/healthz','/api/app/radar']:assert request(path)[0]==200,path
   view=json.loads(request('/api/app/radar')[1]);assert len(view['official_evidence'])==2;assert len(view['market_expectations'])>0;assert all(e['expectation_state']=='NONE' for e in view['macroview_previews']);assert view['expectation_provider']['enabled'] is False
   assert request('/api/app/replay?event_id='+event_id+'&as_of='+recorded)[0]==200
   assert request('/api/app/replay?event_id=bad&as_of=bad')[0]==400
   print('REAL_STATE_INGESTION=28_ARTICLES_28_EVENTS_2_OFFICIAL_20_UNLINKED; RESTART_FREEZE_PASS=true');print('A7_REAL_COUNTS='+json.dumps(dict(total_events=len(view['events']),verified_event_geography=sum(e['event_geography']['status']=='KNOWN' for e in view['events']),context_geography=sum(e['context_geography']['status']=='INFERRED' for e in view['events']),institution_context=sum(bool(e['institution_context']) for e in view['events']),unknown_context=sum(e['context_geography']['status']=='UNKNOWN' for e in view['events']))))
   for method in ['POST','PUT','PATCH','DELETE']:assert request('/api/app/radar',method)[0]==405
   for path in ['/api/app/refresh','/api/app/status','/api/admin']:assert request(path)[0]==404
   node=Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe';playwright=node.parent.parent/'node_modules/playwright';browser=Path(os.environ.get('ProgramFiles(x86)',''))/'Microsoft/Edge/Application/msedge.exe'
   config=dict(screenshot=str(Path(tempfile.gettempdir())/'a7-world-map-review.png'),eventId=event_id,before=before_time,asOf=test_time,origin='http://127.0.0.1:'+str(port),events=len(view['events']),unlinked=len(view['market_expectations']),links=sum(bool(r['market_url']) for r in view['market_expectations']),ecbId=json.loads((root/'demo/radar_public/ecb-official-packet.json').read_text())['canonical_event_id'],playwright=str(playwright),browser=str(browser))
   config['europeId']=next(e['event_id'] for e in view['events'] if 'European banking' in e['event_title'])
   config['globalId']=next(e['event_id'] for e in view['events'] if e['event_title'].startswith('What goes into diesel'))
   result=subprocess.run([str(node),str(root/'tests/ui_reality_replay_browser.cjs')],input=json.dumps(config),text=True,encoding='utf-8',capture_output=True,timeout=120);print(result.stdout);print(result.stderr);assert result.returncode==0
   # A separate, labeled TEMP fixture and loopback server test unpinned Global
   # and MULTI_REGION through the same real API/browser. Real inputs stay intact.
   from unittest.mock import patch
   from tools.stage1b_historical_campaign import radar_web_server as app
   fixture=data/'synthetic-correction-news.json'
   fixture.write_text(json.dumps([dict(observed_time=recorded,event_time=None,headline_or_text=title,source_name=source,source_url='https://example.test/correction/'+str(i)) for i,(title,source) in enumerate([('European energy markets','ECB'),('Global energy supplies tighten','EIA'),('US and China discuss trade','EIA')])]),'utf-8')
   fixture_before=fixture.read_bytes()
   with patch.dict(os.environ,{'RADAR_DATA_ROOT':str(data),'RADAR_DEMO_MODE':'1','GLOBAL_EVENT_RADAR_NEWS_PATH':str(fixture),'GLOBAL_EVENT_RADAR_OFFICIAL_PATH':'','GLOBAL_EVENT_RADAR_POLYMARKET_PATH':'','GLOBAL_EVENT_RADAR_GEOGRAPHY_PATH':'','GLOBAL_EVENT_RADAR_SOURCE_HEALTH_PATH':''}),patch.object(app,'HOST','127.0.0.1'),patch.object(app,'PORT',0):
    fixture_server=app.bind_server();fixture_thread=threading.Thread(target=fixture_server.serve_forever,daemon=True);fixture_thread.start()
    try:
     fixture_config=dict(correctionOnly=True,origin='http://127.0.0.1:'+str(fixture_server.server_port),playwright=str(playwright),browser=str(browser))
     result=subprocess.run([str(node),str(root/'tests/ui_reality_replay_browser.cjs')],input=json.dumps(fixture_config),text=True,encoding='utf-8',capture_output=True,timeout=60);print(result.stdout);print(result.stderr);assert result.returncode==0
    finally:fixture_server.shutdown();fixture_thread.join(timeout=10);fixture_server.server_close()
    assert not fixture_thread.is_alive()
   assert fixture.read_bytes()==fixture_before
   assert news.read_bytes()==news_before;assert args.markets.read_bytes()==market_before
  finally:
   process.terminate();process.wait(timeout=15);reader.join(timeout=2);error_reader.join(timeout=2);process.stdout.close();process.stderr.close()
  assert process.poll() is not None
 assert before=={n:(root/n).read_bytes() for n in bound};print('REAL_BROWSER_ACCEPTANCE=PASS; OWN_SERVER_STOPPED=true; SOURCE_BYTES_UNCHANGED=true')
if __name__=='__main__':main()
