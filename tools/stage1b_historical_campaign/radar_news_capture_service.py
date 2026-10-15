"""Explicit single-writer lifecycle over the existing prospective runner/store.

Import and read APIs do not start workers. No protected Owner/Supervisor access.
Local fixtures keep ISOLATED_LOCAL_PILOT provenance and cannot be promoted.
"""
from __future__ import annotations
from contextlib import closing
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
import argparse, hashlib, json, os, re, shutil, signal, sqlite3, subprocess, sys, tempfile, time, uuid
from dataclasses import replace
from . import radar_news_prospective as p
from .radar_intelligence_store import IntelligenceStore, StoreError, canonical, now, time_value

CONTRACT='NEWS_CAPTURE_SERVICE_V49';PRODUCTION='PRODUCTION_DURABLE_CAPTURE';LOCAL=p.SCOPE
MODULE='tools.stage1b_historical_campaign.radar_news_capture_service'
PAGE=2000;WORKING_ROWS=12000;VERSION_ROWS=2000

def safe_path(path):
 path=Path(path)
 if not path.is_absolute():raise StoreError('STORE_ABSOLUTE_PATH_REQUIRED')
 for parent in [path,*path.parents]:
  if parent.is_symlink() or (hasattr(parent,'is_junction') and parent.is_junction()):raise StoreError('STORE_LINK_REJECTED')
 return path.resolve()

class Config:
 KEYS={'contract','scope','root','durable_root','volume_id','ledger_id','providers','daily_quota','per_source_quota','interval','max_backoff','max_storage_bytes','warning_bytes','min_free_bytes','initialize','activation_approved','fixture_path'}
 def __init__(self,value):
  if not isinstance(value,dict) or set(value)!=self.KEYS or value['contract']!=CONTRACT:raise StoreError('STORE_CAPTURE_CONFIG_INVALID')
  self.value=deepcopy(value);self.root=safe_path(value['root']);self.volume=safe_path(value['durable_root']);self.scope=value['scope']
  if self.scope not in {LOCAL,PRODUCTION} or not self.root.is_relative_to(self.volume) or self.root==self.volume:raise StoreError('STORE_CAPTURE_SCOPE_INVALID')
  if self.root.is_relative_to(p.SOURCE_ROOT) or self.root.is_relative_to(Path(tempfile.gettempdir()).resolve()):raise StoreError('STORE_DURABLE_VOLUME_REQUIRED')
  if not self.volume.is_dir():raise StoreError('STORE_DURABLE_VOLUME_MISSING')
  marker=self.volume/'RADAR_DURABLE_VOLUME_V1.json'
  expected=dict(contract='RADAR_DURABLE_VOLUME_V1',volume_id=value['volume_id'],role='AUTHORIZED_DURABLE_VOLUME' if self.scope==PRODUCTION else 'ISOLATED_TEST_VOLUME')
  if not marker.is_file() or json.loads(marker.read_bytes())!=expected:raise StoreError('STORE_DURABLE_VOLUME_NOT_APPROVED')
  if not re.fullmatch(r'[a-zA-Z0-9_-]{8,80}',value['volume_id']) or not re.fullmatch(r'[a-zA-Z0-9_-]{8,80}',value['ledger_id']):raise StoreError('STORE_NAMESPACE_INVALID')
  sources=value['providers']
  if not isinstance(sources,list) or not sources or len(set(sources))!=len(sources) or any(n not in p.PROVIDERS for n in sources):raise StoreError('UNAPPROVED_SOURCE')
  for key in ['daily_quota','per_source_quota','interval','max_backoff','max_storage_bytes','warning_bytes','min_free_bytes']:
   if type(value[key])!=int:raise StoreError('STORE_CAPTURE_CONFIG_INVALID')
  if not 1<=value['daily_quota']<=288 or not 1<=value['per_source_quota']<=96 or value['interval']<1800 or not value['interval']<=value['max_backoff']<=86400:raise StoreError('STORE_QUOTA_OR_CADENCE_INVALID')
  if not 4*1024*1024<=value['min_free_bytes'] or not 0<value['warning_bytes']<value['max_storage_bytes']:raise StoreError('STORE_CAPACITY_POLICY_INVALID')
  if type(value['initialize'])!=bool or type(value['activation_approved'])!=bool:raise StoreError('STORE_CAPTURE_CONFIG_INVALID')
  if self.scope==PRODUCTION and (not value['activation_approved'] or value['fixture_path'] is not None):raise StoreError('PRODUCTION_ACTIVATION_NOT_APPROVED')
  if self.scope==PRODUCTION and not os.path.ismount(self.volume):raise StoreError('STORE_DURABLE_MOUNT_NOT_VERIFIED')
  self.fixture=safe_path(value['fixture_path']) if value['fixture_path'] else None
  if self.fixture and self.scope!=LOCAL:raise StoreError('PRODUCTION_FIXTURE_REJECTED')
  # Paths/initialize are operational placement, never authority or quota resets.
  self.policy={k:v for k,v in value.items() if k not in {'root','durable_root','initialize','fixture_path'}}
  self.fingerprint=p.digest(self.policy)
 @classmethod
 def read(cls,path):
  path=safe_path(path)
  if path.stat().st_size>65536:raise StoreError('STORE_CAPTURE_CONFIG_TOO_LARGE')
  return cls(json.loads(path.read_bytes()))

class CaptureStore(IntelligenceStore):
 def __init__(self,path,config):
  self.capture_config=config
  marker=Path(path).parent/'CAPTURE_SERVICE_V49.json'
  if not marker.is_file() or json.loads(marker.read_bytes())!=dict(contract=CONTRACT,policy=config.policy,policy_sha256=config.fingerprint):raise StoreError('STORE_CAPTURE_IDENTITY_MISMATCH')
  super().__init__(path)
 def stream(self):
  cursor=None
  with self.connection() as db:
   self._schema(db)
   while True:
    args=[];where=''
    if cursor:where='WHERE (observed_us,observation_id)>(?,?)';args=list(cursor)
    rows=db.execute('SELECT * FROM observations '+where+' ORDER BY observed_us,observation_id LIMIT ?',[*args,PAGE]).fetchall()
    if not rows:break
    for raw in rows:
     row=self.decode(raw)
     if row['provenance'].get('input_contract')!=p.CONTRACT or row['provenance'].get('scope')!=self.capture_config.scope or row['provenance'].get('capture_policy')!=self.capture_config.fingerprint:raise StoreError('STORE_FOREIGN_CAPTURE_HISTORY_REJECTED')
     yield row
    cursor=(rows[-1]['observed_us'],rows[-1]['observation_id'])
 def quota(self,date):
  with self.connection() as db:
   row=db.execute("SELECT * FROM observations WHERE observation_kind='SOURCE_STATE' AND entity_id=? ORDER BY observed_us DESC,observation_id DESC LIMIT 1",('v49:quota:'+date,)).fetchone()
  return self.decode(row)['payload'] if row else dict(record_type='QUOTA',date=date,total=0,sources={},last_reservation_at=None)
 def news_capture_rows(self,as_of=None):
  _,limit=time_value(as_of or now())
  with self.connection() as db:
   # Latest working state and earliest news evidence only. Original full-history
   # pilot remains bounded20000; persistent mode uses bounded SQL/page working sets.
   query="""SELECT o.* FROM observations o JOIN (
    SELECT observation_kind,entity_id,MAX(observed_us) AS t FROM observations
    WHERE observed_us<=? AND (observation_kind!='SOURCE_STATE' OR entity_id LIKE 'v47:seen:%' OR entity_id LIKE 'v47:provider:%')
    GROUP BY observation_kind,entity_id) k ON o.observation_kind=k.observation_kind AND o.entity_id=k.entity_id AND o.observed_us=k.t
    WHERE o.observed_us<=? ORDER BY o.observed_us,o.observation_id LIMIT ?"""
   rows=db.execute(query,(limit,limit,WORKING_ROWS+1)).fetchall()
   # Latest attempt per provider preserves crash reservation and midnight cadence.
   for provider in self.capture_config.value['providers']:
    for kind in ['ATTEMPT','RECEIPT']:
     raw=db.execute("SELECT * FROM observations WHERE observation_kind='SOURCE_STATE' AND json_extract(payload,'$.record_type')=? AND json_extract(payload,'$.provider')=? AND observed_us<=? ORDER BY observed_us DESC,observation_id DESC LIMIT 1",(kind,provider,limit)).fetchone()
     if raw:rows.append(raw)
  if len(rows)>WORKING_ROWS:raise StoreError('STORE_WORKING_STATE_BOUND_EXCEEDED')
  decoded=[self.decode(row) for row in rows]
  if any(r['provenance'].get('scope')!=self.capture_config.scope or r['provenance'].get('capture_policy')!=self.capture_config.fingerprint for r in decoded):raise StoreError('STORE_FOREIGN_CAPTURE_HISTORY_REJECTED')
  return sorted(decoded,key=lambda r:(r['observed_us'],r['observation_id']))
 def capture_news_versions(self,ref,as_of):
  with self.connection() as db:
   rows=db.execute("SELECT * FROM observations WHERE observation_kind='NEWS_ARTICLE' AND entity_id=? AND observed_us<=? ORDER BY observed_us,observation_id LIMIT ?",(ref,time_value(as_of)[1],VERSION_ROWS+1)).fetchall()
  if len(rows)>VERSION_ROWS:raise StoreError('STORE_EVENT_VERSION_BOUND_EXCEEDED')
  return [self.decode(r) for r in rows]
 def read_as_of(self,event_id,as_of):
  limit=time_value(as_of)[1]
  with self.connection() as db:
   # No raw global quotas/receipts/checkpoints in public event replay.
   rows=db.execute("""WITH related AS (SELECT DISTINCT observation_kind,entity_id FROM observations WHERE canonical_event_id=? AND observed_us<=?)
    SELECT o.* FROM observations o WHERE o.observed_us<=? AND o.observation_kind!='SOURCE_STATE'
    AND EXISTS(SELECT 1 FROM related r WHERE r.observation_kind=o.observation_kind AND r.entity_id=o.entity_id)
    ORDER BY o.observed_us,o.observation_id LIMIT 20001""",(event_id,limit,limit)).fetchall()
  if len(rows)>20000:raise StoreError('STORE_EVENT_HISTORY_BOUND_EXCEEDED')
  return [self.decode(r) for r in rows]

class ContinuousRunner(p.ProspectiveRunner):
 def __init__(self,config,*,clock=now,fetcher=p.bounded_fetch):
  self.capture_config=config;self.scope=config.scope
  marker=config.root/'CAPTURE_SERVICE_V49.json'
  if (config.root/'BACKUP_MANIFEST.json').exists():raise StoreError('STORE_BACKUP_REQUIRES_VERIFIED_RESTORE')
  if config.root.exists() and not marker.is_file():raise StoreError('STORE_LEGACY_OR_UNINITIALIZED_LEDGER_REJECTED')
  fresh=not config.root.exists()
  if fresh and not config.value['initialize']:raise StoreError('STORE_INITIALIZATION_NOT_APPROVED')
  self.probe(config.volume)
  super().__init__(config.root,providers=tuple(config.value['providers']),interval=config.value['interval'],max_requests=60,initialize=fresh,clock=clock,fetcher=fetcher)
  if fresh:p.atomic_json(marker,dict(contract=CONTRACT,policy=config.policy,policy_sha256=config.fingerprint))
  self.store=CaptureStore(self.root/'evidence.sqlite3',config)
  self.storage_warning=False
 def record(self,*args,**kwargs):
  record=super().record(*args,**kwargs);record['provenance'].update(scope=self.scope,capture_policy=self.capture_config.fingerprint)
  return record
 @staticmethod
 def probe(root):
  path=root/('.capture-write-probe-'+uuid.uuid4().hex);data=os.urandom(64)
  try:
   with path.open('xb') as f:f.write(data);f.flush();os.fsync(f.fileno())
   if path.read_bytes()!=data:raise StoreError('STORE_WRITE_PROBE_FAILED')
  finally:path.unlink(missing_ok=True)
 def state_rows(self):return self.store.news_capture_rows(self.clock())
 def stop_requested(self):
  path=self.root/'capture-stop.json'
  if path.exists() and json.loads(path.read_bytes()).get('target_pid')==os.getpid():
   self.stop.set();path.unlink()
  return self.stop.is_set()
 def capacity(self):
  self.probe(self.root);used=0
  for path in self.root.rglob('*'):
   safe_path(path)
   if path.is_file():used+=path.stat().st_size
  v=self.capture_config.value;free=shutil.disk_usage(self.root).free
  self.storage_warning=used>=v['warning_bytes']
  if used>=v['max_storage_bytes'] or free<v['min_free_bytes']:raise StoreError('STORE_CAPACITY_EXHAUSTED')
  return dict(used_bytes=used,free_bytes=free,warning=self.storage_warning)
 def reserve_attempt(self,provider,checked,state):
  self.capacity();date=checked[:10]
  with self.store.connection() as db:
   latest=db.execute("SELECT observed_at FROM observations ORDER BY observed_us DESC,observation_id DESC LIMIT 1").fetchone()
   fence=db.execute("SELECT * FROM observations WHERE observation_kind='SOURCE_STATE' AND entity_id='v49:restore_fence' ORDER BY observed_us DESC,observation_id DESC LIMIT 1").fetchone()
  if latest and p.timestamp(checked)<p.timestamp(latest[0]):raise StoreError('STORE_CLOCK_REGRESSION_REJECTED')
  if fence and p.timestamp(checked)<p.timestamp(self.store.decode(fence)['payload']['not_before_utc']):return None
  quota=self.store.quota(date);v=self.capture_config.value
  if quota['total']>=v['daily_quota'] or quota['sources'].get(provider,0)>=v['per_source_quota']:return None
  quota={**quota,'total':quota['total']+1,'sources':{**quota['sources'],provider:quota['sources'].get(provider,0)+1},'last_reservation_at':checked}
  attempt_id='attempt-v47-'+uuid.uuid4().hex
  attempt=dict(record_type='ATTEMPT',attempt_id=attempt_id,provider=provider,provider_checked_at=checked,outcome='RESERVED',scope=self.scope)
  self.store.append([self.record('SOURCE_STATE','v49:quota:'+date,quota),self.record('SOURCE_STATE','v47:attempt:'+attempt_id,attempt)],observed_at=checked)
  return attempt_id,attempt
 def provider_once(self,provider):
  prior=p.state_from_rows(self.state_rows())['providers'].get(provider,{}).get('payload',{})
  if prior.get('circuit_open'):return dict(provider=provider,status='SOURCE_PAUSED',requests=0)
  moment=self.clock();eligible=prior.get('next_eligible_check_at')
  if eligible and p.timestamp(moment)<p.timestamp(eligible):return dict(provider=provider,status='BACKOFF_OR_NOT_DUE',requests=0)
  result=super().provider_once(provider)
  if result['status'] in {'SUCCESS','FAILED'}:
   state=p.state_from_rows(self.state_rows())['providers'][provider]['payload']
   failures=0 if result['status']=='SUCCESS' else prior.get('consecutive_failures',0)+1
   seconds=self.interval if not failures else min(self.capture_config.value['max_backoff'],self.interval*2**min(failures,5))
   if state.get('reason') in {'HTTP_403','HTTP_406'}:seconds=max(seconds,86400)
   next_check=(p.timestamp(state['last_attempt_at'])+timedelta(seconds=seconds)).isoformat().replace('+00:00','Z')
   circuit=failures>=5 or state.get('reason') in {'HTTP_403','HTTP_406'}
   self.store.append([self.record('SOURCE_STATE','v47:provider:'+provider,{**state,'consecutive_failures':failures,'next_eligible_check_at':next_check,'circuit_open':circuit,'requires_operator_ack':circuit,'runner_mode':CONTRACT})],observed_at=self.clock())
   self.publish_checkpoint()
  return result
 def materialize_receipt(self,row):
  data=(canonical(row['payload'])+'\n').encode('utf8');value=deepcopy(row['payload']);identity=value.pop('receipt_id')
  if identity!='source-receipt-v47-'+p.digest(value):raise StoreError('RECEIPT_IDENTITY_FAILED')
  directory=self.root/'receipts';directory.mkdir(exist_ok=True);path=directory/(identity+'.json')
  if path.exists() and path.read_bytes()!=data:
   partial=path.read_bytes()
   if not partial or data.startswith(partial):path.rename(path.with_suffix('.partial-'+hashlib.sha256(partial).hexdigest()+'.json'))
   else:raise StoreError('RECEIPT_FILE_INTEGRITY_FAILED')
  if not path.exists():p.atomic_json(path,row['payload'])
 def recover(self):
  with self.store.connection() as db:
   latest=db.execute('SELECT observed_at FROM observations ORDER BY observed_us DESC,observation_id DESC LIMIT 1').fetchone()
  if latest and p.timestamp(self.clock())<p.timestamp(latest[0]):raise StoreError('STORE_CLOCK_REGRESSION_REJECTED')
  self.capacity()
  # Streaming integrity audit, bounded page size; never delete evidence to pass.
  for row in self.store.stream():
   if self.stop_requested():raise StoreError('STORE_SHUTDOWN_DURING_RECOVERY')
   if row['payload'].get('record_type')=='RECEIPT':self.materialize_receipt(row)
  cp=self.root/'checkpoint.json'
  if cp.exists():
   try:
    value=json.loads(cp.read_bytes());payload=value['payload']
    if value['sha256']!=p.digest(payload) or payload['policy_sha256']!=self.capture_config.fingerprint:raise ValueError()
   except (ValueError,KeyError,TypeError):cp.rename(cp.with_name('checkpoint.corrupt-'+hashlib.sha256(cp.read_bytes()).hexdigest()+'-'+uuid.uuid4().hex[:8]+'.json'))
  for row in p.state_from_rows(self.state_rows())['attempts'].values():
   if row['payload']['outcome']=='RESERVED':self.store.append([self.record('SOURCE_STATE',row['entity_id'],{**row['payload'],'outcome':'INTERRUPTED_UNKNOWN'})],observed_at=self.clock())
  self.publish_checkpoint()
 def publish_checkpoint(self):
  rows=self.state_rows();state=p.state_from_rows(rows)
  for row in state['receipts'].values():self.materialize_receipt(row)
  articles=[dict(article_reference=ref,headline_or_text=r['payload']['title'],source_name=r['payload']['news_source']['name'],source_url=r['payload']['news_source']['url'],source_published_at=r['payload']['reported_at'],event_time=r['payload']['reported_at'],observed_time=r['payload']['observed_at']) for ref,r in state['articles'].items()]
  p.atomic_json(self.root/'CURRENT_NEWS.json',articles)
  with self.store.connection() as db:
   count=db.execute('SELECT COUNT(*) FROM observations').fetchone()[0];last=db.execute('SELECT observation_id FROM observations ORDER BY observed_us DESC,observation_id DESC LIMIT 1').fetchone()
  payload=dict(contract=CONTRACT,scope=self.scope,policy_sha256=self.capture_config.fingerprint,checkpointed_at=self.clock(),ledger_observation_count=count,last_observation_id=last[0] if last else None,articles=len(articles),quota=self.store.quota(self.clock()[:10]),source_states={n:r['payload'] for n,r in state['providers'].items()},storage_warning=getattr(self,'storage_warning',False),compaction='DERIVED_CURRENT_STATE_ONLY;HISTORICAL_LEDGER_AND_RECEIPTS_RETAINED')
  p.atomic_json(self.root/'checkpoint.json',dict(payload=payload,sha256=p.digest(payload)))
 def serve(self,max_cycles=None):
  if max_cycles is not None and (type(max_cycles)!=int or not 1<=max_cycles<=4):raise StoreError('BOUNDED_CYCLES_REQUIRED')
  with p.owner_lock(self.root):
   self.recover();cycles=0
   while not self.stop_requested():
    for provider in self.providers:
     if self.stop_requested():break
     self.provider_once(provider)
    cycles+=1
    if max_cycles and cycles>=max_cycles:break
    self.stop.wait(min(self.interval,60)) # only existing scheduler, consult persisted cadence
   self.publish_checkpoint()

def fixture_fetch(config):
 def fetch(provider):
  values=json.loads(config.fixture.read_bytes());value=values[provider]
  if value=='TIMEOUT':raise TimeoutError()
  if value in {'HTTP_403','HTTP_406'}:raise p.FetchError(value,True)
  return value.encode('utf8')
 return fetch

def acknowledge_source_recovery(config,provider):
 """Offline explicit maintenance: stop capture first; preserve quota/history."""
 if provider not in config.value['providers']:raise StoreError('UNAPPROVED_SOURCE')
 runner=ContinuousRunner(config)
 with p.owner_lock(runner.root):
  runner.recover();state=p.state_from_rows(runner.state_rows())['providers'].get(provider)
  if state is None:raise StoreError('STORE_SOURCE_STATE_MISSING')
  value={**state['payload'],'consecutive_failures':0,'circuit_open':False,'requires_operator_ack':False,'recovery_acknowledged_at':now()}
  runner.store.append([runner.record('SOURCE_STATE','v47:provider:'+provider,value)],observed_at=now())
  runner.publish_checkpoint()

class Lifecycle:
 """One startup-owned child; public requests only read status and snapshots."""
 def __init__(self,enabled=False,config_path=None):self.enabled=enabled;self.config_path=config_path;self.process=None;self.config=None;self.failure=None
 def start(self):
  if not self.enabled:return
  try:
   if os.environ.get('RADAR_PERSIST_INTELLIGENCE','').strip()=='1':raise StoreError('CAPTURE_WRITER_CONFLICT')
   self.config=Config.read(self.config_path)
   self.process=subprocess.Popen([sys.executable,'-B','-m',MODULE,'--config',str(self.config_path)],cwd=p.SOURCE_ROOT,start_new_session=os.name!='nt')
  except (StoreError,OSError,ValueError,TypeError):self.failure='CAPTURE_STARTUP_FAILED'
 def status(self):
  if not self.enabled:return dict(enabled=False,status='OFF',reason=None)
  if self.failure:return dict(enabled=True,status='UNAVAILABLE',reason=self.failure)
  if self.process is None or self.process.poll() is not None:return dict(enabled=True,status='STOPPED',reason='CAPTURE_PROCESS_STOPPED')
  value=dict(enabled=True,status='RUNNING',scope=self.config.scope,reason=None)
  try:
   reader=self.reader();quota=reader.quota(now()[:10]);value.update(daily_quota_used=quota['total'],daily_quota_limit=self.config.value['daily_quota'],budget_status='EXHAUSTED' if quota['total']>=self.config.value['daily_quota'] else 'AVAILABLE')
   with reader.connection() as db:
    raw=db.execute("SELECT * FROM observations WHERE observation_kind='SOURCE_STATE' AND entity_id='v49:restore_fence' ORDER BY observed_us DESC,observation_id DESC LIMIT 1").fetchone()
   if raw:
    fence=reader.decode(raw)['payload']
    if p.timestamp(now())<p.timestamp(fence['not_before_utc']):value.update(budget_status='RESTORE_FENCED',recovery_ready_at=fence['not_before_utc'])
   checkpoint=json.loads((self.config.root/'checkpoint.json').read_bytes())
   if checkpoint['sha256']!=p.digest(checkpoint['payload']):raise StoreError('STORE_CHECKPOINT_INTEGRITY_FAILED')
   value['storage_warning']=checkpoint['payload']['storage_warning']
  except (StoreError,OSError,ValueError):value['status']='STARTING_OR_UNAVAILABLE'
  return value
 def reader(self):
  if not self.enabled or self.config is None:return None
  return CaptureStore(self.config.root/'evidence.sqlite3',self.config)
 def close(self):
  if self.process is None or self.process.poll() is not None:return
  # App signal handler owns this request; HTTP has no path to this method.
  try:
   p.atomic_json(self.config.root/'capture-stop.json',dict(contract=CONTRACT,stop=True,target_pid=self.process.pid))
  except OSError:self.process.terminate()
  try:self.process.wait(timeout=25)
  except subprocess.TimeoutExpired:
   if os.name!='nt':os.killpg(self.process.pid,signal.SIGKILL)
   else:self.process.terminate()
   self.process.wait(timeout=5)

class CaptureIngestion:
 def __init__(self,store):self.store=store
 def read_view(self,adapter,paths):
  state=p.state_from_rows(self.store.news_capture_rows())
  expected=[dict(article_reference=ref,headline_or_text=r['payload']['title'],source_name=r['payload']['news_source']['name'],source_url=r['payload']['news_source']['url'],source_published_at=r['payload']['reported_at'],event_time=r['payload']['reported_at'],observed_time=r['payload']['observed_at']) for ref,r in state['articles'].items()]
  path=self.store.path.parent/'CURRENT_NEWS.json'
  cache=json.loads(path.read_bytes())
  if sorted(cache,key=lambda a:a['article_reference'])!=sorted(expected,key=lambda a:a['article_reference']):raise StoreError('STORE_NEWS_CACHE_INTEGRITY_FAILED')
  view=adapter.build_radar_view(replace(paths,news=path))
  from .live_source_ingestion import disabled_status
  view['discovery_sources']={name:disabled_status(name) for name in ['ECB Press','Global Voices','EIA Today in Energy','UN News','Guardian World']}
  for name,row in state['providers'].items():view['discovery_sources'][name]={**row['payload'],'enabled':True,'scope':self.store.capture_config.scope}
  view['live_ingestion']=dict(enabled=False,status='DEDICATED_CAPTURE_READER;NO_VISITOR_ACQUISITION')
  return view

def backup_capture(config,destination):
 destination=safe_path(destination)
 if destination.exists():raise StoreError('STORE_BACKUP_DESTINATION_EXISTS')
 source=CaptureStore(config.root/'evidence.sqlite3',config);destination.mkdir(parents=True)
 with source.connection() as db:
  with closing(sqlite3.connect(destination/'evidence.sqlite3')) as output:db.backup(output)
 shutil.copyfile(config.root/'CAPTURE_SERVICE_V49.json',destination/'CAPTURE_SERVICE_V49.json')
 shutil.copyfile(config.root/'V47_PILOT.json',destination/'V47_PILOT.json')
 restored=CaptureStore(destination/'evidence.sqlite3',config)
 receipts={};(destination/'receipts').mkdir()
 for row in restored.stream():
  if row['payload'].get('record_type')=='RECEIPT':
   data=(canonical(row['payload'])+'\n').encode();n=row['payload']['receipt_id']+'.json';(destination/'receipts'/n).write_bytes(data);receipts[n]=hashlib.sha256(data).hexdigest()
 manifest=dict(contract=CONTRACT,db_sha256=hashlib.sha256((destination/'evidence.sqlite3').read_bytes()).hexdigest(),receipt_hashes=receipts,policy_sha256=config.fingerprint)
 p.atomic_json(destination/'BACKUP_MANIFEST.json',manifest)
 return manifest

def verify_backup(config,destination):
 destination=safe_path(destination);manifest=json.loads((destination/'BACKUP_MANIFEST.json').read_bytes())
 if manifest['contract']!=CONTRACT or manifest['policy_sha256']!=config.fingerprint:raise StoreError('STORE_BACKUP_POLICY_MISMATCH')
 if hashlib.sha256((destination/'evidence.sqlite3').read_bytes()).hexdigest()!=manifest['db_sha256']:raise StoreError('STORE_BACKUP_DB_HASH_FAILED')
 expected={'evidence.sqlite3','CAPTURE_SERVICE_V49.json','V47_PILOT.json','BACKUP_MANIFEST.json'}|{'receipts/'+name for name in manifest['receipt_hashes']}
 actual={path.relative_to(destination).as_posix() for path in destination.rglob('*') if path.is_file() and not path.name.endswith(('-wal','-shm'))}
 if actual!=expected:raise StoreError('STORE_BACKUP_INVENTORY_FAILED')
 for name,digest in manifest['receipt_hashes'].items():
  if '/' in name or '\\' in name or hashlib.sha256((destination/'receipts'/name).read_bytes()).hexdigest()!=digest:raise StoreError('STORE_BACKUP_RECEIPT_HASH_FAILED')
 reader=CaptureStore(destination/'evidence.sqlite3',config);receipt_names=set();count=0
 with reader.connection() as db:
  if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise StoreError('STORE_BACKUP_SQLITE_INTEGRITY_FAILED')
 for row in reader.stream():
  count+=1
  if row['payload'].get('record_type')=='RECEIPT':receipt_names.add(row['payload']['receipt_id']+'.json')
 if receipt_names!=set(manifest['receipt_hashes']):raise StoreError('STORE_BACKUP_RECEIPT_INVENTORY_FAILED')
 return dict(status='VERIFIED',observations=count,receipts=len(receipt_names),manifest=manifest)

def restore_capture(config,backup,destination):
 backup=safe_path(backup);destination=safe_path(destination)
 if destination.exists() or not destination.is_relative_to(config.volume):raise StoreError('STORE_RESTORE_DESTINATION_REJECTED')
 report=verify_backup(config,backup);destination.mkdir()
 names=['evidence.sqlite3','CAPTURE_SERVICE_V49.json','V47_PILOT.json']+['receipts/'+name for name in report['manifest']['receipt_hashes']]
 for name in names:
  target=destination/name;target.parent.mkdir(parents=True,exist_ok=True)
  with target.open('xb') as handle:handle.write((backup/name).read_bytes());handle.flush();os.fsync(handle.fileno())
 # A backup might predate spent requests. Conservatively fence capture until
 # the next UTC day instead of resetting today's quota after data loss.
 restored_at=now();next_day=(p.timestamp(restored_at).replace(hour=0,minute=0,second=0,microsecond=0)+timedelta(days=1)).isoformat().replace('+00:00','Z')
 row=p.record('SOURCE_STATE','v49:restore_fence',dict(record_type='RESTORE_FENCE',restored_at=restored_at,not_before_utc=next_day,reason='POST_BACKUP_REQUEST_USAGE_UNKNOWN'))
 row['provenance'].update(scope=config.scope,capture_policy=config.fingerprint)
 CaptureStore(destination/'evidence.sqlite3',config).append([row],observed_at=restored_at)
 return dict(status='RESTORED_NOT_STARTED',observations=report['observations'],receipts=report['receipts'],quota_fence_until=next_day)

def main(argv=None):
 parser=argparse.ArgumentParser();parser.add_argument('--config',required=True);parser.add_argument('--max-cycles',type=int);args=parser.parse_args(argv)
 try:
  config=Config.read(args.config);runner=ContinuousRunner(config,fetcher=fixture_fetch(config) if config.fixture else p.bounded_fetch)
  for sig in [signal.SIGINT,signal.SIGTERM]:signal.signal(sig,lambda *a:runner.stop.set())
  # One interruptible wait integrates the private file stop request without an
  # additional thread or scheduler; stale stop means safely stop until operator clears.
  original_wait=runner.stop.wait
  def wait(seconds):
   end=time.monotonic()+seconds
   while not runner.stop.is_set() and time.monotonic()<end:
    if runner.stop_requested():break
    original_wait(min(.2,max(0,end-time.monotonic())))
   return runner.stop.is_set()
  runner.stop.wait=wait
  runner.serve(args.max_cycles);return 0
 except (StoreError,OSError,ValueError,TypeError) as error:
  reason=str(error) if isinstance(error,StoreError) and re.fullmatch('[A-Z_0-9]{1,100}',str(error)) else 'CAPTURE_STORAGE_OR_CONFIG_UNAVAILABLE'
  sys.stderr.write('CAPTURE_UNAVAILABLE:'+reason+';NO_PRODUCTION_AUTHORITY\n');return 1

if __name__=='__main__':raise SystemExit(main())
