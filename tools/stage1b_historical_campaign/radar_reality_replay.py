"""Read-only reconstruction from as-of SQL rows only; no current-file/provider path."""
from copy import deepcopy
from .radar_intelligence_store import time_value,StoreError
from .radar_macroview_freeze import freeze_macroview,MacroViewError
CONTRACT='POINT_IN_TIME_REPLAY_V0'

def replay_event_as_of(store,event_id,as_of,*,internal=False):
 timestamp,limit=time_value(as_of)
 observations=store.read_as_of(event_id,timestamp)
 if any(row['observed_us']>limit for row in observations):raise StoreError('FUTURE_OBSERVATION_REJECTED')
 latest={}
 for row in observations:latest[(row['observation_kind'],row['entity_id'])]=row
 visible=[row for row in latest.values() if row['canonical_event_id']==event_id or row['observation_kind']=='SOURCE_STATE']
 visible.sort(key=lambda row:(row['observed_us'],row['observation_id']))
 def kind(name):return [r for r in visible if r['observation_kind']==name]
 states=kind('CANONICAL_EVENT_STATE');news=kind('NEWS_ARTICLE');facts=kind('OFFICIAL_EVIDENCE');markets=kind('MARKET_EXPECTATION')
 result=dict(contract_version=CONTRACT,canonical_event_id=event_id,as_of=timestamp,time_basis='SYSTEM_RECORDED_TIME',news_observations=[],official_evidence_observations=[],market_expectation_observations=[],source_states=kind('SOURCE_STATE'),reconstructed_macroview=None,unknowns=[],observation_ids=[],replay_status='NO_OBSERVATIONS')
 projection=None
 result['context_observations']=[]
 if states:
  event=deepcopy(states[-1]['payload'])
  # Never re-infer historical context using today's registry or current files.
  contexts=kind('CONTEXT_GEOGRAPHY')
  if contexts:
   context=contexts[-1]['payload']
   for key in ('context_geography','institution_context','headline_explanation'):
    event[key]=deepcopy(context[key])
   event['context_contract']=context['contract_version']
  else:
   for key in ('context_geography','institution_context','headline_explanation','context_contract'):
    event.pop(key,None)
  refs=set(event.get('article_references') or [])
  news=[r for r in news if r['entity_id'] in refs and r['payload'].get('verification_status')=='UNVERIFIED_NEWS']
  facts=[r for r in facts if r['payload'].get('canonical_event_id')==event_id and r['payload'].get('authority_role')=='FACT_AUTHORITY' and r['payload'].get('evidence_status')=='OFFICIAL_CONFIRMED']
  markets=[r for r in markets if r['payload'].get('canonical_event_id')==event_id and r['payload'].get('authority_role')=='EXPECTATION_SENSOR' and r['payload'].get('link_status')=='LINKED']
  # Rebuild links from visible evidence, never copy latest-file IDs/timeline
  # into a historical input. Market refreshes do not enter the News timeline.
  event['official_evidence_ids']=[r['payload']['official_evidence_id'] for r in facts]
  event['official_evidence_count']=len(facts)
  event['market_expectation_ids']=[r['payload']['expectation_id'] for r in markets]
  event.pop('timeline',None);event.pop('status_summary',None)
  projection=dict(events=[event],items=[deepcopy(r['payload']) for r in news],official_evidence=[deepcopy(r['payload']) for r in facts],market_expectations=[deepcopy(r['payload']) for r in markets])
  result.update(replay_status='AVAILABLE')
  selected=states+news+facts+markets+contexts+kind('SOURCE_STATE');selected.sort(key=lambda r:(r['observed_us'],r['observation_id']))
  active_ids={r['observation_id'] for r in selected}
  history=[{**r,'active_at_as_of':r['observation_id'] in active_ids} for r in observations if r['canonical_event_id']==event_id or r['observation_kind']=='SOURCE_STATE']
  result['context_observations']=[r for r in history if r['observation_kind']=='CONTEXT_GEOGRAPHY']
  result['news_observations']=[r for r in history if r['observation_kind']=='NEWS_ARTICLE']
  result['official_evidence_observations']=[r for r in history if r['observation_kind']=='OFFICIAL_EVIDENCE']
  result['market_expectation_observations']=[r for r in history if r['observation_kind']=='MARKET_EXPECTATION']
  result['observation_ids']=[r['observation_id'] for r in history]
  result['active_observation_ids']=[r['observation_id'] for r in selected]
  try:
   reconstructed=freeze_macroview(projection,event_id,freeze_key='REPLAY_AS_OF/'+timestamp,frozen_at=timestamp)
   reconstructed['reconstructed']=True;reconstructed['persisted']=False
   result['reconstructed_macroview']=reconstructed;result['unknowns']=reconstructed['unknowns']
  except MacroViewError:
   result['replay_status']='PARTIAL_OBSERVATIONS';result['unknowns']=['REFERENCED_NEWS_NOT_OBSERVED']
 else:
  result['unknowns']=['EVENT_NOT_OBSERVED_AT_AS_OF']
  # Unknown future identity cannot be revealed via a current catalogue lookup.
  result['source_states']=[]
 if internal:result['_projection']=projection
 return result
