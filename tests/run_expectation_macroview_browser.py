"""Manual offline browser acceptance utility. Starts only its own loopback server.

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
  code="import sys,runpy;sys.path.insert(0,sys.argv[1]);sys.argv=['radar','--serve','--radar-only'];runpy.run_module('tools.stage1b_historical_campaign.radar_web_server',run_name='__main__')"
  process=subprocess.Popen([sys.executable,'-I','-B','-X','utf8','-c',code,str(root)],env=env,cwd=root,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8');lines=queue.Queue()
  reader=threading.Thread(target=lambda:[lines.put(line.strip()) for line in process.stdout],daemon=True);reader.start()
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
   for method in ['POST','PUT','PATCH','DELETE']:assert request('/api/app/radar',method)[0]==405
   for path in ['/api/app/refresh','/api/app/status','/api/admin']:assert request(path)[0]==404
   node=Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe';playwright=node.parent.parent/'node_modules/playwright';browser=Path(os.environ.get('ProgramFiles(x86)',''))/'Microsoft/Edge/Application/msedge.exe'
   config=dict(origin='http://127.0.0.1:'+str(port),events=len(view['events']),unlinked=len(view['market_expectations']),links=sum(bool(r['market_url']) for r in view['market_expectations']),ecbId=json.loads((root/'demo/radar_public/ecb-official-packet.json').read_text())['canonical_event_id'],playwright=str(playwright),browser=str(browser))
   result=subprocess.run([str(node),str(root/'tests/ui_expectation_macroview_browser.cjs')],input=json.dumps(config),text=True,encoding='utf-8',capture_output=True,timeout=120);print(result.stdout);print(result.stderr);assert result.returncode==0
   assert news.read_bytes()==news_before;assert args.markets.read_bytes()==market_before
  finally:
   process.terminate();process.wait(timeout=15);reader.join(timeout=2);process.stdout.close();process.stderr.close()
  assert process.poll() is not None
 assert before=={n:(root/n).read_bytes() for n in bound};print('REAL_BROWSER_ACCEPTANCE=PASS; OWN_SERVER_STOPPED=true; SOURCE_BYTES_UNCHANGED=true')
if __name__=='__main__':main()
