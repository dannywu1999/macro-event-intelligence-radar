"""Read-only M3 receipt analysis. No network, acquisition, source or ledger writes."""
from pathlib import Path
from datetime import datetime,timezone,timedelta
from collections import Counter
import argparse,json,hashlib,re
from research import m3_discovery as m

def dt(value):return datetime.fromisoformat(value.replace('Z','+00:00'))
def category(row):
    title=row['title'];sid=row['source_id']
    if sid=='bls_cpi':return 'INFLATION'
    if sid=='bls_employment':return 'EMPLOYMENT'
    for pattern,name in [(r'\b(?:tariff|sanction|export control|trade deal)','TRADE_POLICY'),(r'\b(?:oil|crude|energy|fuel|gas supply)','ENERGY_SUPPLY'),(r'\b(?:war|missile|invasion|ceasefire|military strike)','GEOPOLITICAL_RISK'),(r'\b(?:Fed|FOMC|Federal Open Market Committee|discount rate|central bank|monetary|interest rate)','MONETARY_POLICY')]:
        if re.search(pattern,title,re.I):return name
    return 'MACRO_CONTEXT' if row['research_relevant'] else 'OTHER'

def analyze(root,benchmark):
    root=Path(root);p=m.project(root);plan=m.pinned_plan(root)
    reserves=[m.read(x) for x in root.glob('cycles/*/*.reserve.json')]
    acks=[m.read(x) for x in root.glob('cycles/*/*.ack.json')]
    parsed=[m.read(x) for x in root.glob('cycles/*/*.parsed.json')]
    terminals=[m.read(x) for x in root.glob('cycles/*/*.terminal.json')]
    auxres=[m.read(x) for x in root.glob('auxiliary/*.reserve.json')]
    auxacks=[m.read(x) for x in root.glob('auxiliary/*.ack.json')]
    end=max([x['completed_at'] for x in terminals]+[x['retrieved_at'] for x in auxacks])
    start=min(x['reserved_at'] for x in reserves)
    at=dt(end);rows=p['observations'];latest={r['article_identity']:r for r in rows}
    matrix=[]
    for s in plan['sources']:
        src=[x for x in rows if x['source_id']==s['id']];last={x['article_identity']:x for x in src}
        rs=[x for x in reserves if x['source_id']==s['id']];ts=sorted([x for x in terminals if x['source_id']==s['id']],key=lambda x:x['completed_at'])
        ps=sorted([x for x in parsed if x['source_id']==s['id']],key=lambda x:x['retrieved_at']);aa=[x for x in acks if x['source_id']==s['id']]
        latestpub=max([x['source_published_at'] for x in last.values() if x['source_published_at']],default=None)
        matrix.append({'source_id':s['id'],'name':s['name'],'source_url':s['url'],'source_kind':s['kind'],'rights_scope':s['terms_status'],'attempts':len(rs),'HTTP_statuses':[x.get('http_status') for x in ts],'parser_successes':len(ps),'raw_articles_latest':ps[-1]['parse_diagnostics']['raw_article_count'] if ps else None,'distinct_retained_articles':len(last) if ps else None,'valid_exact_timestamps':sum(x['publication_precision']=='EXACT_SOURCE_REPORTED' for x in last.values()) if ps else None,'relevant_article_sets':sum(x['research_relevant'] for x in last.values()) if ps else None,'relevant_in_48h':sum(x['research_relevant'] and x['source_published_at'] is not None and x['publication_precision']=='EXACT_SOURCE_REPORTED' and at-timedelta(hours=48)<=dt(x['source_published_at'])<=at for x in last.values()) if ps else None,'duplicates_across_cycles':sum(x['observation_kind']=='duplicate' for x in src),'latest_source_publication':latestpub,'source_publication_age_hours':round((at-dt(latestpub)).total_seconds()/3600,3) if latestpub and len(latestpub)>10 else None,'latest_request_status':ts[-1]['status'] if ts else 'UNATTEMPTED','failure_class':ts[-1].get('failure_class') or ('HTTP_STATUS_SOURCE_DENIAL' if ts[-1].get('http_status') in (403,406) else None) if ts else None,'prospective_eligible':bool(ts and ts[-1]['status']=='SUCCESS')})
    cycles=[]
    for cycle in sorted({x['cycle_id'] for x in reserves}):
        rr=[x for x in reserves if x['cycle_id']==cycle];tt=[x for x in terminals if x['cycle_id']==cycle];obs=[x for x in rows if x['cycle_id']==cycle]
        cycles.append({'cycle_id':cycle,'start_utc':min(x['reserved_at'] for x in rr),'end_utc':max(x['completed_at'] for x in tt),'GET_reservations':len(rr),'successes':sum(x['status']=='SUCCESS' for x in tt),'failures':sum(x['status']!='SUCCESS' for x in tt),'article_observations':len(obs),'new_to_experiment':sum(x['observation_kind']=='new' for x in obs),'updates':sum(x['observation_kind']=='updated' for x in obs),'duplicates':sum(x['observation_kind']=='duplicate' for x in obs)})
    benchmark_results=[{**c,'found':any(m.normalized_url(x['url'])==m.normalized_url(c['source_url']) for x in rows)} for c in benchmark['cases']]
    candidates=[]
    for event in p['canonical_candidates']['events']:
        members=[r for r in latest.values() if r['url'] in event['article_references']]
        for row in members:
            pub=row['source_published_at'];age=(at-dt(pub)).total_seconds()/3600 if pub and len(pub)>10 else None
            candidates.append({'event_id':event['event_id'],'identity_contract':'CANONICAL_EVENT_V0_ARTICLE_SET_NOT_PROVEN_DISTINCT_WORLD_EVENT','title_original':row['title'],'source_id':row['source_id'],'source_url':row['url'],'source_published_at':pub,'publication_precision':row['publication_precision'],'first_observed_at_in_M3':row['first_observed_at'],'last_retrieved_at':row['retrieved_at'],'recorded_at':row['recorded_at'],'category':category(row),'selection_basis':row['research_relevance_basis'],'freshness':'SOURCE_TIME_UNKNOWN' if age is None else 'IN_48H' if 0<=age<=48 else 'IN_7D_CONTEXT' if 48<age<=168 else 'OLDER_CONTEXT','article_kind':'POLICY_MINUTES_CONTEXT_NOT_NEW_RATE_DECISION' if row['research_relevance_basis']=='NAMED_FED_POLICY_MINUTES_CONTEXT_NOT_NEW_RATE_DECISION' else 'SPEECH_ANALYSIS_NOT_NEW_POLICY_DECISION' if row['source_id']=='ecb' and '/key/' in row['url'] else 'DISCOVERY_NOT_VERIFIED_PROPOSITION','official_verification':'OFFICIAL_VERIFICATION_PENDING','global_first_seen_proven':False,'source_to_observation_status':row['source_to_observation_status'],'source_to_observation_seconds':row['source_to_observation_seconds']})
    post_baseline=[row for row in rows if row['cycle_id']!=cycles[0]['cycle_id'] and row['observation_kind']=='new']
    knownbytes=sum(x['response_bytes'] for x in acks+auxacks)
    unknown=sum(not any(x['source_id']==r['source_id'] and x['cycle_id']==r['cycle_id'] for x in acks) for r in reserves)
    assert len(reserves)+len(auxres)<=200 and knownbytes+unknown*m.MAX_BODY<=50_000_000
    return {'scope':'BOUNDED_RESEARCH_OBSERVATION_NOT_24_7','GLOBAL_FIRST_SEEN_NOT_PROVEN':True,'NOT_LIVE_TRADING_SIGNAL':True,'REAL_TIME_DETECTION_PROVEN':False,'observation_start_utc':start,'observation_end_utc':end,'source_cycle_window_seconds':(dt(cycles[-1]['end_utc'])-dt(cycles[0]['start_utc'])).total_seconds(),'GET_requests_reserved':len(reserves)+len(auxres),'feed_GET_requests':len(reserves),'official_document_GET_requests':len(auxres),'payload_bytes_read_known':knownbytes,'unknown_no_ACK_requests':unknown,'charged_payload_upper_bound':knownbytes+unknown*m.MAX_BODY,'transport_wire_bytes':'UNKNOWN_NOT_PACKET_CAPTURED','source_count_tested':len(plan['sources']),'healthy_source_count':sum(x['prospective_eligible'] for x in matrix),'unique_articles':len(latest),'article_observations':len(rows),'new_articles_after_baseline':len(post_baseline),'new_relevant_articles_after_baseline':sum(row['research_relevant'] for row in post_baseline),'canonical_article_set_candidates':len(p['canonical_candidates']['events']),'relevant_48h_candidates':sum(x['freshness']=='IN_48H' for x in candidates),'relevant_7d_candidates':sum(x['freshness'] in ('IN_48H','IN_7D_CONTEXT') for x in candidates),'cycle_start_interval_seconds':(dt(cycles[1]['start_utc'])-dt(cycles[0]['start_utc'])).total_seconds() if len(cycles)>1 else None,'cycles':cycles,'source_matrix':matrix,'event_candidates':candidates,'benchmark':{'frozen_at':benchmark['frozen_at'],'scope':benchmark['scope'],'found':sum(x['found'] for x in benchmark_results),'total':len(benchmark_results),'results':benchmark_results},'as_of_query_implemented':False}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',required=True);p.add_argument('--benchmark',required=True);p.add_argument('--output',required=True);a=p.parse_args()
    result=analyze(a.root,json.loads(Path(a.benchmark).read_bytes()))
    output=Path(a.output);output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('M3_ANALYSIS_COMPLETE; GETs='+str(result['GET_requests_reserved'])+'; healthy='+str(result['healthy_source_count'])+'; unique_articles='+str(result['unique_articles']))
