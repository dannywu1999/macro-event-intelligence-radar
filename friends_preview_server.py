"""Public read-only saved metadata preview. No production entry point, store or collector."""
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlsplit,parse_qs
import hashlib,json,os,sys,threading
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parent
OFF=('RADAR_LIVE_ECB','RADAR_LIVE_EIA','RADAR_LIVE_GUARDIAN','RADAR_LIVE_MARKET_WATCH','RADAR_LIVE_NEWS','RADAR_LIVE_UN_NEWS','RADAR_NEWS_CAPTURE','RADAR_PERSIST_INTELLIGENCE')
ASSETS={'/ui/'+n for n in ('radar_product_workbench.js','radar_product_workbench.css','radar_headline_presentation.js')}

# Ignore only named tracking fields; functional parameters remain strictly validated.
UTM_PARAMETERS=frozenset(('utm_source','utm_medium','utm_campaign','utm_term','utm_content','utm_id','utm_source_platform','utm_creative_format','utm_marketing_tactic'))
def preview_query(query,allowed=()):
 q=parse_qs(query,keep_blank_values=True,max_num_fields=len(UTM_PARAMETERS)+2)
 q={k:v for k,v in q.items() if k not in UTM_PARAMETERS}
 if set(q)-set(allowed) or any(len(v)!=1 for v in q.values()):raise ValueError()
 return q

LLM_INDEX='''# Macro Trading OS — public saved snapshot

Public, read-only macro-event research preview. This is NOT a live news feed or a trading signal.

- Event and article metadata (Markdown): https://macro-radar-friends-preview.onrender.com/llm/events.md
- Compact data (JSON): https://macro-radar-friends-preview.onrender.com/llm/events.json
- Web interface: https://macro-radar-friends-preview.onrender.com/

Source titles and URLs are attributed. Traditional Chinese headlines are presentation-only translations. News discovery is not official factual verification. Event candidates are not confirmed events. Unknown evidence and market snapshots remain unavailable. No article full text or copyrighted images are provided.
'''

def llm_snapshot(views):
    v=views[('public','168')]
    articles=[]
    for item in v['items']:
        source=item.get('news_source') or {}
        local=item.get('local_observation') or {}
        zh=item.get('headline_translation') or {}
        articles.append({
            'headline_zh':zh.get('translated_title') or item.get('title'),
            'headline_original':item.get('raw_title') or item.get('title'),
            'source':source.get('name'),
            'source_url':item.get('article_reference'),
            'source_reported_at':item.get('reported_at'),
            'observed_at':item.get('observed_at'),
            'recorded_at':local.get('recorded_at'),
            'verification_status':item.get('verification_status'),
            'event_family':item.get('event_family'),
            'translation_status':zh.get('status') if zh else 'NOT_AVAILABLE',
        })
    events=[]
    for event in v['events']:
        events.append({
            'event_id':event.get('event_id'),
            'event_title':event.get('event_title'),
            'verification_status':event.get('verification_status'),
            'official_evidence_status':event.get('official_evidence_status'),
            'article_count':event.get('article_count'),
            'article_references':event.get('article_references',[]),
        })
    return {
        'schema':'MACRO_RADAR_PUBLIC_LLM_V1',
        'scope':'SAVED_PUBLIC_METADATA_ONLY',
        'live_feed':False,
        'trading_signal':False,
        'window_hours':168,
        'latest_observed_data_at':v.get('latest_observed_data_at'),
        'last_successful_update':v.get('last_successful_update'),
        'article_count':len(articles),
        'event_candidate_count':len(events),
        'articles':articles,
        'event_candidates':events,
    }

def llm_markdown(data):
    def clean(v):
        if v is None:return 'UNKNOWN'
        return str(v).replace('\r',' ').replace('\n',' ').strip() or 'UNKNOWN'
    lines=[
        '# Macro Trading OS — saved public research snapshot',
        '',
        '> Not live news, official factual verification, a frozen MacroView, or a trading signal.',
        '> Headlines are attributed metadata. Chinese translations are presentation-only. All times below are UTC.',
        '',
        '- Scope: SAVED_PUBLIC_METADATA_ONLY',
        '- Window: last 168 hours within the archived acquisition window (not the current 168 hours)',
        '- Latest observed data: '+clean(data['latest_observed_data_at']),
        '- Last successful update: '+clean(data['last_successful_update']),
        '- Articles: '+str(data['article_count']),
        '- Conservative canonical event candidates: '+str(data['event_candidate_count']),
        '',
        '## Source articles',
        '',
    ]
    for n,a in enumerate(data['articles'],1):
        lines.extend([
            '### '+str(n)+'. '+clean(a['headline_zh']),
            '- Original headline: '+clean(a['headline_original']),
            '- Source: '+clean(a['source']),
            '- Original URL: '+clean(a['source_url']),
            '- Source-reported: '+clean(a['source_reported_at']),
            '- Observed by the system: '+clean(a['observed_at']),
            '- Recorded: '+clean(a['recorded_at']),
            '- Verification: '+clean(a['verification_status']),
            '- Category: '+clean(a['event_family']),
            '',
        ])
    lines.extend(['## Event candidates', ''])
    for n,e in enumerate(data['event_candidates'],1):
        lines.extend([
            '### Candidate '+str(n)+': '+clean(e['event_title']),
            '- ID: '+clean(e['event_id']),
            '- Verification: '+clean(e['verification_status']),
            '- Official evidence: '+clean(e['official_evidence_status']),
            '- Linked article count: '+clean(e['article_count']),
            '',
        ])
    lines.extend([
        '## Interpretation limits',
        '',
        '- A news discovery headline is not proof of a specific official proposition.',
        '- An event candidate is not an independently verified event.',
        '- Missing official evidence, historical replay, or market snapshots must not be inferred.',
        '- No automated capture, persistence writer, paper trading, or live trading runs in this preview.',
        '- For complete reference IDs, rights metadata, and research status see the original web interface and its public API.',
        '',
    ])
    return ('\n'.join(lines)).encode('utf-8')

# Only fixed, reviewed categories may reach startup logs. Never print exception text.
STARTUP_CODES=frozenset(('CONFIG_REQUIRED_OFF','CONFIG_UNEXPECTED_RUNTIME','CONFIG_CREDENTIALS','USERNAME_INVALID','PASSWORD_MISSING','PASSWORD_LENGTH_INVALID','PASSWORD_CONTROL_CHARACTER','CONFIG_BIND','CONFIG_LOOPBACK','CONFIG_INVALID','MANIFEST_READ','MANIFEST_INVALID','PACKAGE_INVENTORY','PACKAGE_HASH','PUBLIC_DATA_INVALID','PACKAGE_READ','READONLY_GUARD_FAILED','BIND_FAILED'))
class StartupRejected(ValueError):
 def __init__(self,code):self.code=code if code in STARTUP_CODES else 'CONFIG_INVALID';super().__init__(self.code)
def startup_rejected(code):
 safe=code if code in STARTUP_CODES else 'CONFIG_INVALID'
 sys.stderr.write('FRIENDS_STARTUP_REJECTED category='+safe+'\n');return 2
def configuration():
 if os.environ.get('FRIENDS_PREVIEW_MODE')!='1' or os.environ.get('RADAR_DEMO_MODE')!='1' or any(os.environ.get(k)!='0' for k in OFF):raise StartupRejected('CONFIG_REQUIRED_OFF')
 # Legacy optional aliases must not create even an apparent live capability.
 if any(v.strip() not in ('','0') for k,v in os.environ.items() if (k.startswith('RADAR_LIVE_') and k not in OFF) or k.startswith(('GLOBAL_EVENT_RADAR_','CLOUDFLARE_','BROKER_','PAPER_TRADING','LIVE_TRADING'))):raise StartupRejected('CONFIG_UNEXPECTED_RUNTIME')
 host=os.environ.get('HOST','0.0.0.0')
 try:port=int(os.environ.get('PORT','8765'))
 except (ValueError,TypeError):raise StartupRejected('CONFIG_BIND') from None
 if host not in ('0.0.0.0','127.0.0.1') or not 1<=port<=65535:raise StartupRejected('CONFIG_BIND')
 local=os.environ.get('FRIENDS_ALLOW_LOOPBACK_HTTP','0')=='1'
 if local and (host!='127.0.0.1' or os.environ.get('RENDER')):raise StartupRejected('CONFIG_LOOPBACK')
 return host,port,local
def verify_package():
 try:raw=(ROOT/'FRIENDS_PACKAGE_MANIFEST.json').read_text(encoding='utf-8')
 except OSError:raise StartupRejected('MANIFEST_READ') from None
 try:
  m=json.loads(raw)
  if not isinstance(m,dict) or not isinstance(m.get('files'),dict):raise ValueError()
 except (ValueError,TypeError):raise StartupRejected('MANIFEST_INVALID') from None
 expected=set(m['files'])|{'FRIENDS_PACKAGE_MANIFEST.json'}
 actual={p.relative_to(ROOT).as_posix() for p in ROOT.rglob('*') if p.is_file() and '.git' not in p.relative_to(ROOT).parts}
 if expected!=actual:raise StartupRejected('PACKAGE_INVENTORY')
 for name,digest in m['files'].items():
  p=ROOT/name
  if p.resolve().is_relative_to(ROOT.resolve()) is False or p.is_symlink() or hashlib.sha256(p.read_bytes()).hexdigest()!=digest:raise StartupRejected('PACKAGE_HASH')
 views={(profile,window):json.loads((ROOT/'data'/(profile+'_'+window+'.json')).read_text(encoding='utf-8')) for profile in ('public','baseline') for window in ('48','168')}
 for v in views.values():
  if v.get('data_scope')!='FRIENDS_PREVIEW_SAVED_PUBLIC_METADATA' or any(i.get('local_observation',{}).get('public_usage')!='PUBLIC_ELIGIBLE' for i in v['items']):raise StartupRejected('PUBLIC_DATA_INVALID')
 return views
def install_readonly_guard():
 def audit(event,args):
  if event in ('socket.connect','socket.getaddrinfo','socket.gethostbyname','socket.gethostbyaddr','socket.getnameinfo','sqlite3.connect','subprocess.Popen','os.system','os.fork','os.posix_spawn','os.remove','os.rename','os.mkdir','os.rmdir','os.chmod','os.truncate','os.link','os.symlink'):raise PermissionError('FRIENDS_RUNTIME_OPERATION_DISABLED')
  if event=='open':
   mode=args[1];flags=args[2]
   if (isinstance(mode,str) and any(x in mode for x in 'wax+')) or (isinstance(flags,int) and flags & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND)):raise PermissionError('FRIENDS_RUNTIME_WRITE_DISABLED')
 sys.addaudithook(audit)
class Server(ThreadingHTTPServer):
 daemon_threads=True;request_queue_size=16
 def __init__(self,*a,**kw):self.slots=threading.BoundedSemaphore(16);super().__init__(*a,**kw)
 def process_request(self,request,address):
  if not self.slots.acquire(False):self.shutdown_request(request);return
  try:super().process_request(request,address)
  except BaseException:self.slots.release();raise
 def process_request_thread(self,*a):
  try:super().process_request_thread(*a)
  finally:self.slots.release()
 def handle_error(self,*a):sys.stderr.write('FRIENDS_REQUEST_FAILED\n')
class Handler(BaseHTTPRequestHandler):
 server_version='MacroRadarFriends';sys_version='';protocol_version='HTTP/1.0'
 def setup(self):super().setup();self.connection.settimeout(10)
 def log_request(self,code='-',size='-'):sys.stderr.write('friends_preview request status='+str(code)+'\n') # no headers, URL, user, IP or password
 def log_message(self,*args):pass
 def log_error(self,*args):sys.stderr.write('FRIENDS_HTTP_ERROR\n')
 def reply(self,code,payload,content='application/json; charset=utf-8',challenge=False):
  data=payload if isinstance(payload,bytes) else json.dumps(payload,ensure_ascii=False).encode('utf-8')
  self.send_response(code);self.send_header('Content-Type',content);self.send_header('Content-Length',str(len(data)))
  for k,v in {'Cache-Control':'no-store, private, max-age=0','Pragma':'no-cache','Vary':'Authorization','X-Robots-Tag':'noindex, nofollow, noarchive','X-Content-Type-Options':'nosniff','X-Frame-Options':'DENY','Referrer-Policy':'no-referrer','Content-Security-Policy':"default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"}.items():
   if k=='X-Robots-Tag' and self.path.split('?',1)[0] in ('/llms.txt','/llm/events.md','/llm/events.json'):continue
   self.send_header(k,v)
  if content.startswith('text/html'):self.send_header('Link','</llms.txt>; rel="alternate"; type="text/plain"')
  if self.headers.get('X-Forwarded-Proto')=='https':self.send_header('Strict-Transport-Security','max-age=86400')
  self.end_headers()
  if self.command!='HEAD':self.wfile.write(data)
 def send_error(self,code,message=None,explain=None):self.reply(code,{'error':'REQUEST_REJECTED'})
 def authenticated(self):
  if not self.server.loopback_http and self.headers.get('X-Forwarded-Proto')!='https':self.reply(426,{'error':'HTTPS_REQUIRED'});return False
  return True
 def do_GET(self):
  try:
   if len(self.path)>4096:self.reply(414,{'error':'REQUEST_TOO_LONG'});return
   u=urlsplit(self.path)
   if u.path=='/healthz' and not u.query and self.command in ('GET','HEAD'):self.reply(200,{'status':'ok'});return
   if not self.authenticated():return
   if self.command not in ('GET','HEAD'):self.reply(405,{'error':'READ_ONLY_PREVIEW'});return
   if u.path in ('/llms.txt','/llm/events.md','/llm/events.json'):
    preview_query(u.query)
    if u.path=='/llms.txt':self.reply(200,LLM_INDEX.encode('utf-8'),'text/plain; charset=utf-8')
    elif u.path=='/llm/events.md':self.reply(200,llm_markdown(llm_snapshot(self.server.views)),'text/markdown; charset=utf-8')
    else:self.reply(200,llm_snapshot(self.server.views))
   elif u.path in ('/','/feed'):
    self.options(u.query);self.reply(200,(ROOT/'ui/radar_public_showcase_v1.html').read_bytes(),'text/html; charset=utf-8')
   elif u.path in ASSETS and not u.query:self.reply(200,(ROOT/u.path.lstrip('/')).read_bytes(),'text/css; charset=utf-8' if u.path.endswith('.css') else 'text/javascript; charset=utf-8')
   elif u.path=='/api/app/radar':
    profile,window=self.options(u.query);self.reply(200,self.server.views[(profile,window)])
   elif u.path in ('/api/app/replay','/api/app/research'):self.reply(503,{'error':'INTELLIGENCE_REPLAY_UNAVAILABLE','read_only':True})
   elif u.path=='/api/app/source-rights' and not u.query:self.reply(200,(ROOT/'data/SOURCE_RIGHTS.json').read_bytes())
   elif u.path=='/robots.txt' and not u.query:self.reply(200,b'User-agent: *\nAllow: /\n','text/plain; charset=utf-8')
   elif u.path=='/favicon.ico':self.reply(204,b'','image/x-icon')
   else:self.reply(404,{'error':'PREVIEW_ROUTE_UNAVAILABLE'})
  except ValueError:self.reply(400,{'error':'INVALID_PREVIEW_REQUEST'})
  except (OSError,KeyError):self.reply(503,{'error':'PREVIEW_UNAVAILABLE','read_only':True})
 def options(self,query):
  q=preview_query(query,('profile','window'))
  profile=q.get('profile',['public'])[0];window=q.get('window',['168'])[0]
  if profile not in ('public','baseline') or window not in ('48','168'):raise ValueError()
  return profile,window
 do_HEAD=do_GET
 do_POST=do_GET
 do_PUT=do_GET
 do_PATCH=do_GET
 do_DELETE=do_GET
 do_OPTIONS=do_GET
 do_TRACE=do_GET
 do_CONNECT=do_GET
def main():
 try:host,port,local=configuration()
 except StartupRejected as exc:return startup_rejected(exc.code)
 except Exception:return startup_rejected('CONFIG_INVALID')
 try:views=verify_package()
 except StartupRejected as exc:return startup_rejected(exc.code)
 except Exception:return startup_rejected('PACKAGE_READ')
 try:install_readonly_guard()
 except Exception:return startup_rejected('READONLY_GUARD_FAILED')
 try:
  server=Server((host,port),Handler);server.loopback_http=local;server.views=views
 except Exception:return startup_rejected('BIND_FAILED')
 sys.stderr.write('FRIENDS_PREVIEW_READY_SAVED_READ_ONLY\n')
 try:server.serve_forever()
 except KeyboardInterrupt:pass
 finally:server.server_close()
 return 0
if __name__=='__main__':raise SystemExit(main())
