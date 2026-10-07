"""Isolated loopback/Edge acceptance; saved News and synthetic market fixture.

External access is opt-in and restricted in the browser to OpenFreeMap. No
collector, existing process inspection, persistence or market request is used.
"""
import argparse,copy,hashlib,json,os,subprocess,sys,tempfile,threading
from datetime import datetime,timedelta,timezone
from pathlib import Path
from unittest.mock import patch

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True);parser.add_argument('--news-view',type=Path,required=True);parser.add_argument('--allow-map-network',action='store_true');args=parser.parse_args()
 root=args.root.resolve();sys.path[:0]=[str(root)]
 from tools.stage1b_historical_campaign import radar_web_server as app,global_event_radar_read_adapter as radar
 from tools.stage1b_historical_campaign import radar_market_reality as market_module
 from tools.stage1b_historical_campaign.radar_market_reality import INPUT,iso
 original=args.news_view.read_bytes();captured=json.loads(original)
 before={p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in ['demo/radar_public/news/rss_headlines_eia_snapshot.csv','demo/radar_public/official-packet.json','demo/radar_public/ecb-official-packet.json','demo/radar_public/metadata.json']}
 with tempfile.TemporaryDirectory(prefix='radar-map-market-browser-') as temp:
  data=Path(temp);news=data/'news.json';news.write_text(json.dumps([dict(observed_time=i['observed_at'],event_time=i['reported_at'],headline_or_text=i['raw_title'],source_name=i['news_source']['name'],source_url=i['article_reference']) for i in captured['items']]),'utf8')
  base=radar.build_radar_view(radar.EvidencePaths(news=news,official=root/'demo/radar_public/official-packet.json'))
  assert len(base['items'])==28 and len(base['events'])==28
  event=next(e for e in base['events'] if e['official_evidence_count'] and 'EIA' in str(e['source_names']))
  now=datetime.now(timezone.utc);anchor=now-timedelta(minutes=10)
  raw=json.loads((root/'tests/fixtures/market_reality_v0.json').read_bytes())['observations']
  for row in raw:
   offset=datetime.fromisoformat(row['market_timestamp'].replace('Z','+00:00'))-datetime(2026,10,7,10,0,tzinfo=timezone.utc)
   row.update(event_id=event['event_id'],event_observed_at=iso(anchor),market_timestamp=iso(anchor+offset),observed_at=iso(anchor+offset),source={'name':'Synthetic offline fixture — not real market data','url':'https://example.test/synthetic-market'})
  market=data/'market.json';market.write_text(json.dumps(dict(schema=INPUT,synthetic=True,observations=raw)),'utf8')
  assert market_module.read_observations(market)==([], 'UNAVAILABLE')
  # Explicit TEMP-only mocked market source for browser rendering tests. The
  # real public reader rejects this very file; no runtime/config opt-out exists.
  def synthetic_test_source(path):
   assert Path(path).resolve()==market.resolve()
   packet=json.loads(market.read_bytes());assert packet['synthetic'] is True
   return [market_module.normalize_record(row) for row in packet['observations']], 'SYNTHETIC_TEST_ONLY'
  immutable={p:p.read_bytes() for p in [news,market]}
  clean={k:v for k,v in os.environ.items() if not k.startswith(('RADAR_','GLOBAL_EVENT_RADAR_')) and k not in ('HOST','PORT','PYTHONPATH')}
  clean.update(RADAR_DEMO_MODE='1',RADAR_DATA_ROOT=str(data),GLOBAL_EVENT_RADAR_NEWS_PATH=str(news),GLOBAL_EVENT_RADAR_OFFICIAL_PATH=str(root/'demo/radar_public/official-packet.json'),GLOBAL_EVENT_RADAR_MARKET_REALITY_PATH=str(market),GLOBAL_EVENT_RADAR_POLYMARKET_PATH='')
  with patch.dict(os.environ,clean,clear=True),patch.object(app,'HOST','127.0.0.1'),patch.object(app,'PORT',0),patch.object(market_module,'read_observations',side_effect=synthetic_test_source):
   server=app.bind_server();thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
   try:
    node=Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe';playwright=node.parent.parent/'node_modules/playwright';browser=Path(os.environ.get('ProgramFiles(x86)',''))/'Microsoft/Edge/Application/msedge.exe'
    config=dict(origin='http://127.0.0.1:'+str(server.server_port),playwright=str(playwright),browser=str(browser),eventId=event['event_id'],allowNetwork=args.allow_map_network,screenshot=str(Path(tempfile.gettempdir())/'a718-browser'))
    result=subprocess.run([str(node),str(root/'tests/ui_interactive_map_browser.cjs')],input=json.dumps(config),text=True,encoding='utf8',capture_output=True,timeout=240)
    print(result.stdout);print(result.stderr);assert result.returncode==0
   finally:server.shutdown();thread.join(timeout=10);server.server_close()
   assert not thread.is_alive()
  assert all(p.read_bytes()==value for p,value in immutable.items())
 assert args.news_view.read_bytes()==original
 assert before=={p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in before}
 print('OWN_SERVER_STOPPED=true; SOURCES_UNCHANGED=true; MARKET_FIXTURE=SYNTHETIC_ONLY; PERSISTENCE_ENABLED=false')
if __name__=='__main__':main()
