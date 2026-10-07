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
KINDS={'NEWS_ARTICLE','CANONICAL_EVENT_STATE','OFFICIAL_EVIDENCE','MARKET_EXPECTATION','SOURCE_STATE'}
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
 keys={'NEWS_ARTICLE':('observed_at','discovered_at'),'CANONICAL_EVENT_STATE':('first_detected_at',),'OFFICIAL_EVIDENCE':('first_seen_at','retrieved_at'),'MARKET_EXPECTATION':('observed_at',)}.get(kind,())
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
   db.row_factory=sqlite3.Row;db.execute('PRAGMA busy_timeout=3000');db.execute('PRAGMA foreign_keys=ON')
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
   payload=canonical(record['payload'])
   if len(payload.encode('utf-8'))>MAX_PAYLOAD:raise StoreError('PAYLOAD_TOO_LARGE')
   provenance=canonical(record.get('provenance') or {})
   source=optional_time(record.get('source_timestamp'))
   payload_hash=sha(payload)
   identity=sha(canonical([OBSERVATION,kind,entity,event,timestamp,source,payload_hash,provenance]))
   prepared.append(('observation-v1-'+identity,kind,entity,event,timestamp,micros,source,payload,payload_hash,provenance,OBSERVATION))
  inserted=[]
  try:
   with self.connection(write=True) as db:
    self._schema(db);db.execute('BEGIN IMMEDIATE')
    for row in prepared:
     existing=db.execute('SELECT * FROM observations WHERE observation_id=?',(row[0],)).fetchone()
     if existing:
      if tuple(existing)!=row:raise StoreError('OBSERVATION_IDENTITY_COLLISION')
      continue
     latest=db.execute('SELECT * FROM observations WHERE observation_kind=? AND entity_id=? ORDER BY observed_us DESC,observation_id DESC LIMIT 1',(row[1],row[2])).fetchone()
     if latest:
      if row[5]<latest['observed_us']:raise StoreError('BACKDATED_OBSERVATION_REJECTED')
      if row[8]==latest['payload_sha256'] and row[6]==latest['source_timestamp'] and row[9]==latest['provenance']:continue
      if row[5]==latest['observed_us']:raise StoreError('CONFLICTING_SAME_TIME_OBSERVATION')
     result=db.execute('INSERT OR IGNORE INTO observations VALUES (?,?,?,?,?,?,?,?,?,?,?)',row)
     if result.rowcount:inserted.append(row[0])
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
  for event in view.get('events',[]):add('CANONICAL_EVENT_STATE',event['event_id'],event,event['event_id'])
  for fact in view.get('official_evidence',[]):add('OFFICIAL_EVIDENCE',fact['official_evidence_id'],fact,fact.get('canonical_event_id'),fact.get('published_at'))
  for market in view.get('market_expectations',[]):
   # One stable entity per provider market, with changing snapshot IDs in payload.
   add('MARKET_EXPECTATION',market['provider']+':'+market['market_id'],market,market.get('canonical_event_id'),None)
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

 @staticmethod
 def decode(row):
  if row['contract_version']!=OBSERVATION or sha(row['payload'])!=row['payload_sha256']:raise StoreError('OBSERVATION_INTEGRITY_FAILED')
  payload=json.loads(row['payload']);provenance=json.loads(row['provenance'])
  validate_payload_time(row['observation_kind'],payload,row['observed_us'])
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
