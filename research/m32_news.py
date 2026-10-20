"""M3.2 news-first, metadata-only research; no production registrations or writers."""
import argparse,json,re
from html import unescape
from pathlib import Path
from datetime import datetime,timezone
from research import m3_discovery as m, m31_access as access

VERSION='M3.2_NEWS_FIRST_V2'
SOURCES={
 'globalvoices':{'id':'globalvoices','name':'Global Voices','url':'https://globalvoices.org/feed/','article_hosts':['globalvoices.org'],'terms_status':'CC_BY_3_0_AUTHOR_ATTRIBUTION_REQUIRED','terms_url':'https://globalvoices.org/about/','license_url':'https://creativecommons.org/licenses/by/3.0/'},
 '360info':{'id':'360info','name':'360info','url':'https://360info.org/feed/','article_hosts':['360info.org'],'terms_status':'CC_BY_4_0_AUTHOR_ATTRIBUTION_REQUIRED','terms_url':'https://360info.org/how-to-use-our-content/','license_url':'https://creativecommons.org/licenses/by/4.0/'},
 'cna_business':{'id':'cna_business','name':'CNA Business','url':'https://www.channelnewsasia.com/api/v1/rss-outbound-feed?_format=xml&category=6936','article_hosts':['channelnewsasia.com'],'terms_status':'PERSONAL_NONCOMMERCIAL_ONLY_NO_REDISTRIBUTION','terms_url':'https://www.channelnewsasia.com/rss/rssterms','license_url':None},
}
ENDPOINTS={k:v['url'] for k,v in SOURCES.items()}
ENDPOINTS.update({'bea_calendar':'https://www.bea.gov/news/schedule','bls_calendar':'https://www.bls.gov/schedule/2026/home.htm','fed_official_feed':'https://www.federalreserve.gov/feeds/press_monetary.xml'})
# Two qualification GETs in V1 are preserved in their original separate namespace.
# V2 reserves at most the remaining 118 requests, with a conservative 16 MB ceiling.
CONTRACT=access.AccessContract(VERSION,'M32','M32_IDENTITY.json','M32_EXPERIMENT_ONLY_NOT_GLOBAL_FIRST_SEEN',118,16_000_000,5,ENDPOINTS,{k:(k,) for k in ENDPOINTS},{k:k for k in ENDPOINTS})
OFFICIAL_ENDPOINTS={'boj_schedule':'https://www.boj.or.jp/en/mopo/mpmsche_minu/','bok_schedule':'https://www.bok.or.kr/eng/main/contents.do?menuNo=400020'}
OFFICIAL_CONTRACT=access.AccessContract('M3.2_OFFICIAL_CONTEXT_V1','M32','M32_OFFICIAL_IDENTITY.json','OFFICIAL_CALENDAR_CONTEXT_NOT_POLICY_RESULT',2,5_000_000,2,OFFICIAL_ENDPOINTS,{k:(k,) for k in OFFICIAL_ENDPOINTS},{k:k for k in OFFICIAL_ENDPOINTS})

def acquire(root,endpoint,request_id,enable_network=False,fetcher=m.bounded_get,official=False):
    """One study budget includes immutable V1 qualification, V2, and official context."""
    if not enable_network:raise ValueError('NETWORK_DISABLED')
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',request_id):raise ValueError('REQUEST_IDENTITY')
    root=m.safe_root(root);m.assert_external_root(root)
    if root.name!=('OFFICIAL' if official else 'RUN_V2'):raise ValueError('STUDY_NAMESPACE')
    root.parent.mkdir(parents=True,exist_ok=True)
    lock=root.parent/'NETWORK_LOCK';lock.mkdir(exist_ok=True)
    with m.owner_lock(lock):
        # An already spent ID may resume without consuming or issuing a request.
        reserved=root/'HTTP'/(request_id+'.reserve.json')
        if reserved.exists():
            contract=OFFICIAL_CONTRACT if official else CONTRACT
            access.validate_root(root,contract)
            r=m.read(reserved)
            if r['endpoint_id']!=endpoint or r['request_id']!=request_id or r['url']!=contract.endpoints.get(endpoint):raise ValueError('RESUME_IDENTITY_MISMATCH')
            return {'status':'ALREADY_RESERVED_NO_RETRY','request_id':request_id}
        spent=size=0
        for name in ('RUN','RUN_V2','OFFICIAL'):
            child=m.safe_root(root.parent/name)
            count,nbytes=access.accounting(child);spent+=count;size+=nbytes
        if spent>=120 or size+m.MAX_BODY>20_000_000:raise ValueError('STUDY_BUDGET_EXHAUSTED')
        return access.acquire(root,endpoint,request_id,True,fetcher,parse if not official and endpoint in SOURCES else None,OFFICIAL_CONTRACT if official else CONTRACT)

def parse(endpoint,body):
    if endpoint not in SOURCES:raise ValueError('NOT_NEWS_ENDPOINT')
    rows,summary=m.parse_metadata(body,SOURCES[endpoint])
    for row in rows:
        row['terms_url']=SOURCES[endpoint]['terms_url'];row['license_url']=SOURCES[endpoint]['license_url']
        row['authority_role']='NEWS_DISCOVERY_NOT_OFFICIAL_VERIFICATION'
        row['public_export_allowed']=endpoint!='cna_business'
    return {'records':rows,'summary':summary}

# Explicit rules are discovery hypotheses, never evidence of policy action or price direction.
RULES=[('MONETARY_POLICY',r'\b(?:Federal Reserve|FOMC|ECB|Bank of Japan|central bank|interest rates?|rate cuts?|rate hikes?)\b'),
 ('INFLATION_EMPLOYMENT',r'\b(?:inflation|CPI|consumer prices?|payrolls?|unemployment|jobs report|PCE)\b'),
 ('TRADE_SANCTIONS',r'\b(?:tariffs?|sanctions?|trade war|export (?:ban|controls?|restrictions?))\b'),
 ('ENERGY_SUPPLY',r'\b(?:oil|natural gas|LNG|OPEC|pipeline|Strait of Hormuz)\b.*\b(?:supply|output|production|disruption|shutdown|blockade|export ban|cuts?)\b|\b(?:supply|output|production|disruption|shutdown|blockade)\b.*\b(?:oil|natural gas|LNG|OPEC|pipeline)\b'),
 ('MATERIAL_GEOPOLITICS',r'\b(?:war|ceasefire|invasion|missile|blockade)\b')]

def relevance(row):
    for category,pattern in RULES:
        if re.search(pattern,row['title'],re.I):return category
    return None

def utc(value):
    d=datetime.fromisoformat(value.replace('Z','+00:00'))
    if d.tzinfo is None:raise ValueError('UTC_TIMESTAMP_REQUIRED')
    return d.astimezone(timezone.utc)

def project(root,as_of=None):
    root=access.validate_root(root,CONTRACT)
    cutoff=utc(as_of or m.now())
    observations=[];articles={};rejects={};requests=[]
    for p in sorted((root/'HTTP').glob('*.parsed.json')):
        receipt=m.read(p);ep=receipt['endpoint_id']
        if ep not in SOURCES:continue
        if p.name!=receipt['request_id']+'.parsed.json':raise ValueError('REQUEST_STEM_BINDING')
        stem=p.with_name(p.name.replace('.parsed.json',''))
        ack=m.read(Path(str(stem)+'.ack.json'));body=Path(str(stem)+'.body').read_bytes()
        if m.sha(body)!=ack['response_sha256'] or receipt['result']!=parse(ep,body):raise ValueError('RECEIPT_INTEGRITY')
        reserve=m.read(Path(str(stem)+'.reserve.json'))
        terminal=m.read(Path(str(stem)+'.terminal.json'))
        if p.name!=receipt['request_id']+'.parsed.json' or any(x['request_id']!=receipt['request_id'] or x['endpoint_id']!=ep for x in (reserve,ack,terminal)):raise ValueError('REQUEST_STEM_BINDING')
        if terminal['status']!='SUCCESS' or terminal['http_status']!=200 or reserve['experiment_version']!=VERSION or ack['scope']!=CONTRACT.scope:raise ValueError('COMPLETION_OR_VERSION_BINDING')
        if any(x['request_id']!=receipt['request_id'] or x['endpoint_id']!=ep for x in (reserve,ack)) or ack['url']!=ENDPOINTS[ep] or reserve['url']!=ENDPOINTS[ep] or ack['http']['http_status']!=200 or len(body)!=ack['response_bytes']:raise ValueError('SOURCE_RECEIPT_BINDING')
        clocks=list(map(utc,[reserve['reserved_at'],ack['started_at'],ack['retrieved_at'],ack['recorded_at'],receipt['recorded_at'],terminal['completed_at']]))
        if clocks!=sorted(clocks) or receipt['retrieved_at']!=ack['retrieved_at'] or receipt['http_ack_recorded_at']!=ack['recorded_at'] or receipt['response_sha256']!=ack['response_sha256']:raise ValueError('CLOCK_OR_ACK_BINDING')
        if utc(terminal['completed_at'])>cutoff:continue
        receipt=dict(receipt,evidence_available_at=terminal['completed_at'])
        requests.append(receipt)
    for receipt in sorted(requests,key=lambda x:(x['recorded_at'],x['request_id'])):
        for reason,n in receipt['result']['summary']['rejected_by_reason'].items():rejects[reason]=rejects.get(reason,0)+n
        for row in receipt['result']['records']:
            aid=m.article_identity(row['url']);cid=m.content_identity({'title':row['title'],'news_source':{'url':row['url'],'name':row['source_name']},'source_published_at':row['source_published_at'],'source_timestamp_precision':row['publication_precision']})
            prev=articles.get(aid);status='NEW_TO_EXPERIMENT' if prev is None else 'DUPLICATE' if prev['content_id']==cid else 'UPDATED'
            item=dict(row,article_id=aid,content_id=cid,first_observed_at=receipt['retrieved_at'] if prev is None else prev['first_observed_at'],first_recorded_at=receipt['recorded_at'] if prev is None else prev['first_recorded_at'],evidence_available_at=receipt['evidence_available_at'],last_observed_at=receipt['retrieved_at'],last_recorded_at=receipt['recorded_at'])
            articles[aid]=item
            observations.append({'request_id':receipt['request_id'],'article_id':aid,'status':status,'retrieved_at':receipt['retrieved_at'],'recorded_at':receipt['recorded_at']})
    candidates=[]
    for item in articles.values():
        category=relevance(item)
        if not category:continue
        published=item['source_published_at'];age=None
        if item['publication_precision']=='EXACT_SOURCE_REPORTED' and published:
            age=(cutoff-utc(published)).total_seconds()/3600
        if age is not None and age<0:continue
        if item['publication_precision']=='DATE_ONLY' and published and published>cutoff.date().isoformat():continue
        candidates.append(dict(item,event_candidate_id='M32-ARTICLE-'+item['article_id'],category=category,
            freshness='FUTURE_SOURCE_TIME_EXCLUDED' if age is not None and age<0 else 'RECENT_48H' if age is not None and age<=48 else 'OLDER_CONTEXT' if age is not None else 'TIME_UNKNOWN',
            age_hours=age,discovery_status='NEWS_DISCOVERED',official_status='OFFICIAL_VERIFICATION_PENDING',
            event_grouping='ARTICLE_SET_CANDIDATE_NOT_PROVEN_DISTINCT_WORLD_EVENT',claim_type='REPORTED_EXPECTATION_OR_ANONYMOUS_REPORT' if re.search(r'\b(?:poll|forecast|sources? say|may|expects?)\b',item['title'],re.I) else 'UNVERIFIED_NEWS_REPORT',detection_latency='UNKNOWN',macroview_status='RESEARCH_PREVIEW_ONLY',trade_ready=False))
    return {'version':VERSION,'as_of':cutoff.isoformat(),'scope':CONTRACT.scope,'articles':list(articles.values()),'observations':observations,'event_candidates':candidates,'rejected_by_reason':rejects,'article_count':len(articles),'candidate_count':len(candidates),'recent_48h_candidate_count':sum(x['freshness']=='RECENT_48H' for x in candidates),'breaking_news_detection_proven':False,'global_first_seen_proven':False}

def official_context(official_root,endpoint,as_of):
    """Verify only an exact calendar proposition; never a reported future rate decision."""
    root=access.validate_root(official_root,OFFICIAL_CONTRACT)
    stem=root/'HTTP'/('handoff_'+endpoint)
    terminal=m.read(Path(str(stem)+'.terminal.json'))
    if terminal['status']!='SUCCESS':return {'status':'OFFICIAL_VERIFICATION_PENDING','request_status':terminal['status']}
    reserve=m.read(Path(str(stem)+'.reserve.json'));ack=m.read(Path(str(stem)+'.ack.json'));body=Path(str(stem)+'.body').read_bytes()
    if any(x['request_id']!='handoff_'+endpoint or x['endpoint_id']!=endpoint for x in (reserve,ack,terminal)) or reserve['url']!=OFFICIAL_ENDPOINTS[endpoint] or ack['url']!=OFFICIAL_ENDPOINTS[endpoint] or ack['scope']!=OFFICIAL_CONTRACT.scope or reserve['experiment_version']!=OFFICIAL_CONTRACT.version:raise ValueError('OFFICIAL_RECEIPT_BINDING')
    if ack['http']['http_status']!=200 or terminal['http_status']!=200 or len(body)!=ack['response_bytes'] or m.sha(body)!=ack['response_sha256']:raise ValueError('OFFICIAL_BODY_INTEGRITY')
    clocks=list(map(utc,[reserve['reserved_at'],ack['started_at'],ack['retrieved_at'],ack['recorded_at'],terminal['completed_at']]))
    if clocks!=sorted(clocks):raise ValueError('OFFICIAL_CLOCK_ORDER')
    if utc(terminal['completed_at'])>utc(as_of):return {'status':'UNAVAILABLE_AS_OF','request_status':'LATER_OFFICIAL_OBSERVATION'}
    html=body.decode('utf-8',errors='strict')
    if endpoint=='boj_schedule':
        match=re.search(r'<h2\b[^>]*id="p2026"[^>]*>2026</h2>(.*?)(?=<h2\b|\Z)',html,re.S)
        expected=r'Oct\.\s*29\s*\(Thurs\.\),\s*30\s*\(Fri\.\)';date='2026-10-29/2026-10-30';proposition='BOJ monetary policy meeting is scheduled for October 29-30, 2026.'
    elif endpoint=='bok_schedule':
        match=re.search(r'<h3\b[^>]*>\s*2026\s*</h3>(.*?)(?=<h3\b|\Z)',html,re.S)
        expected=r'Oct\.\s*22\s*\(Thu\)';date='2026-10-22';proposition='BOK policy-setting meeting is scheduled for October 22, 2026.'
    else:raise ValueError('UNKNOWN_OFFICIAL_PROPOSITION')
    text=' '.join(unescape(re.sub('<[^>]+>',' ',match[1])).split()) if match else ''
    found=re.search(expected,text)
    if not found:return {'status':'OFFICIAL_VERIFICATION_PENDING','request_status':'CALENDAR_PROPOSITION_NOT_FOUND'}
    return {'status':'OFFICIAL_CONTEXT_VERIFIED','proposition':proposition,'scheduled_date':date,'scheduled_precision':'DATE_ONLY','source_url':ack['url'],'response_sha256':ack['response_sha256'],'retrieved_at':ack['retrieved_at'],'recorded_at':ack['recorded_at'],'evidence_available_at':terminal['completed_at'],'supporting_calendar_text':found[0],'source_publication_at':None,'publication_precision':'UNKNOWN','scope':'SCHEDULE_ONLY_NOT_RATE_DECISION_OR_FORECAST','does_not_verify_news_forecast':True}

def handoff(news_projection,official_root):
    packets=[]
    for candidate in news_projection['event_candidates']:
        endpoint='boj_schedule' if 'Bank of Japan' in candidate['title'] else 'bok_schedule' if 'South Korea central bank' in candidate['title'] else None
        try:context=official_context(official_root,endpoint,news_projection['as_of']) if endpoint else {'status':'UNAVAILABLE','request_status':'NO_SCOPED_OFFICIAL_SOURCE'}
        except FileNotFoundError:context={'status':'OFFICIAL_VERIFICATION_PENDING','request_status':'NOT_RETRIEVED'}
        packets.append({'event_candidate_id':candidate['event_candidate_id'],'news_article_id':candidate['article_id'],'news_claim':candidate['title'],'news_url':candidate['url'],'news_source_published_at':candidate['source_published_at'],'news_retrieved_at':candidate['first_observed_at'],'news_recorded_at':candidate['first_recorded_at'],'public_export_allowed':candidate['public_export_allowed'],'claim_type':candidate['claim_type'],'reported_rate_or_forecast_status':'OFFICIAL_VERIFICATION_PENDING','official_context':context,'macroview':{'status':'RESEARCH_PREVIEW_ONLY','as_of':news_projection['as_of'],'known':'Attributed news report and any separately scoped calendar evidence.','unknown':'Future policy decision and forecasts remain unverified; market causality and detection latency unknown.','conditional_hypothesis':'If policy expectations change, rate differentials and funding conditions may change. This does not predict market direction.','next_evidence':'Official policy statement and dated outlook after the meeting.','polymarket':'UNAVAILABLE','trade_ready':False}})
    return packets

def main():
    # JSON wire output stays portable under native Windows code pages, including emoji.
    emit=lambda value:print(json.dumps(value,ensure_ascii=True,sort_keys=True))
    p=argparse.ArgumentParser();p.add_argument('--root',required=True);p.add_argument('--endpoint',choices=ENDPOINTS);p.add_argument('--request-id');p.add_argument('--enable-network',action='store_true');p.add_argument('--project',action='store_true');p.add_argument('--as-of');p.add_argument('--plan');p.add_argument('--cycle');a=p.parse_args()
    if a.project:emit(project(a.root,a.as_of));return
    if not a.enable_network:emit({'mode':'OFFLINE','network_requests':0});return
    if a.plan or a.cycle:
        if not a.plan or not a.cycle or not re.fullmatch(r'cycle_[0-9]{3}',a.cycle):raise ValueError('EXPLICIT_PLAN_AND_CYCLE_REQUIRED')
        plan=m.read(Path(a.plan));root=access.pin(a.root,plan,CONTRACT)
        (root/'CYCLE_LOCK').mkdir(exist_ok=True)
        with m.owner_lock(root/'CYCLE_LOCK'):
            emit([acquire(root,ep,a.cycle+'_'+ep,True) for source in plan['sources'] for ep in CONTRACT.sources[source]])
        return
    if not a.endpoint or not a.request_id:raise ValueError('EXPLICIT_ENDPOINT_AND_REQUEST_REQUIRED')
    emit(acquire(a.root,a.endpoint,a.request_id,True))

if __name__=='__main__':main()
