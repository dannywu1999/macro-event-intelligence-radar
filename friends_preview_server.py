"""Public read-only saved metadata preview. No production entry point, store or collector."""
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlsplit,parse_qs
import hashlib,json,os,sys,threading
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parent
OFF=('RADAR_LIVE_ECB','RADAR_LIVE_EIA','RADAR_LIVE_GUARDIAN','RADAR_LIVE_MARKET_WATCH','RADAR_LIVE_NEWS','RADAR_LIVE_UN_NEWS','RADAR_NEWS_CAPTURE','RADAR_PERSIST_INTELLIGENCE')
ASSETS={'/ui/'+n for n in ('radar_product_workbench.js','radar_product_workbench.css','radar_headline_presentation.js')}

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
  for k,v in {'Cache-Control':'no-store, private, max-age=0','Pragma':'no-cache','Vary':'Authorization','X-Robots-Tag':'noindex, nofollow, noarchive','X-Content-Type-Options':'nosniff','X-Frame-Options':'DENY','Referrer-Policy':'no-referrer','Content-Security-Policy':"default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"}.items():self.send_header(k,v)
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
   if u.path in ('/','/feed'):
    self.options(u.query);self.reply(200,(ROOT/'ui/radar_public_showcase_v1.html').read_bytes(),'text/html; charset=utf-8')
   elif u.path in ASSETS and not u.query:self.reply(200,(ROOT/u.path.lstrip('/')).read_bytes(),'text/css; charset=utf-8' if u.path.endswith('.css') else 'text/javascript; charset=utf-8')
   elif u.path=='/api/app/radar':
    profile,window=self.options(u.query);self.reply(200,self.server.views[(profile,window)])
   elif u.path in ('/api/app/replay','/api/app/research'):self.reply(503,{'error':'INTELLIGENCE_REPLAY_UNAVAILABLE','read_only':True})
   elif u.path=='/api/app/source-rights' and not u.query:self.reply(200,(ROOT/'data/SOURCE_RIGHTS.json').read_bytes())
   elif u.path=='/robots.txt' and not u.query:self.reply(200,b'User-agent: *\nDisallow: /\n','text/plain; charset=utf-8')
   elif u.path=='/favicon.ico':self.reply(204,b'','image/x-icon')
   else:self.reply(404,{'error':'PREVIEW_ROUTE_UNAVAILABLE'})
  except ValueError:self.reply(400,{'error':'INVALID_PREVIEW_REQUEST'})
  except (OSError,KeyError):self.reply(503,{'error':'PREVIEW_UNAVAILABLE','read_only':True})
 def options(self,query):
  q=parse_qs(query,keep_blank_values=True,max_num_fields=2)
  if set(q)-{'profile','window'} or any(len(v)!=1 for v in q.values()):raise ValueError()
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
