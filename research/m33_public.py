"""Offline-first M3.3 rights gate. Metadata context only; never production capture."""
import argparse,json,re
from datetime import datetime,timezone
from html import unescape
from pathlib import Path
from research import m3_discovery as m,m31_access as a

QUALITY={
 'voa_economy':dict(id='voa_economy',name='Voice of America Economy',url='https://www.voanews.com/api/zyboql-vomx-tpetvmi',article_hosts=['voanews.com'],terms_status='ITEM_LEVEL_RIGHTS_REQUIRED'),
 'globalvoices':dict(id='globalvoices',name='Global Voices',url='https://globalvoices.org/feed/',article_hosts=['globalvoices.org'],terms_status='CC_BY_3_0_AUTHOR_ATTRIBUTION_REQUIRED'),
 '360info':dict(id='360info',name='360info',url='https://360info.org/feed/',article_hosts=['360info.org'],terms_status='CC_BY_4_0_AUTHOR_ATTRIBUTION_REQUIRED'),
 'fed_monetary':dict(id='fed_monetary',name='Federal Reserve Board',url='https://www.federalreserve.gov/feeds/press_monetary.xml',article_hosts=['federalreserve.gov'],terms_status='US_GOVERNMENT_ORIGINAL_ONLY'),
 'bea_releases':dict(id='bea_releases',name='U.S. Bureau of Economic Analysis',url='https://apps.bea.gov/rss/rss.xml',article_hosts=['bea.gov'],terms_status='US_GOVERNMENT_ORIGINAL_ONLY')}
DOCS={'voa_directory':'https://www.voanews.com/rssfeeds','voa_terms':'https://www.voanews.com/p/5338.html','gv_terms':'https://globalvoices.org/about/','360_terms':'https://360info.org/how-to-use-our-content/','ecb_terms':'https://www.ecb.europa.eu/services/disclaimer/html/index.en.html','fed_terms':'https://www.federalreserve.gov/disclaimer.htm','bea_terms':'https://www.bea.gov/help/faq/147','bea_calendar':'https://www.bea.gov/news/schedule'}
ITEMS={'360_energy_capture':'https://360info.org/how-the-fossil-fuel-industry-captured-australia-and-maintains-its-political-dominance/','360_energy_lobby':'https://360info.org/how-fossil-fuel-lobby-is-undermining-democracy/','fed_discount_minutes':'https://www.federalreserve.gov/newsevents/pressreleases/monetary20261013a.htm'}
DOC_CONTRACT=a.AccessContract('M33_RIGHTS_QUALIFICATION_V1','M33','M33_IDENTITY.json','M33_PRIVATE_QUALIFICATION_NOT_PUBLIC_PROJECTION',100,20_000_000,8,DOCS,{k:(k,) for k in DOCS},{k:k for k in DOCS})
DATA_CONTRACT=a.AccessContract('M33_SOURCE_QUALITY_V1','M33','M33_IDENTITY.json','M33_SOURCE_QUALITY_NOT_PUBLIC_APPROVAL',90,16_000_000,5,{k:v['url'] for k,v in QUALITY.items()},{k:(k,) for k in QUALITY},{k:k for k in QUALITY})
ITEM_CONTRACT=a.AccessContract('M33_ITEM_RIGHTS_V1','M33','M33_IDENTITY.json','M33_LOCAL_ITEM_RIGHTS_REVIEW',6,8_000_000,3,ITEMS,{k:(k,) for k in ITEMS},{k:k for k in ITEMS})
PUBLIC_SOURCES=frozenset({'360info','fed_monetary'})
VERSION='M33_PUBLIC_CONTEXT_V1'

def utc(v):
    d=datetime.fromisoformat(v.replace('Z','+00:00'))
    if d.tzinfo is None:raise ValueError('TIMEZONE_REQUIRED')
    return d.astimezone(timezone.utc)

def plain(html):return ' '.join(unescape(re.sub('<[^>]+>',' ',html)).split())
def fingerprint(row):return m.sha(m.canonical(row).encode())
def parse(endpoint,body):
    rows,summary=m.parse_metadata(body,QUALITY[endpoint]);return {'records':rows,'summary':summary}

def bundle(root,contract,request,parser=None):
    """Read-only reserve/ACK/body/checkpoint binding; incomplete evidence fails closed."""
    root=a.validate_root(root,contract)
    if not re.fullmatch('[A-Za-z0-9_-]{1,80}',request):raise ValueError('REQUEST_ID')
    stem=root/'HTTP'/request;r=m.read(Path(str(stem)+'.reserve.json'));ack=m.read(Path(str(stem)+'.ack.json'));t=m.read(Path(str(stem)+'.terminal.json'))
    ep=r['endpoint_id'];expected=contract.endpoints[ep]
    if any(x['request_id']!=request or x['endpoint_id']!=ep for x in (r,ack,t)) or r['url']!=expected or ack['url']!=expected or r['experiment_version']!=contract.version or ack['scope']!=contract.scope:raise ValueError('RECEIPT_IDENTITY')
    if t['status']!='SUCCESS' or t['http_status']!=200 or ack['http']['http_status']!=200:raise ValueError('NO_SUCCESSFUL_EVIDENCE')
    body=Path(str(stem)+'.body').read_bytes()
    if len(body)!=ack['response_bytes'] or m.sha(body)!=ack['response_sha256']:raise ValueError('BODY_INTEGRITY')
    clocks=[r['reserved_at'],ack['started_at'],ack['retrieved_at'],ack['recorded_at']]
    result=None
    if parser:
        p=m.read(Path(str(stem)+'.parsed.json'))
        if p['request_id']!=request or p['endpoint_id']!=ep or p['retrieved_at']!=ack['retrieved_at'] or p['http_ack_recorded_at']!=ack['recorded_at'] or p['response_sha256']!=ack['response_sha256']:raise ValueError('PARSED_BINDING')
        result=parser(ep,body)
        if result!=p['result']:raise ValueError('PARSED_CONTENT')
        clocks.append(p['recorded_at'])
    clocks.append(t['completed_at'])
    if list(map(utc,clocks))!=sorted(map(utc,clocks)):raise ValueError('CLOCK_ORDER')
    return {'endpoint':ep,'ack':ack,'body':body,'available_at':t['completed_at'],'result':result}

def acquire(study,endpoint,cycle,enable_network=False,fetcher=m.bounded_get):
    if not enable_network:raise ValueError('NETWORK_DISABLED')
    study=m.safe_root(study);m.assert_external_root(study)
    if endpoint not in PUBLIC_SOURCES or not re.fullmatch('cycle_[0-9]{3}',cycle):raise ValueError('SELECTED_SOURCE_ONLY')
    lock=study/'NETWORK_LOCK';lock.mkdir(exist_ok=True)
    with m.owner_lock(lock):
        count=size=0
        for name in ('QUALIFICATION','DATA','ITEMS'):
            c,b=a.accounting(m.safe_root(study/name));count+=c;size+=b
        request=cycle+'_'+endpoint;root=study/'DATA'
        if (root/'HTTP'/(request+'.reserve.json')).exists():
            a.validate_root(root,DATA_CONTRACT)
            if (root/'PLAN.json').exists():a.frozen(root,DATA_CONTRACT)
            r=m.read(root/'HTTP'/(request+'.reserve.json'))
            if r['endpoint_id']!=endpoint or r['url']!=QUALITY[endpoint]['url']:raise ValueError('RESUME_IDENTITY')
            terminal=root/'HTTP'/(request+'.terminal.json')
            return {'status':'ALREADY_RESERVED_NO_RETRY','request_id':request,'original_status':m.read(terminal)['status'] if terminal.exists() else 'UNKNOWN'}
        if count>=100 or size+m.MAX_BODY>20_000_000:raise ValueError('STUDY_BUDGET')
        return a.acquire(root,endpoint,request,True,fetcher,parse,DATA_CONTRACT)

def item_rights(row,policy,item):
    """Positive publisher evidence scoped to original title/byline only, not images/body."""
    ep=row['source_id'];html=item['body'].decode('utf-8');text=plain(html)
    if item['ack']['url']!=row['url']:raise ValueError('ITEM_URL_MISMATCH')
    if ep=='360info':
        headings=re.findall(r'<h1\b[^>]*>(.*?)</h1>',html,re.S)
        published=re.findall(r'"datePublished"\s*:\s*"([^"]+)"',html)
        if len(headings)!=1 or plain(headings[0])!=row['title'] or len(published)!=1 or utc(published[0])!=utc(row['source_published_at']):raise ValueError('ITEM_TITLE_OR_PUBLICATION_MISMATCH')
        author_block=re.search(r'<div\b[^>]*class="post-meta-authors"[^>]*>(.*?)</div>',html,re.S)
        body_block=re.search(r'<div\b[^>]*class="copy main-copy"[^>]*>(.*?)</div>',html,re.S)
        if not author_block or not body_block:raise ValueError('ITEM_AUTHOR_OR_LICENSE_REGION')
        names=re.sub(r'^Authors\s*','',plain(author_block[1]));expected=plain(row.get('author') or '')
        if not expected or names!=expected:raise ValueError('AUTHOR_MISMATCH')
        if 'https://creativecommons.org/licenses/by/4.0/' not in body_block[1] or not re.search(r'Originally published under\s+Creative Commons\s+by\s+360info',plain(body_block[1]),re.I):raise ValueError('ITEM_LICENSE_MISSING')
        if re.search(r'\b(?:Reuters|Associated Press|Agence France.Presse|All rights reserved)\b',expected+' '+plain(body_block[1]),re.I):raise ValueError('THIRD_PARTY_TEXT')
        if not all(x in plain(policy['body'].decode('utf-8')) for x in ('licence all content created and distributed by 360info','Attribution 4.0')):raise ValueError('POLICY_LICENSE_MISSING')
        license_url='https://creativecommons.org/licenses/by/4.0/'
        return names,license_url,'ANALYSIS_CONTEXT','INDEPENDENT_ANALYSIS_CONTEXT'
    if ep=='fed_monetary':
        policy_text=plain(policy['body'].decode('utf-8'))
        if "Unless otherwise indicated, information on Board's website is in the public domain and may be copied and distributed without permission." not in policy_text:raise ValueError('POLICY_LICENSE_MISSING')
        if 'Board of Governors of the Federal Reserve System' not in text or row['title'] not in text:raise ValueError('ORIGINAL_OFFICIAL_DOCUMENT_MISMATCH')
        return QUALITY[ep]['name'],None,'OFFICIAL_ANNOUNCEMENT','OFFICIAL_ORIGIN_DISCOVERY'
    raise ValueError('NOT_PUBLIC_ELIGIBLE')

def project(study,as_of=None):
    study=m.safe_root(study);m.assert_external_root(study);cut=utc(as_of or m.now())
    manifest=m.read(study/'PUBLIC_ITEM_REVIEW.json');pinned=m.read(study/'PUBLIC_ITEM_REVIEW_SHA256.json')
    if pinned!={'sha256':fingerprint(manifest)} or manifest['version']!=VERSION:raise ValueError('REVIEW_MANIFEST_HASH')
    if set(manifest)!={'version','reviewed_at','items'}:raise ValueError('REVIEW_SCHEMA')
    records={};observations=[];last_checkpoint={}
    root=a.validate_root(study/'DATA',DATA_CONTRACT)
    if (root/'PLAN.json').exists():a.frozen(root,DATA_CONTRACT)
    for p in sorted((root/'HTTP').glob('*.parsed.json')):
        request=p.name.removesuffix('.parsed.json');b=bundle(root,DATA_CONTRACT,request,parse)
        if utc(b['available_at'])>cut:continue
        last_checkpoint[b['endpoint']]=max(last_checkpoint.get(b['endpoint'],''),b['available_at'])
        for row in b['result']['records']:
            if row['source_id'] not in PUBLIC_SOURCES:continue
            observations.append((b['available_at'],request,b['ack']['retrieved_at'],row))
    counts={'NEW_TO_EXPERIMENT':0,'UPDATED':0,'DUPLICATE':0};cycle_counts={}
    for available,request,retrieved,row in sorted(observations,key=lambda x:(utc(x[0]),x[1])):
        aid=m.article_identity(row['url']);prev=records.get(aid);fp=fingerprint(row)
        status='NEW_TO_EXPERIMENT' if prev is None else 'DUPLICATE' if prev['fp']==fp else 'UPDATED'
        counts[status]+=1;cycle_counts.setdefault(request,dict.fromkeys(counts,0))[status]+=1
        records[aid]={'row':row,'fp':fp,'first':retrieved if prev is None else prev['first'],'first_recorded':available if prev is None else prev['first_recorded'],'available':available,'last':retrieved}
    public=[];excluded={}
    for aid,v in records.items():
        row=v['row'];review=manifest['items'].get(aid)
        if not review or review.get('metadata_sha256')!=v['fp']:excluded['UNREVIEWED_OR_UPDATED_ITEM']=excluded.get('UNREVIEWED_OR_UPDATED_ITEM',0)+1;continue
        if set(review)!={'metadata_sha256','item_endpoint','item_body_sha256','policy_endpoint','policy_body_sha256','kind','previous_experiment_presence'}:raise ValueError('ITEM_REVIEW_SCHEMA')
        if review['previous_experiment_presence'] not in ('ALREADY_PRESENT_IN_M32_RAW_FEED','KNOWN_FROM_M3'):raise ValueError('PRIOR_EXPERIMENT_SCOPE')
        item=bundle(study/'ITEMS',ITEM_CONTRACT,'item_'+review['item_endpoint'])
        policy=bundle(study/'QUALIFICATION',DOC_CONTRACT,'rights_'+review['policy_endpoint'])
        expected_policy='360_terms' if row['source_id']=='360info' else 'fed_terms'
        if review['policy_endpoint']!=expected_policy or item['ack']['response_sha256']!=review['item_body_sha256'] or policy['ack']['response_sha256']!=review['policy_body_sha256']:raise ValueError('RIGHTS_PROOF_BINDING')
        author,license_url,kind,origin=item_rights(row,policy,item)
        if kind!=review['kind']:raise ValueError('CONTENT_TYPE_BINDING')
        gate_at=max(map(utc,[manifest['reviewed_at'],item['available_at'],policy['available_at'],v['available']]))
        if gate_at>cut:excluded['RIGHTS_EVIDENCE_LATER_THAN_AS_OF']=excluded.get('RIGHTS_EVIDENCE_LATER_THAN_AS_OF',0)+1;continue
        pub=row['source_published_at'];precision=row['publication_precision'];age=(cut-utc(pub)).total_seconds()/3600 if pub and precision=='EXACT_SOURCE_REPORTED' else None
        if age is not None and age<0:continue
        if precision=='DATE_ONLY' and pub>cut.date().isoformat():continue
        result={'article_identity':aid,'event_candidate_identity':'M33-ARTICLE-CONTEXT-'+aid,'headline_original':row['title'],'original_url':row['url'],'publisher':row['source_name'],'author_attribution':author,'source_id':row['source_id'],'source_reported_published_at':pub,'publication_precision':precision,'first_observed_in_M33':v['first'],'first_recorded_at':v['first_recorded'],'last_observed_at':v['last'],'public_eligibility_available_at':gate_at.isoformat(),'content_fingerprint':v['fp'],'kind':kind,'discovery_origin':origin,'macro_category':'ENERGY_POLICY_CONTEXT' if kind=='ANALYSIS_CONTEXT' else 'MONETARY_POLICY_MINUTES_CONTEXT','age_hours':age,'previous_experiment_presence':review['previous_experiment_presence'],'not_a_new_policy_decision':True,'distinct_world_event_proven':False,'official_status':'OFFICIAL_PROPOSITION_VERIFICATION_PENDING','macroview_status':'RESEARCH_PREVIEW_ONLY','polymarket':'UNAVAILABLE','trade_ready':False,'rights':{'classification':'PUBLIC_COMMERCIAL_ELIGIBLE','scope':'EXACT_ORIGINAL_HEADLINE_BYLINE_TIME_LINK_ONLY','license_url':license_url,'terms_url':policy['ack']['url'],'terms_body_sha256':policy['ack']['response_sha256'],'item_body_sha256':item['ack']['response_sha256'],'review_manifest_sha256':pinned['sha256'],'changes':'No headline translation or rewriting. Formatting/metadata selection only; separate classification is our research annotation.','images_and_body_included':False,'periodic_access_permission':'NOT_EXPRESSLY_STATED_PRODUCTION_NOT_AUTHORIZED'}}
        public.append(result)
    audit={'public_records':len(public),'independent_news_48h':0,'independent_news_7d':0,'analysis_48h':sum(x['kind']=='ANALYSIS_CONTEXT' and x['age_hours'] is not None and 0<=x['age_hours']<=48 for x in public),'analysis_7d':sum(x['kind']=='ANALYSIS_CONTEXT' and x['age_hours'] is not None and 0<=x['age_hours']<=168 for x in public),'official_48h':sum(x['kind']=='OFFICIAL_ANNOUNCEMENT' and x['age_hours'] is not None and 0<=x['age_hours']<=48 for x in public),'official_7d':sum(x['kind']=='OFFICIAL_ANNOUNCEMENT' and x['age_hours'] is not None and 0<=x['age_hours']<=168 for x in public),'excluded_by_reason':excluded,'observations':counts,'per_request_counts':cycle_counts}
    return {'version':VERSION,'as_of':cut.isoformat(),'status':'PARTIAL_NO_RECENT_INDEPENDENT_NEWS','capture':'OFF','first_seen_scope':'M33_ONLY_NOT_GLOBAL_FIRST_SEEN','breaking_detection_proven':False,'audit':audit,'records':public}

def public_projection(study,as_of=None):
    p=project(study,as_of)
    # Fixed product fields only. No local request IDs, raw receipts, bodies or paths.
    audit_keys=('public_records','independent_news_48h','independent_news_7d','analysis_48h','analysis_7d','official_48h','official_7d')
    return {k:p[k] for k in ('version','as_of','status','capture','first_seen_scope','breaking_detection_proven')}|{'audit':{k:p['audit'][k] for k in audit_keys},'records':p['records']}

def handoff(study,as_of=None):
    p=public_projection(study,as_of);packets=[]
    for row in p['records']:
        verified=None
        if row['source_id']=='fed_monetary':
            item=bundle(Path(study)/'ITEMS',ITEM_CONTRACT,'item_fed_discount_minutes')
            text=plain(item['body'].decode('utf-8'))
            if all(phrase in text for phrase in ('released the minutes','August 17, September 9, and September 16, 2026','discount rate is distinct from')):
                verified={'status':'VERIFIED_SCOPED_OFFICIAL_FACT','proposition':'The Board published minutes covering its discount-rate meetings on August 17, September 9 and September 16, 2026.','source_url':row['original_url'],'body_sha256':item['ack']['response_sha256'],'retrieved_at':item['ack']['retrieved_at'],'recorded_at':item['ack']['recorded_at'],'scope':'PUBLICATION_AND_MEETING_COVERAGE_ONLY_NOT_FOMC_RATE_DECISION','not_a_new_m33_discovery':True}
        packets.append({'article_identity':row['article_identity'],'kind':row['kind'],'original_url':row['original_url'],'headline_original':row['headline_original'],'publisher':row['publisher'],'author_attribution':row['author_attribution'],'rights':row['rights'],'as_of':p['as_of'],'first_observed_in_M33':row['first_observed_in_M33'],'source_reported_published_at':row['source_reported_published_at'],'main_claim_status':'ANALYSIS_NOT_OFFICIALLY_VERIFIED' if row['kind']=='ANALYSIS_CONTEXT' else 'SCOPED_PUBLICATION_FACT_ONLY','official_proposition':verified,'official_verification_pending':row['kind']=='ANALYSIS_CONTEXT' or verified is None,'macroview':{'status':'RESEARCH_PREVIEW_ONLY','not_frozen':True,'uncertainty':'Analysis is not a new policy or supply decision; missing official propositions stay pending.','next_evidence':'Original official energy-policy decisions or relevant dated statistical releases.','polymarket':'UNAVAILABLE','trade_ready':False}})
    return {'status':'PARTIAL_NO_RECENT_NEWS_REPORT_HANDOFF','evaluation_as_of':p['as_of'],'packets':packets}

def main():
    p=argparse.ArgumentParser();p.add_argument('--study',required=True);p.add_argument('--project',action='store_true');p.add_argument('--public',action='store_true');p.add_argument('--as-of');p.add_argument('--plan');p.add_argument('--cycle');p.add_argument('--enable-network',action='store_true');args=p.parse_args();emit=lambda value:print(json.dumps(value,ensure_ascii=True,sort_keys=True))
    if args.public:emit(public_projection(args.study,args.as_of));return
    if args.project:emit(project(args.study,args.as_of));return
    if not args.enable_network:emit({'mode':'OFFLINE','network_requests':0});return
    if not args.plan or not args.cycle or not re.fullmatch('cycle_[0-9]{3}',args.cycle):raise ValueError('EXPLICIT_PLAN_AND_CYCLE')
    plan=m.read(Path(args.plan))
    if set(plan['sources'])!=PUBLIC_SOURCES:raise ValueError('EXACT_SELECTED_SOURCE_SET')
    root=a.pin(Path(args.study)/'DATA',plan,DATA_CONTRACT);(root/'CYCLE_LOCK').mkdir(exist_ok=True)
    with m.owner_lock(root/'CYCLE_LOCK'):results=[acquire(args.study,ep,args.cycle,True) for ep in plan['sources']]
    emit(results)
    if any(x['status']!='SUCCESS' and not (x['status']=='ALREADY_RESERVED_NO_RETRY' and x.get('original_status')=='SUCCESS') for x in results):raise SystemExit(2)

if __name__=='__main__':main()
