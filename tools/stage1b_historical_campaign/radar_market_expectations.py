"""Bounded public Gamma snapshots. No legacy runtime, credentials or factual authority.

Existing repository Gamma sensor maps outcomePrices to observed expectation
values. V1 retains those provider values (including their original string type),
explicitly labeled PROVIDER_OUTCOME_PRICES: no calibration or normalization.
No imports/fetches/threads at import time; opt-in lifecycle is process-owned.
"""
from __future__ import annotations
from collections import Counter
from copy import deepcopy
from datetime import datetime,timezone
import hashlib,json,math,re,ssl,threading
from urllib.request import Request,build_opener,HTTPSHandler,HTTPRedirectHandler
CONTRACT='MARKET_EXPECTATION_V1'
ENDPOINT='https://gamma-api.polymarket.com/markets?active=true&closed=false&limit=20'
MAX_BYTES=2*1024*1024
TIMEOUT=10
class ExpectationError(ValueError):pass

def timestamp(value):
 if not isinstance(value,str):return None
 try:
  dt=datetime.fromisoformat(value.replace('Z','+00:00'))
  return dt.astimezone(timezone.utc).isoformat().replace('+00:00','Z') if dt.tzinfo else None
 except (ValueError,OverflowError):return None

def text(value,limit=3000):return value.strip()[:limit] if isinstance(value,str) and value.strip() else None

def array(value):
 if isinstance(value,str):
  try:value=json.loads(value)
  except (ValueError,TypeError):return None
 return value if isinstance(value,list) and len(value)<=32 else None

def price(value):
 if isinstance(value,bool) or not isinstance(value,(str,int,float)):return None
 try:valid=math.isfinite(float(value)) and 0<=float(value)<=1
 except (ValueError,OverflowError):valid=False
 return value if valid else None

def amount(value):
 if isinstance(value,bool) or not isinstance(value,(str,int,float)):return None
 try:valid=math.isfinite(float(value)) and float(value)>=0
 except (ValueError,OverflowError):valid=False
 return value if valid else None

def parse_markets(payload,observed_at):
 observed=timestamp(observed_at)
 if observed is None:raise ExpectationError('INVALID_OBSERVED_AT')
 if isinstance(payload,(bytes,str)):
  if len(payload)>MAX_BYTES:raise ExpectationError('RESPONSE_TOO_LARGE')
  try:payload=json.loads(payload)
  except (ValueError,UnicodeError) as e:raise ExpectationError('INVALID_JSON') from e
 rows=payload if isinstance(payload,list) else [payload] if isinstance(payload,dict) and 'id' in payload else None
 if rows is None or len(rows)>100:raise ExpectationError('INVALID_MARKET_LIST')
 records={};conflicts=set()
 for row in rows:
  if not isinstance(row,dict):raise ExpectationError('INVALID_MARKET_ROW')
  mid=row.get('id')
  if isinstance(mid,bool) or not isinstance(mid,(int,str)) or not str(mid).strip():continue
  mid=str(mid).strip()
  if len(mid)>200:continue
  labels=array(row.get('outcomes'));values=array(row.get('outcomePrices'))
  labels=[text(x,300) for x in labels] if labels is not None else None
  probabilities=[price(x) for x in values] if values is not None and labels is not None and len(values)==len(labels) else None
  slug=text(row.get('slug'),300)
  if slug and not re.fullmatch(r'[a-zA-Z0-9-]+',slug):slug=None
  provider_events=row.get('events')
  event_slugs={e.get('slug') for e in provider_events if isinstance(e,dict) and isinstance(e.get('slug'),str) and re.fullmatch(r'[a-zA-Z0-9-]+',e['slug'])} if isinstance(provider_events,list) and len(provider_events)<=100 else set()
  event_slug=next(iter(event_slugs)) if len(event_slugs)==1 else None
  record=dict(contract_version=CONTRACT,provider='Polymarket',authority_role='EXPECTATION_SENSOR',market_id=mid,market_slug=slug,question=text(row.get('question')),outcomes=labels,probabilities=probabilities,probability_semantics='PROVIDER_OUTCOME_PRICES',observed_at=observed,market_close_time=timestamp(row.get('endDate')),market_url='https://polymarket.com/event/'+event_slug if event_slug else None,link_status='UNLINKED',canonical_event_id=None,link_method=None)
  # Public allowlisted metadata only; resolution text is not factual authority.
  metadata=dict(description=text(row.get('description'),6000),resolution_criteria=text(row.get('resolutionCriteria'),6000),resolution_source=text(row.get('resolutionSource'),1000),group_title=text(row.get('groupItemTitle'),300),provider_created_at=timestamp(row.get('createdAt')),provider_updated_at=timestamp(row.get('updatedAt')),
   provider_events=[{k:text(e.get(k),500) for k in ('id','slug','title','category')} for e in provider_events[:20] if isinstance(e,dict)] if isinstance(provider_events,list) else [])
  # Public outcome identifiers are optional provenance. They must align with
  # labels before being attached; a token ID never supplies a missing price.
  for source,kind in (('clobTokenIds','CLOB_TOKEN_ID'),('positionIds','POSITION_ID')):
   ids=array(row.get(source))
   if labels and ids is not None and len(ids)==len(labels) and all(isinstance(x,str) and re.fullmatch(r'(?:[0-9]{1,128}|0x[0-9a-fA-F]{64})',x) for x in ids):
    metadata['outcome_identifiers']=ids
    metadata['outcome_identifier_kind']=kind
    break
  for flag in ('closed','active'):
   if type(row.get(flag)) is bool:metadata[flag]=row[flag]
  for field in ('liquidity','volume'):
   if field in row:metadata[field]=amount(row[field])
  if type(row.get('archived')) is bool:metadata['archived']=row['archived']
  if (any(isinstance(row.get(key),str) and len(row[key].strip())>limit for key,limit in [('question',3000),('description',6000),('resolutionCriteria',6000)])
      or isinstance(provider_events,list) and len(provider_events)>20):metadata['incomplete']=True
  if any(metadata.values()) or any(flag in metadata for flag in ('closed','active')):record['proposition_metadata']=metadata
  # Snapshot identity includes observation and values. Re-reading the same
  # snapshot is stable; a later observation is a new snapshot, never history.
  record['expectation_id']='market-expectation-v1-'+hashlib.sha256(json.dumps(record,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()
  if mid in records and records[mid]!=record:conflicts.add(mid)
  else:records[mid]=record
 return [records[mid] for mid in sorted(records) if mid not in conflicts][:20]

def project_expectations(events,records,mapping=None):
 from .radar_event_expectation_linker import link_events,CONTRACT as LINK_CONTRACT,identify
 by_market={};conflicts=set()
 for record in records[:100]:
  mid=record['market_id']
  if mid in by_market and by_market[mid]!=record:conflicts.add(mid)
  else:by_market[mid]=record
 rows=[deepcopy(by_market[m]) for m in sorted(by_market) if m not in conflicts][:20];event_ids={e['event_id'] for e in events};market_ids={r['market_id'] for r in rows}
 decisions=link_events(events,rows)
 mapping_status='DETERMINISTIC_EVALUATED';links={}
 if mapping is None:
  links={p['expectation_market_id']:p for p in decisions if p['link_status']=='LINKED'}
 if mapping is not None:
  expanded={e:([value] if isinstance(value,str) else value) for e,value in mapping.items()} if isinstance(mapping,dict) else {}
  valid=isinstance(mapping,dict) and len(mapping)<=100 and all(isinstance(e,str) and e in event_ids and isinstance(ms,list) and 0<len(ms)<=20 and all(isinstance(m,str) and m in market_ids for m in ms) for e,ms in expanded.items())
  all_ids=[m for ms in expanded.values() for m in ms] if valid else []
  if valid and len(set(all_ids))==len(all_ids):
   decisions=[identify({**p,'link_status':'LINKED','link_method':'EXACT_CURATED_MAPPING','confidence_class':'HIGH','reason':'EXPLICIT_CURATOR_ASSERTED_RELATIONSHIP','matched_terms':[]}) if p['expectation_market_id'] in expanded.get(p['canonical_event_id'],[]) else identify({**p,'link_status':'NO_MATCH','confidence_class':None,'matched_terms':[],'reason':'NOT_IN_EXPLICIT_CURATED_MAPPING'}) for p in decisions]
   links={p['expectation_market_id']:p for p in decisions if p['link_status']=='LINKED'};mapping_status='AVAILABLE'
  else:
   mapping_status='INVALID_MAPPING'
   decisions=[identify({**p,'link_status':'INSUFFICIENT_EVIDENCE','confidence_class':None,'matched_terms':[],'reason':'INVALID_EXPLICIT_CURATED_MAPPING'}) for p in decisions]
 for row in rows:
  row.pop('event_expectation_link',None)
  link=links.get(row['market_id']);event_id=link['canonical_event_id'] if link else None
  row.update(canonical_event_id=event_id,link_status='LINKED' if event_id else 'UNLINKED',link_method=link['link_method'] if link else None)
  if link:row['event_expectation_link']=deepcopy(link)
 enriched=[{**event,'market_expectation_ids':[r['expectation_id'] for r in rows if r['canonical_event_id']==event['event_id']]} for event in events]
 return dict(market_expectation_contract=CONTRACT,market_expectations=rows,expectation_link_status=mapping_status,event_expectation_link_contract=LINK_CONTRACT,event_expectation_links=decisions,events=enriched)

class NoRedirect(HTTPRedirectHandler):
 def redirect_request(self,*args,**kwargs):raise ExpectationError('REDIRECT_NOT_ALLOWED')

def fetch_gamma():
 request=Request(ENDPOINT,headers={'User-Agent':'EventCentricDynamicDiscovery/1.0','Accept':'application/json'})
 opener=build_opener(HTTPSHandler(context=ssl.create_default_context()),NoRedirect())
 with opener.open(request,timeout=TIMEOUT) as response:
  if response.status!=200 or response.geturl()!=ENDPOINT:raise ExpectationError('INVALID_RESPONSE')
  if response.headers.get_content_type()!='application/json':raise ExpectationError('INVALID_CONTENT_TYPE')
  data=response.read(MAX_BYTES+1)
 if len(data)>MAX_BYTES:raise ExpectationError('RESPONSE_TOO_LARGE')
 return data

class MarketExpectationSensor:
 def __init__(self,*,fetcher=fetch_gamma,interval=1800,clock=None):
  if type(interval) is not int or not 300<=interval<=86400:raise ExpectationError('INVALID_REFRESH_INTERVAL')
  self.fetcher,self.interval=fetcher,interval
  self.clock=clock or (lambda:datetime.now(timezone.utc).isoformat().replace('+00:00','Z'))
  self.lock,self.refresh_lock=threading.RLock(),threading.Lock();self.stop_event=threading.Event();self.thread=None;self.records=[]
  self.state=dict(enabled=True,status='STARTING',last_attempt_at=None,last_success_at=None,reason=None)
 def refresh(self):
  if not self.refresh_lock.acquire(blocking=False):return False
  try:
   observed=self.clock()
   with self.lock:self.state['last_attempt_at']=observed
   try:
    rows=parse_markets(self.fetcher(),observed)
    with self.lock:self.records=rows;self.state.update(status='LIVE' if rows else 'EMPTY',last_success_at=observed,reason=None)
    return True
   except Exception:
    with self.lock:self.state.update(status='LAST_VALID_FALLBACK' if self.records else 'UNAVAILABLE',reason='PROVIDER_REQUEST_FAILED')
    return False
  finally:self.refresh_lock.release()
 def snapshot(self):
  with self.lock:return deepcopy(self.records),dict(self.state)
 def start(self):
  with self.lock:
   if self.thread is None:self.thread=threading.Thread(target=self._loop,name='radar-expectation-refresh',daemon=True);self.thread.start()
 def _loop(self):
  while not self.stop_event.is_set():
   self.refresh()
   if self.stop_event.wait(self.interval):break
 def close(self):
  self.stop_event.set()
  if self.thread:self.thread.join(TIMEOUT+2)
