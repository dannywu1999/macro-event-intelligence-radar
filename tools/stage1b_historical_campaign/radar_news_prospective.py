"""Explicit bounded public-source pilot; existing append-only IntelligenceStore.

No import-time acquisition, recorder, authoritative freeze, or production opt-in.
Only title/link/time/attribution metadata is retained; source response bytes are
hashed in memory and discarded. One OS lock owns one isolated pilot namespace.
"""
from __future__ import annotations
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import argparse, hashlib, json, os, re, signal, subprocess, sys, tempfile
import threading, time, unicodedata, uuid
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
import xml.etree.ElementTree as ET
from .radar_intelligence_store import IntelligenceStore, StoreError, canonical, now, time_value
from .radar_news_freshness import timestamp
from .global_event_radar_read_adapter import build_canonical_events, normalize_news_text

CONTRACT='NEWS_PROSPECTIVE_V47'
MODULE='tools.stage1b_historical_campaign.radar_news_prospective'
SCOPE='ISOLATED_LOCAL_PILOT'
SOURCE_ROOT=Path(__file__).resolve().parents[2]
PROVIDERS={
 'ECB Press':dict(endpoint='https://www.ecb.europa.eu/rss/press.html',host='www.ecb.europa.eu',rights='OFFICIAL_LINK_TITLE_DISCOVERY;NO_ARTICLE_REPUBLICATION'),
 'Global Voices':dict(endpoint='https://globalvoices.org/feed/',host='globalvoices.org',rights='CC_BY_3_0;RETAIN_AUTHOR_AND_ORIGINAL_LINK',license='https://creativecommons.org/licenses/by/3.0/'),
 'EIA Today in Energy':dict(endpoint='https://www.eia.gov/rss/todayinenergy.xml',host='www.eia.gov',rights='US_GOVERNMENT_TITLE_LINK_DISCOVERY;NO_THIRD_PARTY_REUSE_ASSUMED'),
}
MAX_ROWS=20000
MIN_INTERVAL=1800

def digest(value):
 return hashlib.sha256(canonical(value).encode('utf8')).hexdigest()

def normalized_url(value):
 """Strip documented tracking keys only; semantic query parameters remain."""
 try:
  u=urlsplit(value)
  if u.scheme!='https' or not u.hostname or u.username or u.password or u.port not in (None,443):raise ValueError()
  query=[(k,v) for k,v in parse_qsl(u.query,keep_blank_values=True)
   if not k.lower().startswith('utm_') and k.lower() not in {'fbclid','gclid','mc_cid','mc_eid'}]
  return urlunsplit(('https',u.hostname.lower(),u.path or '/',urlencode(query),''))
 except (TypeError,ValueError):raise StoreError('INVALID_PUBLIC_ARTICLE_URL') from None

def article_identity(url):
 return 'article-url-v47-'+hashlib.sha256(normalized_url(url).encode()).hexdigest()

def title_key(value):
 text=unicodedata.normalize('NFKC',normalize_news_text(value) or '')
 return ' '.join(text.translate(str.maketrans({'’':"'",'‘':"'",'“':'"','”':'"','–':'-','—':'-'})).split())

def content_identity(article):
 return 'news-content-v47-'+digest(dict(title=title_key(article.get('title')),url=normalized_url(article['news_source']['url']),
  publisher=article['news_source']['name'],published=article.get('source_published_at'),
  precision=article.get('source_timestamp_precision')))

def source_time(value):
 if not value:return None,'UNKNOWN'
 if re.fullmatch(r'\d{4}-\d{2}-\d{2}',value):
  try:datetime.strptime(value,'%Y-%m-%d')
  except ValueError:return None,'UNKNOWN'
  return value,'DATE_ONLY'
 try:
  try:dt=parsedate_to_datetime(value)
  except (TypeError,ValueError,IndexError):dt=datetime.fromisoformat(value.replace('Z','+00:00'))
  if dt.tzinfo is None:return None,'UNKNOWN'
  precision='SECOND' if re.search(r'\d{2}:\d{2}:\d{2}',value) else 'MINUTE' if re.search(r'\d{2}:\d{2}',value) else 'UNKNOWN'
  return dt.astimezone(timezone.utc).isoformat().replace('+00:00','Z'),precision
 except (TypeError,ValueError,OverflowError):return None,'UNKNOWN'

def parse_source(provider,data,retrieved):
 """Use the existing source eligibility/parsing contracts, retaining precision."""
 if provider not in PROVIDERS:raise StoreError('UNAPPROVED_SOURCE')
 from .eia_live_ingestion import parse_rss as eia
 from .ecb_live_ingestion import parse_rss as ecb
 from .broad_news_ingestion import parse_rss as broad
 rows=(ecb(data,retrieved) if provider=='ECB Press' else eia(data,retrieved) if provider=='EIA Today in Energy' else broad(data,retrieved,source=provider))
 dates={};titles={};aliases={}
 for item in ET.fromstring(data).findall('./channel/item'):
  link=(item.findtext('link') or '').strip()
  try:
   key=normalized_url(link);date=source_time((item.findtext('pubDate') or '').strip())
   title=normalize_news_text(item.findtext('title'))
   if key in dates and (dates[key]!=date or title_key(titles[key])!=title_key(title)):raise StoreError('CONFLICTING_FEED_COPIES')
   dates[key]=date;titles[key]=min(titles.get(key) or title or '',title or '')
   aliases.setdefault(key,[]).append(link)
  except StoreError as error:
   if str(error)=='CONFLICTING_FEED_COPIES':raise
   continue
 articles={}
 for row in sorted(rows,key=lambda r:(r['source_url'],r['headline_or_text'])):
  url=normalized_url(row['source_url'])
  if urlsplit(url).hostname!=PROVIDERS[provider]['host'] and not (provider=='EIA Today in Energy' and urlsplit(url).hostname=='eia.gov'):
   raise StoreError('SOURCE_HOST_MISMATCH')
  published,precision=dates.get(url,(None,'UNKNOWN'))
  exact=published if precision in {'SECOND','MINUTE'} else None
  a=dict(article_reference=url,title=titles.get(url) or normalize_news_text(row['headline_or_text']),news_summary=None,
   news_source=dict(name=row['source_name'],url=url),reported_at=exact,
   reported_time_kind='REPORTED_TIME' if exact else 'SOURCE_DATE_PROXY' if precision=='DATE_ONLY' else 'UNKNOWN',
   source_published_at=published,source_timestamp_precision=precision,publication_precision=precision,
   verification_status='UNVERIFIED_NEWS',observed_at=retrieved,discovered_at=retrieved,
   article_identity=article_identity(url),provider=provider,rights=PROVIDERS[provider]['rights'],
   url_identity_evidence=dict(rule='EXACT_URL_WITH_KNOWN_TRACKING_KEYS_REMOVED',input_urls=sorted(set(aliases.get(url,[url]))),canonical_url=url),
   observation_time_basis='FIRST_RECORDED_SOURCE_OBSERVATION')
  a['content_version_identity']=content_identity(a)
  if url in articles and articles[url]['content_version_identity']!=a['content_version_identity']:
   raise StoreError('CONFLICTING_FEED_COPIES')
  articles[url]=a
 if len(articles)>1000:raise StoreError('ARTICLE_BOUND_EXCEEDED')
 return list(articles.values()),getattr(rows,'diagnostics',dict(accepted_item_count=len(articles)))

def fetch_worker(provider):
 """Transport only. Parent imposes a hard wall deadline and owns persistence."""
 from .ecb_live_ingestion import fetch_ecb
 from .eia_live_ingestion import fetch_eia
 from .broad_news_ingestion import fetch_rss
 return fetch_ecb() if provider=='ECB Press' else fetch_eia() if provider=='EIA Today in Energy' else fetch_rss(provider)

class FetchError(StoreError):
 def __init__(self,code,request_started):
  super().__init__(code);self.request_started=request_started

def bounded_fetch(provider):
 # Sequential transient child is necessary for a hard DNS/socket deadline on
 # Windows. It has no ledger access, collector identity, retries or checkpoints.
 try:
  p=subprocess.run([sys.executable,'-B','-m',MODULE,'--fetch-worker',provider],
   cwd=SOURCE_ROOT,capture_output=True,timeout=22)
 except subprocess.TimeoutExpired as error:raise FetchError('PROVIDER_WALL_TIMEOUT',b'FETCH_STARTED' in (error.stderr or b'')) from None
 if p.returncode:
  started=b'FETCH_STARTED' in p.stderr
  error=p.stderr.decode('ascii','replace').strip().splitlines()[-1] if p.stderr else ''
  raise FetchError(error if started and re.fullmatch(r'[A-Z_0-9]{1,80}',error) else 'WORKER_BOOTSTRAP_FAILED',started)
 if len(p.stdout)>2*1024*1024:raise StoreError('RESPONSE_TOO_LARGE')
 return p.stdout

@contextmanager
def owner_lock(root):
 path=root/'runner.lock';handle=path.open('a+b')
 if path.stat().st_size==0:handle.write(b'0');handle.flush()
 handle.seek(0)
 try:
  try:
   if os.name=='nt':
    import msvcrt;msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
   else:
    import fcntl;fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
  except OSError:raise StoreError('DUPLICATE_PILOT_RUNNER') from None
  yield
 finally:
  handle.close() # OS releases ownership even after termination.

def ledger_rows(store,as_of=None):
 if hasattr(store,'news_capture_rows'):return store.news_capture_rows(as_of)
 limit=time_value(as_of or now())[1]
 with store.connection() as db:
  store._schema(db)
  rows=db.execute('SELECT * FROM observations WHERE observed_us<=? ORDER BY observed_us,observation_id LIMIT ?', (limit,MAX_ROWS+1)).fetchall()
 if len(rows)>MAX_ROWS:raise StoreError('PILOT_READ_BOUND_EXCEEDED')
 return [store.decode(r) for r in rows if json.loads(r['provenance']).get('input_contract')==CONTRACT]

def state_from_rows(rows):
 articles={};seen={};providers={};attempts={};receipts={};events={};official={}
 for r in rows:
  p=r['payload'];kind=r['observation_kind'];entity=r['entity_id']
  if kind=='NEWS_ARTICLE':articles[entity]=r
  elif kind=='CANONICAL_EVENT_STATE':events[entity]=r
  elif kind=='OFFICIAL_EVIDENCE':official[entity]=r
  elif kind=='SOURCE_STATE':
   if p.get('record_type')=='SEEN':seen[p['article_reference']]=r
   elif p.get('record_type')=='PROVIDER':providers[p['provider']]=r
   elif p.get('record_type')=='ATTEMPT':attempts[p['attempt_id']]=r
   elif p.get('record_type')=='RECEIPT':receipts[p['receipt_id']]=r
 return dict(articles=articles,seen=seen,providers=providers,attempts=attempts,receipts=receipts,events=events,official=official)

def record(kind,entity,payload,event=None,source=None):
 return dict(observation_kind=kind,entity_id=entity,canonical_event_id=event,payload=payload,source_timestamp=source,
  provenance=dict(input_contract=CONTRACT,time_basis='SYSTEM_RECORDED_TIME',scope=SCOPE))

def atomic_json(path,value):
 data=(canonical(value)+'\n').encode('utf8')
 temp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
 with temp.open('xb') as f:f.write(data);f.flush();os.fsync(f.fileno())
 try:os.replace(temp,path)
 finally:temp.unlink(missing_ok=True)

class ProspectiveRunner:
 def __init__(self,root,*,providers=('ECB Press','Global Voices'),interval=1800,max_requests=56,initialize=False,clock=now,fetcher=bounded_fetch):
  requested=Path(root).expanduser()
  if requested.is_symlink() or any(p.is_symlink() for p in requested.parents):raise StoreError('SYMLINK_STORAGE_REJECTED')
  self.root=requested.resolve();self.providers=tuple(providers);self.scope=getattr(self,'scope',SCOPE)
  if (not self.providers or len(set(self.providers))!=len(self.providers) or any(p not in PROVIDERS for p in self.providers)
      or type(interval)!=int or interval<MIN_INTERVAL or type(max_requests)!=int or not 1<=max_requests<=60):raise StoreError('INVALID_PILOT_CONFIG')
  if self.root.is_relative_to(SOURCE_ROOT) or self.root.is_relative_to(Path(tempfile.gettempdir()).resolve()):raise StoreError('NON_DURABLE_OR_SOURCE_ROOT_REJECTED')
  if self.root.is_symlink() or any(p.is_symlink() for p in self.root.parents):raise StoreError('SYMLINK_STORAGE_REJECTED')
  self.interval,self.max_requests,self.clock,self.fetcher=interval,max_requests,clock,fetcher
  self.stop=threading.Event();self.config=dict(contract=CONTRACT,scope=self.scope,providers=list(providers),interval=interval,max_requests=max_requests,storage_claim='LOCAL_RESTART_ONLY;NOT_CLOUD_DURABILITY')
  marker=self.root/'V47_PILOT.json'
  if initialize:
   if self.root.exists():raise StoreError('INITIALIZE_REQUIRES_NEW_ROOT')
   self.root.mkdir(parents=True)
   atomic_json(marker,self.config)
   IntelligenceStore(self.root/'evidence.sqlite3',create=True)
  if not marker.is_file() or json.loads(marker.read_bytes())!=self.config:raise StoreError('PILOT_CONFIG_OR_STORAGE_UNAVAILABLE')
  self.store=IntelligenceStore(self.root/'evidence.sqlite3')
  self.result=[]

 def recover(self):
  state=state_from_rows(self.state_rows())
  # Any durable attempt without a terminal receipt is retained as uncertain.
  for r in state['attempts'].values():
   p=r['payload']
   if p.get('outcome')=='RESERVED':
    interrupted={**p,'outcome':'INTERRUPTED_UNKNOWN'}
    self.store.append([self.record('SOURCE_STATE',r['entity_id'],interrupted)],observed_at=self.clock())
  self.publish_checkpoint()

 def publish_checkpoint(self):
  rows=self.state_rows();state=state_from_rows(rows)
  directory=self.root/'receipts';directory.mkdir(exist_ok=True)
  for receipt_id,row in state['receipts'].items():
   data=(canonical(row['payload'])+'\n').encode('utf8');path=directory/(receipt_id+'.json')
   if path.exists():
    if path.read_bytes()!=data:raise StoreError('RECEIPT_FILE_INTEGRITY_FAILED')
   else:
    with path.open('xb') as f:f.write(data);f.flush();os.fsync(f.fileno())
  news=[]
  for ref,r in sorted(state['articles'].items()):
   a=r['payload']
   news.append(dict(article_reference=ref,headline_or_text=a['title'],source_name=a['news_source']['name'],source_url=a['news_source']['url'],
    source_published_at=a['reported_at'],event_time=a['reported_at'],observed_time=a['observed_at']))
  atomic_json(self.root/'CURRENT_NEWS.json',news)
  atomic_json(self.root/'checkpoint.json',dict(contract=CONTRACT,scope=self.scope,checkpointed_at=self.clock(),
   request_count=len(state['attempts']),articles=len(state['articles']),receipt_count=len(state['receipts']),
   source_states={p:r['payload'] for p,r in state['providers'].items()},last_seen={ref:r['payload']['last_seen_at'] for ref,r in state['seen'].items()},
   ledger_observation_count=len(rows),authoritative_freezes=0,read_model_basis='DERIVED_FROM_APPEND_ONLY_LEDGER'))

 def provider_once(self,provider):
  state=state_from_rows(self.state_rows());checked=self.clock()
  previous=state['providers'].get(provider,{}).get('payload',{})
  attempts=[r for r in state['attempts'].values() if r['payload']['provider']==provider and r['payload'].get('outcome')!='CLIENT_LAUNCH_FAILED']
  latest=max((timestamp(r['payload']['provider_checked_at']) for r in attempts),default=None)
  current=timestamp(checked)
  if latest and (current-latest).total_seconds()<self.interval:return dict(provider=provider,status='NOT_DUE',requests=0)
  reservation=self.reserve_attempt(provider,checked,state)
  if reservation is None:return dict(provider=provider,status='REQUEST_BUDGET_EXHAUSTED',requests=0)
  attempt_id,attempt=reservation
  self.publish_checkpoint() # Reservation survives process termination.
  try:
   raw=self.fetcher(provider);retrieved=self.clock()
   articles,diagnostics=parse_source(provider,raw,retrieved)
   recorded=self.clock()
   if not timestamp(checked)<=timestamp(retrieved)<=timestamp(recorded):raise StoreError('SYSTEM_CLOCK_ORDER_INVALID')
   receipt=dict(record_type='RECEIPT',contract=CONTRACT,scope=self.scope,attempt_id=attempt_id,provider=provider,
    source_url=PROVIDERS[provider]['endpoint'],provider_checked_at=checked,retrieved_at=retrieved,recorded_at=recorded,
    http_status=200,response_sha256=hashlib.sha256(raw).hexdigest(),response_bytes=len(raw),rights=PROVIDERS[provider],
    retained_scope='TITLE_LINK_TIME_ATTRIBUTION_ONLY',selected=[{k:a[k] for k in ['title','news_source','source_published_at','source_timestamp_precision','article_identity','content_version_identity','url_identity_evidence']} for a in articles],diagnostics=diagnostics)
   receipt['receipt_id']='source-receipt-v47-'+digest(receipt)
   fresh_news={ref:deepcopy(r['payload']) for ref,r in state['articles'].items()}
   records=[];new=updated=duplicates=0
   for a in articles:
    ref=a['article_reference'];prior=state['articles'].get(ref)
    same=prior and prior['payload']['content_version_identity']==a['content_version_identity']
    if prior:
     a['observed_at']=prior['payload']['observed_at'];a['discovered_at']=a['observed_at']
    a['detection_evidence']=dict(contract=CONTRACT,scope=self.scope,article_identity=a['article_identity'],
     content_version_identity=a['content_version_identity'],source_receipt_identity=receipt['receipt_id'],
     actual_observation_identity=attempt_id,source_published_at=a['source_published_at'],source_timestamp_precision=a['source_timestamp_precision'],
     provider_checked_at=checked,retrieved_at=retrieved,first_observed_at=a['observed_at'],first_observed_proven=True,
     recorded_at=recorded,last_seen_at=retrieved,version_observed_at=retrieved)
    if same:duplicates+=1
    elif prior:updated+=1;fresh_news[ref]=a
    else:new+=1;fresh_news[ref]=a
    seen=dict(record_type='SEEN',scope=self.scope,article_reference=ref,article_identity=a['article_identity'],
     source_receipt_identity=receipt['receipt_id'],actual_observation_identity=attempt_id,last_seen_at=retrieved,provider_checked_at=checked,retrieved_at=retrieved,recorded_at=recorded)
    records.append(self.record('SOURCE_STATE','v47:seen:'+a['article_identity'],seen))
   if len(fresh_news)>2000:raise StoreError('PILOT_RETENTION_BOUND_EXCEEDED')
   event_view=build_canonical_events(list(fresh_news.values()))
   membership={ref:e['event_id'] for e in event_view['events'] for ref in e['article_references']}
   for a in articles:
    ref=a['article_reference'];prior=state['articles'].get(ref)
    if not prior or prior['payload']['content_version_identity']!=a['content_version_identity']:
     records.append(self.record('NEWS_ARTICLE',ref,a,membership.get(ref),a['reported_at']))
   for event in event_view['events']:
    records.append(self.record('CANONICAL_EVENT_STATE',event['event_id'],event,event['event_id']))
   source=dict(record_type='PROVIDER',provider=provider,scope=self.scope,status='LIVE',last_attempt_at=checked,last_success_at=retrieved,
    refresh_interval_seconds=self.interval,article_count=sum(a['provider']==provider for a in fresh_news.values()),new_article_count=new,
    updated_article_count=updated,duplicate_article_count=duplicates,reason=None,last_successful_cycle=diagnostics,runner_mode='BOUNDED_EXPLICIT_PILOT;NOT_ALWAYS_ON')
   terminal={**attempt,'outcome':'SUCCESS','external_request_started':True}
   records.extend([self.record('SOURCE_STATE','v47:receipt:'+receipt['receipt_id'],receipt),self.record('SOURCE_STATE','v47:provider:'+provider,source),self.record('SOURCE_STATE','v47:attempt:'+attempt_id,terminal)])
   self.store.append(records,observed_at=recorded)
   self.publish_checkpoint()
   return dict(provider=provider,status='SUCCESS',requests=1,new_articles=new,updated=updated,duplicates=duplicates,receipt_id=receipt['receipt_id'])
  except Exception as error:
   if isinstance(error,PermissionError) or (isinstance(error,StoreError) and
      (str(error).startswith(('STORE_','RECEIPT_','OBSERVATION_','BACKDATED_','CONFLICTING_SAME_TIME','FUTURE_INPUT')))):
    raise
   from .eia_live_ingestion import failure_reason
   code=str(error) if isinstance(error,StoreError) and re.fullmatch(r'[A-Z_0-9]{1,80}',str(error)) else failure_reason(error)
   recorded=self.clock();source={**previous,'record_type':'PROVIDER','provider':provider,'scope':self.scope,
    'status':'LAST_VALID_FALLBACK' if any(a['payload']['provider']==provider for a in state['articles'].values()) else 'UNAVAILABLE',
    'last_attempt_at':checked,'last_success_at':previous.get('last_success_at'),'refresh_interval_seconds':self.interval,
    'new_article_count':0,'reason':code,'runner_mode':'BOUNDED_EXPLICIT_PILOT;NOT_ALWAYS_ON'}
   started=getattr(error,'request_started',True)
   self.store.append([self.record('SOURCE_STATE','v47:provider:'+provider,source),self.record('SOURCE_STATE','v47:attempt:'+attempt_id,{**attempt,'outcome':'FAILED' if started else 'CLIENT_LAUNCH_FAILED','external_request_started':started,'error':code})],observed_at=recorded)
   self.publish_checkpoint()
   return dict(provider=provider,status='FAILED',requests=1,error=code)

 def run(self,cycles=1,only=None):
  if type(cycles)!=int or not 1<=cycles<=4:raise StoreError('BOUNDED_CYCLES_REQUIRED')
  selected=self.providers if only is None else tuple(only)
  if not selected or any(p not in self.providers for p in selected):raise StoreError('UNCONFIGURED_SOURCE_SELECTION')
  with owner_lock(self.root):
   self.recover()
   for cycle in range(cycles):
    for provider in selected:
     if self.stop.is_set():break
     self.result.append(self.provider_once(provider))
    if self.stop.is_set() or cycle==cycles-1:break
    self.stop.wait(self.interval)
   self.publish_checkpoint()
  return self.result

 def state_rows(self):return ledger_rows(self.store)
 def record(self,*args,**kwargs):
  row=record(*args,**kwargs);row['provenance']['scope']=self.scope;return row
 def reserve_attempt(self,provider,checked,state):
  if len(state['attempts'])>=self.max_requests:return None
  attempt_id='attempt-v47-'+uuid.uuid4().hex
  attempt=dict(record_type='ATTEMPT',attempt_id=attempt_id,provider=provider,provider_checked_at=checked,outcome='RESERVED',scope=self.scope)
  self.store.append([self.record('SOURCE_STATE','v47:attempt:'+attempt_id,attempt)],observed_at=checked)
  return attempt_id,attempt

def triage(article,event_id=None,as_of=None,proof=None):
 current=timestamp(as_of or now());published=timestamp(article.get('reported_at'))
 age=(current-published).total_seconds() if published else None
 freshness='UNKNOWN' if age is None else 'INVALID_FUTURE' if age<0 else 'FRESH_48H' if age<=172800 else 'SOURCE_STALE'
 title=article.get('title') or ''
 high=bool(re.search(r'\b(?:cuts|raises|hikes|lowers) (?:interest )?rates\b|\b(?:imposes|announces|introduces) (?:new )?(?:tariffs|sanctions)\b|\b(?:invasion|bank failure|sovereign default|supply disruption)\b',title,re.I))
 importance='HIGH' if high else 'NORMAL'
 eligible=bool(proof and proof.get('first_observed_proven') and proof.get('status')!='CAPTURED_EARLIER_VERSION' and event_id and article.get('news_source',{}).get('url'))
 priority='STALE_SOURCE_ARTICLE' if freshness=='SOURCE_STALE' else 'INSUFFICIENT_EVIDENCE' if freshness!='FRESH_48H' else 'HIGH_PRIORITY_RESEARCH' if high and eligible else 'NORMAL_RESEARCH'
 return dict(priority=priority,event_importance=importance,source_freshness=freshness,
  high_priority_eligible=high and eligible and freshness=='FRESH_48H',
  factors=['EXPLICIT_EVENT_ACTION' if high else 'TOPIC_RESEARCH_ONLY',freshness,'DURABLE_FIRST_OBSERVATION' if eligible else 'FIRST_OBSERVATION_NOT_PROVEN'],
  authority='RESEARCH_TRIAGE_ONLY;NO_TRADING_SIGNAL')

def attach_detection(view,store=None,*,as_of=None):
 result=deepcopy(view);moment=as_of or now();rows=ledger_rows(store,moment) if store else []
 state=state_from_rows(rows);membership={ref:e['event_id'] for e in result.get('events',[]) for ref in e.get('article_references',[])}
 for a in result.get('items',[]):
  try:ref=normalized_url(a.get('news_source',{}).get('url'));row=state['articles'].get(ref)
  except StoreError:ref=None;row=None
  proof=deepcopy(row['payload'].get('detection_evidence')) if row else None
  if proof:
   seen=state['seen'].get(ref,{}).get('payload',{})
   proof.update(last_seen_at=seen.get('last_seen_at',proof['last_seen_at']),last_provider_check_at=seen.get('provider_checked_at',proof['provider_checked_at']),
    latest_retrieved_at=seen.get('retrieved_at',proof['retrieved_at']),knowledge_recorded_at=row['observed_at'])
   versions=store.capture_news_versions(ref,moment) if hasattr(store,'capture_news_versions') else [r for r in rows if r['observation_kind']=='NEWS_ARTICLE' and r['entity_id']==ref]
   proof['versions']=[dict(recorded_at=r['observed_at'],content_version_identity=r['payload']['content_version_identity'],title=r['payload']['title']) for r in versions]
   same=title_key(a.get('title'))==title_key(row['payload']['title']) and a.get('reported_at')==row['payload'].get('reported_at')
   proof['status']=('NEWLY_OBSERVED' if seen.get('actual_observation_identity')==proof['actual_observation_identity'] and len(versions)==1 else 'PREVIOUSLY_OBSERVED') if same else 'CAPTURED_EARLIER_VERSION'
   firstrow=versions[0];proof['first_recorded_at']=firstrow['observed_at']
   pub=timestamp(firstrow['payload'].get('reported_at'));first=timestamp(proof['first_observed_at'])
   delay=(first-pub).total_seconds() if pub and first and first>=pub and firstrow['payload']['source_timestamp_precision']=='SECOND' else None
   proof['source_to_observation_delay_seconds']=delay;proof['latency_status']='MEASURED_SOURCE_CLAIM_TO_OBSERVATION' if delay is not None else 'UNKNOWN'
   proof['processing_delay_seconds']=(timestamp(row['observed_at'])-timestamp(proof['retrieved_at'])).total_seconds()
   a['publication_precision']=row['payload']['source_timestamp_precision']
   # Only this ledger join establishes first observation, never the legacy CSV clock.
   a['observation_time_basis']='FIRST_RECORDED_SOURCE_OBSERVATION';a['observed_at']=proof['first_observed_at']
   a['prospective_evidence']=dict(status='RECORDED_DURABLE_CAPTURE' if proof.get('scope')=='PRODUCTION_DURABLE_CAPTURE' else 'RECORDED_LOCAL_PILOT',recorded_at=row['observed_at'],retrieval_time=proof['retrieved_at'],receipt_id=proof['source_receipt_identity'],
    content_hash=row['payload']['content_version_identity'].removeprefix('news-content-v47-'),evidence_version=row['payload']['content_version_identity'],scope=proof.get('scope',SCOPE),replay_available=True)
  else:
   provider=next((name for name in PROVIDERS if (a.get('news_source') or {}).get('name','').startswith(name)),None)
   source=(result.get('discovery_sources') or {}).get(provider,{})
   proof=dict(contract=CONTRACT,status='FIRST_SEEN_NOT_PROVEN',first_observed_at=None,first_observed_proven=False,
    source_published_at=a.get('reported_at'),source_timestamp_precision=a.get('publication_precision') or 'UNKNOWN',
    provider_checked_at=source.get('last_attempt_at'),retrieved_at=None,recorded_at=None,last_seen_at=None,versions=[],latency_status='UNKNOWN',source_to_observation_delay_seconds=None,scope='NOT_CONFIGURED')
  proof['research_priority']=triage(a,membership.get(a.get('article_reference')),moment,proof)
  a['detection_evidence']=proof
 result['prospective_detection']=dict(contract=CONTRACT,scope=rows[0]['provenance'].get('scope',SCOPE) if rows else 'NOT_CONFIGURED',
  source_health=[r['payload'] for r in state['providers'].values()],as_of=moment,
  collection_mode='EXPLICIT_BOUNDED_PILOT;NO_AUTOMATIC_PRODUCTION_RECORDING')
 return result

def research_as_of(store,event_id,as_of):
 from .radar_reality_replay import replay_event_as_of
 from .radar_macroview_freeze import preview_macroview
 replay=replay_event_as_of(store,event_id,as_of,internal=True)
 projection=replay.pop('_projection',None)
 knowledge=attach_detection(projection,store,as_of=as_of) if projection else None
 return dict(contract=CONTRACT,scope=getattr(getattr(store,'capture_config',None),'scope',SCOPE),canonical_event_id=event_id,as_of=replay['as_of'],
  status=replay['replay_status'],news=knowledge.get('items',[]) if knowledge else [],official_propositions=[r['payload'] for r in replay['official_evidence_observations'] if r.get('active_at_as_of')],
  evidence_versions=[dict(recorded_at=r['observed_at'],title=r['payload'].get('title'),active_at_as_of=r['active_at_as_of']) for r in replay['news_observations']],
  macroview_preview=preview_macroview(projection,event_id) if projection else None,macroview_authority='NON_AUTHORITATIVE_CURRENT_RULES_ON_ASOF_EVIDENCE;NOT_RECORDED_FORECAST',
  historical_analogue_status='EX_POST_LIBRARY_EXCLUDED_FROM_ASOF_EVIDENCE',market_observation='MARKET_OBSERVATION_NOT_AVAILABLE',
  polymarket_match='NO_VERIFIED_POLYMARKET_MATCH',unknowns=replay['unknowns'])

def main(argv=None):
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--fetch-worker',choices=tuple(PROVIDERS))
 parser.add_argument('--pilot-root',type=Path)
 parser.add_argument('--opt-in-isolated-public-capture',action='store_true')
 parser.add_argument('--initialize',action='store_true')
 parser.add_argument('--provider',action='append',choices=tuple(PROVIDERS))
 parser.add_argument('--interval',type=int,default=1800)
 parser.add_argument('--max-requests',type=int,default=56)
 parser.add_argument('--cycles',type=int,default=1)
 parser.add_argument('--only-provider',action='append',choices=tuple(PROVIDERS))
 args=parser.parse_args(argv)
 if args.fetch_worker:
  from .eia_live_ingestion import failure_reason
  sys.stderr.write('FETCH_STARTED\n');sys.stderr.flush()
  try:sys.stdout.buffer.write(fetch_worker(args.fetch_worker));return 0
  except Exception as error:sys.stderr.write(failure_reason(error));return 1
 if not args.opt_in_isolated_public_capture or not args.pilot_root:parser.error('explicit isolated capture opt-in and new durable pilot root required')
 try:
  runner=ProspectiveRunner(args.pilot_root,providers=args.provider or ('ECB Press','Global Voices'),interval=args.interval,max_requests=args.max_requests,initialize=args.initialize)
  for sig in (signal.SIGINT,signal.SIGTERM):signal.signal(sig,lambda signum,frame:runner.stop.set())
  print(json.dumps(dict(contract=CONTRACT,scope=SCOPE,results=runner.run(args.cycles,only=args.only_provider)),ensure_ascii=True))
  return 0
 except (StoreError,OSError,ValueError):sys.stderr.write('PILOT_STORAGE_OR_CAPTURE_UNAVAILABLE;NO_PRODUCTION_ACTIVATION\n');return 1

if __name__=='__main__':raise SystemExit(main())
