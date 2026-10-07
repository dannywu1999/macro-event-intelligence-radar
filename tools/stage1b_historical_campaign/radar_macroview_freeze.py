"""Pure point-in-time evidence snapshots, with a separate non-persisted preview.

No filesystem, clock, provider, control-plane or decision-system dependencies.
Callers supply an explicit freeze key/time. Returned nested contents never share
mutable references with News, facts, expectations or geography input objects.
"""
from __future__ import annotations
from copy import deepcopy
from datetime import datetime,timezone
import hashlib,json
CONTRACT='MACROVIEW_FREEZE_V0'
class MacroViewError(ValueError):pass

def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)
def digest(value):return hashlib.sha256(canonical(value).encode('utf-8')).hexdigest()
def select(row,keys):return {key:deepcopy(row.get(key)) for key in keys}

def unique_records(rows,key,required,accept):
 records={}
 for row in rows:
  if not isinstance(row,dict):raise MacroViewError('INVALID_EVIDENCE_ROW')
  identity=row.get(key)
  if identity not in required:continue
  if not accept(row):raise MacroViewError('EVIDENCE_AUTHORITY_OR_LINK_INVALID')
  if identity in records and records[identity]!=row:raise MacroViewError('CONFLICTING_EVIDENCE')
  records[identity]=row
 if set(records)!=set(required):raise MacroViewError('REFERENCED_EVIDENCE_MISSING')
 return [records[identity] for identity in sorted(records)]

def freeze_macroview(view,event_id,*,freeze_key,frozen_at=None):
 if not isinstance(freeze_key,str) or not freeze_key.strip() or len(freeze_key)>1000:raise MacroViewError('EXPLICIT_FREEZE_KEY_REQUIRED')
 if frozen_at is not None:
  try:
   dt=datetime.fromisoformat(frozen_at.replace('Z','+00:00'))
   if dt.tzinfo is None:raise ValueError('naive')
   frozen_at=dt.astimezone(timezone.utc).isoformat().replace('+00:00','Z')
  except (ValueError,TypeError,AttributeError,OverflowError) as e:raise MacroViewError('INVALID_FREEZE_TIME') from e
 matches=[e for e in view.get('events',[]) if e.get('event_id')==event_id]
 if len(matches)!=1:raise MacroViewError('EXACT_EVENT_REQUIRED')
 event=matches[0]
 if event.get('verification_status')!='UNVERIFIED_NEWS':raise MacroViewError('UNSUPPORTED_EVENT_STATUS')
 refs=event.get('article_references') or []
 if not refs:raise MacroViewError('NEWS_REFERENCES_REQUIRED')
 fact_ids=event.get('official_evidence_ids') or []
 expectation_ids=event.get('market_expectation_ids') or []
 if not all(isinstance(ids,list) and len(ids)<=512 and all(isinstance(i,str) and i for i in ids) for ids in (refs,fact_ids,expectation_ids)):raise MacroViewError('INVALID_EVIDENCE_REFERENCES')
 news=unique_records(view.get('items',[]),'article_reference',refs,lambda r:r.get('verification_status')=='UNVERIFIED_NEWS')
 facts=unique_records(view.get('official_evidence',[]),'official_evidence_id',fact_ids,lambda r:r.get('canonical_event_id')==event_id and r.get('evidence_status')=='OFFICIAL_CONFIRMED' and r.get('authority_role')=='FACT_AUTHORITY')
 expectations=unique_records(view.get('market_expectations',[]),'expectation_id',expectation_ids,lambda r:r.get('canonical_event_id')==event_id and r.get('link_status')=='LINKED' and r.get('authority_role')=='EXPECTATION_SENSOR')
 snapshot={
  'event':select(event,('event_id','event_title','verification_status','event_occurred_at','first_detected_at','latest_article_at','geography_status','geography','event_geography','context_geography','institution_context','headline_explanation','context_contract')),
  'news':[select(r,('article_reference','title','news_source','observed_at','reported_at','reported_time_kind','event_occurred_at','verification_status')) for r in news],
  'official_evidence':[select(r,('official_evidence_id','authority_name','authority_role','document_title','document_url','document_reference','fact_proposition','published_at','first_seen_at','retrieved_at','effective_at','evidence_status','canonical_event_id','link_status')) for r in facts],
  'market_expectations':[select(r,('expectation_id','provider','authority_role','market_id','market_slug','question','outcomes','probabilities','probability_semantics','observed_at','market_close_time','market_url','link_status','canonical_event_id','link_method')) for r in expectations]}
 # Add only supplied A8 observations. Existing freezes keep their original bytes.
 if event.get('market_reality') is not None:
  snapshot['market_reality']=deepcopy(event['market_reality'])
 unknowns=[]
 if event.get('event_occurred_at') is None:unknowns.append('EVENT_OCCURRENCE_TIME_UNKNOWN')
 if event.get('geography_status') not in {'KNOWN','MAPPED'}:unknowns.append('GEOGRAPHY_UNKNOWN')
 if not facts:unknowns.append('NO_OFFICIAL_EVIDENCE')
 if not expectations:unknowns.append('NO_LINKED_MARKET_EXPECTATION')
 if any(r.get('reported_at') is None for r in news):unknowns.append('NEWS_REPORTED_TIME_UNKNOWN')
 if any(r.get('published_at') is None for r in facts):unknowns.append('OFFICIAL_PUBLICATION_TIME_UNKNOWN')
 if any(r.get('market_close_time') is None for r in expectations):unknowns.append('MARKET_CLOSE_TIME_UNKNOWN')
 if any(r.get('probabilities') is None or any(p is None for p in r['probabilities']) for r in expectations):unknowns.append('MARKET_PROBABILITIES_UNKNOWN')
 result=dict(contract_version=CONTRACT,canonical_event_id=event_id,freeze_key=freeze_key,frozen_at=frozen_at,news_article_references=sorted(set(refs)),official_evidence_ids=sorted(set(fact_ids)),market_expectation_ids=sorted(set(expectation_ids)),fact_state='PARTIAL_OFFICIAL_EVIDENCE' if facts else 'NEWS_ONLY',expectation_state='EXPECTATION_PRESENT' if expectations else 'NONE',unknowns=unknowns,snapshot=snapshot,provenance={'snapshot_sha256':digest(snapshot),'news_sha256':digest(snapshot['news']),'official_sha256':digest(snapshot['official_evidence']),'expectation_sha256':digest(snapshot['market_expectations'])})
 result['macroview_id']='macroview-freeze-v0-'+digest(result)
 return result

def preview_macroview(view,event_id):
 result=freeze_macroview(view,event_id,freeze_key='CURRENT_PREVIEW',frozen_at=None)
 result.update(contract_version='MACROVIEW_PREVIEW_V0',preview_only=True,persisted=False)
 result.pop('macroview_id');result['macroview_id']='macroview-preview-v0-'+digest(result)
 return result

def build_previews(view):
 previews=[]
 for event in view.get('events',[])[:100]:
  try:previews.append(preview_macroview(view,event['event_id']))
  except MacroViewError:continue
 return previews
