"""Opt-in SQLite evidence ledger. Imports and read APIs never create a database.

Ledger observation time is the time this store records knowledge, NOT the time
embedded in imported snapshots. Importing an old CSV cannot fabricate history.
"""
from __future__ import annotations
from copy import deepcopy
from contextlib import contextmanager, closing
from datetime import datetime,timezone
import hashlib,json,os,sqlite3,threading
from pathlib import Path
SCHEMA='RADAR_INTELLIGENCE_DB_V1'
OBSERVATION='INTELLIGENCE_OBSERVATION_V1'
ROOT=Path(__file__).resolve().parents[2]
KINDS={'NEWS_ARTICLE','CANONICAL_EVENT_STATE','OFFICIAL_EVIDENCE','MARKET_EXPECTATION','SOURCE_STATE','CONTEXT_GEOGRAPHY','MARKET_REALITY','MARKET_OBSERVATION','MARKET_OBSERVATION_RECEIPT'}
MAX_PAYLOAD=2*1024*1024
class StoreError(ValueError):pass

def canonical(value):
 try:return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)
 except (ValueError,TypeError) as e:raise StoreError('INVALID_JSON_VALUE') from e

def sha(text):return hashlib.sha256(text.encode('utf-8')).hexdigest()

def time_value(value):
 if not isinstance(value,str):raise StoreError('INVALID_SYSTEM_TIME')
 try:
  dt=datetime.fromisoformat(value.replace('Z','+00:00'))
  if dt.tzinfo is None:raise ValueError('timezone required')
  dt=dt.astimezone(timezone.utc)
  delta=dt-datetime(1970,1,1,tzinfo=timezone.utc)
  return dt.isoformat(timespec='microseconds').replace('+00:00','Z'),(delta.days*86400+delta.seconds)*1000000+delta.microseconds
 except (ValueError,OverflowError) as e:raise StoreError('INVALID_SYSTEM_TIME') from e

def now():return datetime.now(timezone.utc).isoformat().replace('+00:00','Z')

def optional_time(value):
 try:return time_value(value)[0]
 except StoreError:return None

def configured_db():
 value=os.environ.get('RADAR_INTELLIGENCE_DB','').strip()
 if value:return Path(value).expanduser().resolve()
 runtime=os.environ.get('RADAR_RUNTIME_ROOT','').strip()
 if runtime:return Path(runtime).expanduser().resolve()/'intelligence/radar_intelligence.sqlite3'
 if os.environ.get('RADAR_PERSIST_INTELLIGENCE','').strip()=='1':
  try:return Path.home()/'.global-event-radar/intelligence/radar_intelligence.sqlite3'
  except RuntimeError as e:raise StoreError('LOCAL_DATA_ROOT_UNAVAILABLE') from e
 return None

def validate_payload_time(kind,payload,recorded_us):
 if not isinstance(payload,dict):raise StoreError('INVALID_OBSERVATION_PAYLOAD')
 if kind=='MARKET_REALITY':
  from .radar_market_reality import normalize_record,MarketRealityError
  try:
   if normalize_record(payload)!=payload:raise MarketRealityError('NONCANONICAL_MARKET_RECORD')
  except (MarketRealityError,TypeError):raise StoreError('INVALID_MARKET_REALITY_RECORD')
 if kind=='MARKET_OBSERVATION':
  from .radar_market_reality import normalize_observation,MarketRealityError
  try:
   if normalize_observation(payload)!=payload:raise MarketRealityError('NONCANONICAL_MARKET_OBSERVATION')
  except (MarketRealityError,TypeError):raise StoreError('INVALID_MARKET_OBSERVATION')
 if kind=='MARKET_OBSERVATION_RECEIPT':
  if (payload.get('contract_version')!='MARKET_OBSERVATION_RECEIPT_V0' or
      not isinstance(payload.get('observation_id'),str) or not payload['observation_id'].startswith('market-observation-v0-') or
      payload.get('data_usage_scope')!='PRIVATE_RESEARCH_ONLY'):
   raise StoreError('INVALID_MARKET_RECEIPT')
 if kind=='CONTEXT_GEOGRAPHY':
  refs=payload.get('derived_from');fingerprint=payload.get('registry_fingerprint');context=payload.get('context_geography')
  if (payload.get('contract_version')!='EVENT_CONTEXT_V1' or not payload.get('canonical_event_id')
      or not isinstance(refs,list) or not refs or len(refs)>512 or not all(isinstance(r,str) and r for r in refs)
      or not isinstance(fingerprint,str) or len(fingerprint)!=64 or any(c not in '0123456789abcdef' for c in fingerprint)
      or not isinstance(context,dict) or context.get('method') not in ('UNKNOWN','MULTI_REGION','EXPLICIT_CONTEXT_MENTION','MENTION_DERIVED','INSTITUTION_JURISDICTION')
      or context.get('confidence') not in (None,'LOW','MEDIUM','HIGH')
      or not isinstance(payload.get('institution_context'),list) or not isinstance(payload.get('headline_explanation'),dict)):
   raise StoreError('INVALID_CONTEXT_PROVENANCE')
 keys={'NEWS_ARTICLE':('observed_at','discovered_at'),'CANONICAL_EVENT_STATE':('first_detected_at',),'OFFICIAL_EVIDENCE':('first_seen_at','retrieved_at'),'MARKET_EXPECTATION':('observed_at',),'MARKET_REALITY':('observed_at','event_observed_at'),'MARKET_OBSERVATION':('observed_at',)}.get(kind,())
 for key in keys:
  value=payload.get(key)
  if value is not None and time_value(value)[1]>recorded_us:raise StoreError('FUTURE_INPUT_KNOWLEDGE_REJECTED')

_SQL="""
CREATE TABLE schema_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
INSERT INTO schema_metadata VALUES ('contract_version','RADAR_INTELLIGENCE_DB_V1');
CREATE TABLE observations (
 observation_id TEXT PRIMARY KEY, observation_kind TEXT NOT NULL,
 entity_id TEXT NOT NULL, canonical_event_id TEXT,
 observed_at TEXT NOT NULL, observed_us INTEGER NOT NULL,
 source_timestamp TEXT, payload TEXT NOT NULL, payload_sha256 TEXT NOT NULL,
 provenance TEXT NOT NULL, contract_version TEXT NOT NULL);
CREATE INDEX observation_entity_time ON observations(observation_kind,entity_id,observed_us,observation_id);
CREATE INDEX observation_event_time ON observations(canonical_event_id,observed_us,observation_id);
CREATE TABLE macroview_freezes (
 macroview_id TEXT PRIMARY KEY, canonical_event_id TEXT NOT NULL,
 freeze_key TEXT NOT NULL, frozen_at TEXT, contract_version TEXT NOT NULL,
 payload TEXT NOT NULL,payload_sha256 TEXT NOT NULL,created_at TEXT NOT NULL,
 created_us INTEGER NOT NULL,provenance TEXT NOT NULL,snapshot_sha256 TEXT NOT NULL,
 UNIQUE(canonical_event_id,freeze_key,snapshot_sha256));
CREATE TRIGGER observations_no_update BEFORE UPDATE ON observations BEGIN SELECT RAISE(ABORT,'APPEND_ONLY'); END;
CREATE TRIGGER observations_no_delete BEFORE DELETE ON observations BEGIN SELECT RAISE(ABORT,'APPEND_ONLY'); END;
CREATE TRIGGER freezes_no_update BEFORE UPDATE ON macroview_freezes BEGIN SELECT RAISE(ABORT,'APPEND_ONLY'); END;
CREATE TRIGGER freezes_no_delete BEFORE DELETE ON macroview_freezes BEGIN SELECT RAISE(ABORT,'APPEND_ONLY'); END;
PRAGMA user_version=1;
"""

class IntelligenceStore:
 def __init__(self,path,*,create=False):
  self.path=Path(path).expanduser().resolve()
  if self.path.is_relative_to(ROOT):raise StoreError('STORE_INSIDE_SOURCE_TREE')
  if create:
   self.path.parent.mkdir(parents=True,exist_ok=True)
   try:
    with closing(sqlite3.connect(self.path,timeout=3)) as db, db:
     db.execute('PRAGMA busy_timeout=3000')
     db.execute('BEGIN IMMEDIATE')
     exists=db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
     if not exists:
      # executescript commits its prior transaction; exclusive creation happens
      # under its own transaction, so a second initializer cannot overwrite it.
      db.executescript('BEGIN IMMEDIATE;'+_SQL+'COMMIT;')
     else:self._schema(db)
     db.commit();db.execute('PRAGMA journal_mode=WAL')
   except sqlite3.Error as e:raise StoreError('STORE_UNAVAILABLE') from e
  with self.connection() as db:self._schema(db)

 @staticmethod
 def _schema(db):
  version=db.execute("SELECT value FROM schema_metadata WHERE key='contract_version'").fetchone()
  if version is None or version[0]!=SCHEMA or db.execute('PRAGMA user_version').fetchone()[0]!=1:raise StoreError('UNSUPPORTED_STORE_SCHEMA')
  tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
  if tables!={'observations','macroview_freezes','schema_metadata'}:raise StoreError('INVALID_STORE_SCHEMA')
  if 'snapshot_sha256' not in {r[1] for r in db.execute('PRAGMA table_info(macroview_freezes)')}:raise StoreError('INVALID_STORE_SCHEMA')
  triggers={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='trigger'")}
  if triggers!={'observations_no_update','observations_no_delete','freezes_no_update','freezes_no_delete'}:raise StoreError('INVALID_STORE_SCHEMA')

 @contextmanager
 def connection(self,*,write=False):
  if not self.path.is_file():raise StoreError('STORE_UNAVAILABLE')
  try:
   db=sqlite3.connect(self.path.as_uri()+('?mode=rw' if write else '?mode=ro'),uri=True,timeout=3)
   db.row_factory=sqlite3.Row;db.execute('PRAGMA busy_timeout=3000');db.execute('PRAGMA foreign_keys=ON');db.execute('PRAGMA recursive_triggers=ON')
   if not write:db.execute('PRAGMA query_only=ON')
   try:
    yield db
    if write:db.commit()
   except BaseException:
    if write:db.rollback()
    raise
   finally:db.close()
  except sqlite3.Error as e:raise StoreError('STORE_UNAVAILABLE') from e

 def append(self,records,*,observed_at):
  timestamp,micros=time_value(observed_at);prepared=[]
  for record in records:
   kind,entity=record['observation_kind'],record['entity_id'];event=record.get('canonical_event_id')
   if kind not in KINDS or not isinstance(entity,str) or not entity or len(entity)>2048:raise StoreError('INVALID_OBSERVATION_IDENTITY')
   if event is not None and (not isinstance(event,str) or not event):raise StoreError('INVALID_EVENT_IDENTITY')
   validate_payload_time(kind,record['payload'],micros)
   if kind=='CONTEXT_GEOGRAPHY' and record['payload']['canonical_event_id']!=event:raise StoreError('CONTEXT_EVENT_BINDING_MISMATCH')
   if kind=='MARKET_REALITY' and record['payload']['event_id']!=event:raise StoreError('MARKET_EVENT_BINDING_MISMATCH')
   if kind=='MARKET_OBSERVATION' and (entity!=record['payload']['observation_id'] or event is not None):raise StoreError('GLOBAL_MARKET_IDENTITY_MISMATCH')
   payload=canonical(record['payload'])
   if len(payload.encode('utf-8'))>MAX_PAYLOAD:raise StoreError('PAYLOAD_TOO_LARGE')
   provenance=canonical(record.get('provenance') or {})
   source=optional_time(record.get('source_timestamp'))
   if kind=='MARKET_OBSERVATION' and source!=time_value(record['payload']['market_timestamp'])[0]:raise StoreError('MARKET_SOURCE_TIME_MISMATCH')
   payload_hash=sha(payload)
   identity=sha(canonical([OBSERVATION,kind,entity,event,timestamp,source,payload_hash,provenance]))
   prepared.append(('observation-v1-'+identity,kind,entity,event,timestamp,micros,source,payload,payload_hash,provenance,OBSERVATION))
   if kind=='MARKET_OBSERVATION' and record['payload']['data_usage_scope']=='PRIVATE_RESEARCH_ONLY':
    # Content remains unique. A separate append-only, deduplicated receipt
    # tracks A -> B -> A revisions without duplicating unchanged polling.
    p=record['payload'];receipt=canonical(dict(contract_version='MARKET_OBSERVATION_RECEIPT_V0',observation_id=entity,data_usage_scope='PRIVATE_RESEARCH_ONLY'))
    receipt_entity=canonical([p['provider'],p['provider_dataset'],p['symbol'],p['market_timestamp'],p['interval']])
    rh=sha(receipt);rp=canonical({'time_basis':'SYSTEM_RECORDED_TIME'})
    rid='observation-v1-'+sha(canonical([OBSERVATION,'MARKET_OBSERVATION_RECEIPT',receipt_entity,None,timestamp,source,rh,rp]))
    prepared.append((rid,'MARKET_OBSERVATION_RECEIPT',receipt_entity,None,timestamp,micros,source,receipt,rh,rp,OBSERVATION))
  inserted=[]
  try:
   with self.connection(write=True) as db:
    self._schema(db);db.execute('BEGIN IMMEDIATE')
    for row in prepared:
     if row[1]=='MARKET_OBSERVATION':
      # Atomic content identity dedup across poll times, including restarts.
      prior=db.execute('SELECT * FROM observations WHERE observation_kind=? AND entity_id=?',(row[1],row[2])).fetchall()
      if len(prior)>1:raise StoreError('AMBIGUOUS_MARKET_OBSERVATION')
      if prior:
       self.decode(prior[0])
       if row[5]<prior[0]['observed_us']:raise StoreError('BACKDATED_OBSERVATION_REJECTED')
       continue
     existing=db.execute('SELECT * FROM observations WHERE observation_id=?',(row[0],)).fetchone()
     if existing:
      if tuple(existing)!=row:raise StoreError('OBSERVATION_IDENTITY_COLLISION')
      continue
     latest=db.execute('SELECT * FROM observations WHERE observation_kind=? AND entity_id=? ORDER BY observed_us DESC,observation_id DESC LIMIT 1',(row[1],row[2])).fetchone()
     if latest:
      if row[5]<latest['observed_us']:raise StoreError('BACKDATED_OBSERVATION_REJECTED')
      if row[3]==latest['canonical_event_id'] and row[8]==latest['payload_sha256'] and row[6]==latest['source_timestamp'] and row[9]==latest['provenance']:continue
      if row[5]==latest['observed_us']:raise StoreError('CONFLICTING_SAME_TIME_OBSERVATION')
     result=db.execute('INSERT OR IGNORE INTO observations VALUES (?,?,?,?,?,?,?,?,?,?,?)',row)
     if result.rowcount and row[1]!='MARKET_OBSERVATION_RECEIPT':inserted.append(row[0])
   return inserted
  except sqlite3.Error as e:raise StoreError('STORE_WRITE_UNAVAILABLE') from e

 def ingest_projection(self,view,*,observed_at):
  if view.get('status') not in {'AVAILABLE','EMPTY'}:raise StoreError('PROJECTION_UNAVAILABLE')
  event_by_article={}
  for event in view.get('events',[]):
   for ref in event['article_references']:
    if ref in event_by_article and event_by_article[ref]!=event['event_id']:raise StoreError('AMBIGUOUS_ARTICLE_MEMBERSHIP')
    event_by_article[ref]=event['event_id']
  records=[]
  def add(kind,entity,payload,event=None,source=None):
   records.append(dict(observation_kind=kind,entity_id=entity,canonical_event_id=event,payload=deepcopy(payload),source_timestamp=source,provenance={'input_contract':view.get('contract_version'),'time_basis':'SYSTEM_RECORDED_TIME','imported_observation_time_not_backdated':True}))
  for item in view.get('items',[]):add('NEWS_ARTICLE',item['article_reference'],item,event_by_article.get(item['article_reference']),item.get('reported_at'))
  for event in view.get('events',[]):
   add('CANONICAL_EVENT_STATE',event['event_id'],event,event['event_id'])
   if event.get('context_contract')=='EVENT_CONTEXT_V1':
    add('CONTEXT_GEOGRAPHY',event['event_id'],dict(contract_version='EVENT_CONTEXT_V1',canonical_event_id=event['event_id'],derived_from=list(event['article_references']),context_geography=event['context_geography'],institution_context=event['institution_context'],headline_explanation=event['headline_explanation'],registry_fingerprint=event['context_registry_fingerprint']),event['event_id'])
  for fact in view.get('official_evidence',[]):add('OFFICIAL_EVIDENCE',fact['official_evidence_id'],fact,fact.get('canonical_event_id'),fact.get('published_at'))
  for market in view.get('market_expectations',[]):
   # One stable entity per provider market, with changing snapshot IDs in payload.
   add('MARKET_EXPECTATION',market['provider']+':'+market['market_id'],market,market.get('canonical_event_id'),None)
  for record in view.get('market_reality_observations',[]):
   add('MARKET_REALITY',record['observation_id'],record,record['event_id'],record['market_timestamp'])
  for group in ('sources','discovery_sources'):
   for name,state in sorted(view.get(group,{}).items()):add('SOURCE_STATE',group+':'+name,state)
  if view.get('expectation_provider') is not None:add('SOURCE_STATE','expectation_provider',view['expectation_provider'])
  return self.append(records,observed_at=observed_at)

 def read_as_of(self,event_id,as_of):
  _,micros=time_value(as_of)
  try:
   with self.connection() as db:
    self._schema(db)
    rows=db.execute("""WITH related AS (SELECT DISTINCT observation_kind,entity_id FROM observations WHERE canonical_event_id=? AND observed_us<=?)
    SELECT o.* FROM observations o WHERE o.observed_us<=? AND
    (o.observation_kind='SOURCE_STATE' OR EXISTS(SELECT 1 FROM related r WHERE r.observation_kind=o.observation_kind AND r.entity_id=o.entity_id))
    ORDER BY o.observed_us,o.observation_id""",(event_id,micros,micros)).fetchall()
   return [self.decode(row) for row in rows]
  except sqlite3.Error as e:raise StoreError('STORE_READ_UNAVAILABLE') from e

 def read_market_as_of(self,as_of,*,market_start=None,market_end=None):
  """Private callers only; the public API never serializes this global kind."""
  _,micros=time_value(as_of)
  bounds='';parameters=[micros]
  if market_start is not None:bounds+=' AND source_timestamp>=?';parameters.append(time_value(market_start)[0])
  if market_end is not None:bounds+=' AND source_timestamp<=?';parameters.append(time_value(market_end)[0])
  try:
   with self.connection() as db:
    self._schema(db)
    rows=db.execute("SELECT * FROM observations WHERE observation_kind='MARKET_OBSERVATION' AND observed_us<=?"+bounds+" ORDER BY observed_us,observation_id LIMIT 10001",parameters).fetchall()
    receipts=db.execute("SELECT * FROM observations WHERE observation_kind='MARKET_OBSERVATION_RECEIPT' AND observed_us<=?"+bounds+" ORDER BY observed_us,observation_id LIMIT 10001",parameters).fetchall()
   if len(rows)>10000 or len(receipts)>10000:raise StoreError('MARKET_READ_BOUND_EXCEEDED')
   decoded=[self.decode(row) for row in rows];by_content={r['entity_id']:r for r in decoded};latest={}
   for raw in receipts:
    receipt=self.decode(raw);original=by_content.get(receipt['payload']['observation_id'])
    if original is None:raise StoreError('MARKET_RECEIPT_CONTENT_MISSING')
    p=original['payload'];expected_entity=canonical([p['provider'],p['provider_dataset'],p['symbol'],p['market_timestamp'],p['interval']])
    if receipt['entity_id']!=expected_entity or receipt['observed_us']<original['observed_us']:raise StoreError('INVALID_MARKET_RECEIPT_BINDING')
    latest[receipt['entity_id']]={**original,'receipt_observed_at':receipt['observed_at']}
   # Public/unknown lower records and pre-receipt stores retain their original
   # registration. Private recorded revisions use latest as-of receipt time.
   return [r for r in decoded if r['payload']['data_usage_scope']!='PRIVATE_RESEARCH_ONLY' or
       canonical([r['payload']['provider'],r['payload']['provider_dataset'],r['payload']['symbol'],r['payload']['market_timestamp'],r['payload']['interval']]) not in latest]+list(latest.values())
  except sqlite3.Error as e:raise StoreError('STORE_READ_UNAVAILABLE') from e

 @staticmethod
 def decode(row):
  if row['contract_version']!=OBSERVATION or sha(row['payload'])!=row['payload_sha256']:raise StoreError('OBSERVATION_INTEGRITY_FAILED')
  payload=json.loads(row['payload']);provenance=json.loads(row['provenance'])
  validate_payload_time(row['observation_kind'],payload,row['observed_us'])
  if row['observation_kind']=='CONTEXT_GEOGRAPHY' and payload.get('canonical_event_id')!=row['canonical_event_id']:raise StoreError('CONTEXT_EVENT_BINDING_MISMATCH')
  if row['observation_kind']=='MARKET_REALITY' and payload.get('event_id')!=row['canonical_event_id']:raise StoreError('MARKET_EVENT_BINDING_MISMATCH')
  if row['observation_kind']=='MARKET_OBSERVATION' and (payload['observation_id']!=row['entity_id'] or row['canonical_event_id'] is not None):raise StoreError('GLOBAL_MARKET_IDENTITY_MISMATCH')
  if row['observation_kind']=='MARKET_OBSERVATION' and row['source_timestamp']!=time_value(payload['market_timestamp'])[0]:raise StoreError('MARKET_SOURCE_TIME_MISMATCH')
  identity='observation-v1-'+sha(canonical([OBSERVATION,row['observation_kind'],row['entity_id'],row['canonical_event_id'],row['observed_at'],row['source_timestamp'],row['payload_sha256'],row['provenance']]))
  if identity!=row['observation_id'] or time_value(row['observed_at'])[1]!=row['observed_us']:raise StoreError('OBSERVATION_INTEGRITY_FAILED')
  return {**dict(row),'payload':payload,'provenance':provenance}

 def freeze_event(self,event_id,*,freeze_key,as_of,created_at):
  from .radar_reality_replay import replay_event_as_of
  from .radar_macroview_freeze import freeze_macroview
  replay=replay_event_as_of(self,event_id,as_of,internal=True)
  if replay['replay_status']!='AVAILABLE':raise StoreError('NO_EVENT_OBSERVATIONS')
  created,created_us=time_value(created_at)
  if created_us<time_value(as_of)[1]:raise StoreError('FREEZE_CREATION_BEFORE_AS_OF')
  frozen=freeze_macroview(replay['_projection'],event_id,freeze_key=freeze_key,frozen_at=time_value(as_of)[0])
  payload=canonical(frozen);provenance=canonical({'observation_ids':replay['observation_ids'],'time_basis':'SYSTEM_RECORDED_TIME'})
  try:
   with self.connection(write=True) as db:
    self._schema(db);db.execute('BEGIN IMMEDIATE')
    snapshot_hash=frozen['provenance']['snapshot_sha256']
    prior=db.execute('SELECT payload,payload_sha256 FROM macroview_freezes WHERE canonical_event_id=? AND freeze_key=? AND snapshot_sha256=?',(event_id,freeze_key,snapshot_hash)).fetchone()
    if prior:
     if sha(prior[0])!=prior[1]:raise StoreError('FREEZE_INTEGRITY_FAILED')
     return json.loads(prior[0])
    db.execute('INSERT INTO macroview_freezes VALUES (?,?,?,?,?,?,?,?,?,?,?)',(frozen['macroview_id'],event_id,freeze_key,frozen['frozen_at'],frozen['contract_version'],payload,sha(payload),created,created_us,provenance,snapshot_hash))
   return frozen
  except sqlite3.Error as e:raise StoreError('FREEZE_WRITE_UNAVAILABLE') from e

 def freezes(self,event_id):
  try:
   with self.connection() as db:
    self._schema(db);rows=db.execute('SELECT * FROM macroview_freezes WHERE canonical_event_id=? ORDER BY created_us,macroview_id',(event_id,)).fetchall()
   result=[]
   for row in rows:
    if row['contract_version']!='MACROVIEW_FREEZE_V0' or sha(row['payload'])!=row['payload_sha256']:raise StoreError('FREEZE_INTEGRITY_FAILED')
    frozen=json.loads(row['payload']);identity=frozen.pop('macroview_id',None)
    expected='macroview-freeze-v0-'+sha(canonical(frozen));frozen['macroview_id']=identity
    if identity!=expected or identity!=row['macroview_id'] or frozen['canonical_event_id']!=row['canonical_event_id'] or frozen['provenance']['snapshot_sha256']!=row['snapshot_sha256']:raise StoreError('FREEZE_INTEGRITY_FAILED')
    result.append(frozen)
   return result
  except sqlite3.Error as e:raise StoreError('STORE_READ_UNAVAILABLE') from e

class IntelligenceRecorder:
 """One opt-in owned thread. Reads an in-memory projection; never fetches News."""
 def __init__(self,path,projection,*,interval=60,clock=now):
  if type(interval) is not int or not 5<=interval<=86400:raise StoreError('INVALID_RECORD_INTERVAL')
  self.store=IntelligenceStore(path,create=True);self.projection=projection;self.interval=interval;self.clock=clock
  self.stop_event=threading.Event();self.thread=None;self.lock=threading.RLock();self.status='STARTING'
 def record_once(self):
  try:
   view=self.projection();recorded=self.clock();inserted=self.store.ingest_projection(view,observed_at=recorded)
   if inserted:
    for event in view.get('events',[])[:100]:self.store.freeze_event(event['event_id'],freeze_key='RECORDED/'+recorded,as_of=recorded,created_at=recorded)
   with self.lock:self.status='AVAILABLE'
   return True
  except (StoreError,ValueError,sqlite3.Error,OSError):
   with self.lock:self.status='UNAVAILABLE'
   return False
 def start(self):
  with self.lock:
   if self.thread is None:self.thread=threading.Thread(target=self._loop,name='radar-intelligence-recorder',daemon=True);self.thread.start()
 def _loop(self):
  while not self.stop_event.is_set():
   if not self.record_once():break
   if self.stop_event.wait(self.interval):break
 def close(self):
  self.stop_event.set()
  if self.thread:self.thread.join(timeout=8)
