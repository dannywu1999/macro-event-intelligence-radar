"""M3.1 bounded access receipts; reuse M3 transport/locking, never its frozen plan."""
from pathlib import Path
import argparse,json,os,re
from datetime import datetime,timezone
from research import m3_discovery as m

VERSION='M3.1_SOURCE_RECOVERY_V1'
MAX_REQUESTS=80
MAX_BYTES=20_000_000
ENDPOINTS={
 'bls_cpi':'https://api.bls.gov/publicAPI/v1/timeseries/data/CUUR0000SA0',
 'bls_payroll':'https://api.bls.gov/publicAPI/v1/timeseries/data/CES0000000001',
 'bea_rss':'https://apps.bea.gov/rss/rss.xml',
 'bea_releases':'https://www.bea.gov/news/current-releases',
 'dol_claims':'https://www.dol.gov/ui/data.pdf',
 'bea_developers_doc':'https://www.bea.gov/resources/for-developers',
 'census_rss_doc':'https://www.census.gov/about/contact-us/feeds.html',
 'dol_rights_doc':'https://www.dol.gov/general/aboutdol/copyright',
}
SOURCES={'bls_api':('bls_cpi','bls_payroll'),'bea_releases':('bea_releases',)}
def family(endpoint):return 'bls_api' if endpoint in SOURCES['bls_api'] else 'bea' if endpoint in ('bea_rss','bea_releases','bea_developers_doc') else endpoint

def validate_plan(plan):
    if set(plan)!={'version','experiment_id','interval_seconds','max_requests','max_bytes','sources'}:raise ValueError('PLAN_SCHEMA')
    if plan['version']!=VERSION or not re.fullmatch(r'M31-[A-Za-z0-9_-]{1,60}',plan['experiment_id']):raise ValueError('PLAN_VERSION')
    if any(type(plan[x]) is not int for x in ('interval_seconds','max_requests','max_bytes')):raise ValueError('PLAN_TYPE')
    if plan['interval_seconds']<1800 or not 1<=plan['max_requests']<=80 or not 1<=plan['max_bytes']<=MAX_BYTES:raise ValueError('PLAN_LIMIT')
    if not isinstance(plan['sources'],list) or not 1<=len(plan['sources'])<=2 or len(set(plan['sources']))!=len(plan['sources']):raise ValueError('SOURCE_LIMIT')
    if not all(x in SOURCES for x in plan['sources']):raise ValueError('UNKNOWN_SOURCE')
    return plan

def setup(root):
    root=m.safe_root(root);m.assert_external_root(root)
    root.mkdir(parents=True,exist_ok=True)
    marker=root/'M31_IDENTITY.json'
    identity={'version':VERSION,'scope':'M31_ONLY_NOT_GLOBAL_FIRST_SEEN','max_requests':MAX_REQUESTS,'max_bytes':MAX_BYTES}
    if marker.exists():
        if m.read(marker)!=identity:raise ValueError('ROOT_IDENTITY_MISMATCH')
    else:
        if any(root.iterdir()):raise ValueError('NONEMPTY_UNKNOWN_ROOT')
        m.save(marker,identity)
    return root

def pin(root,plan):
    root=setup(root);plan=validate_plan(plan)
    with m.owner_lock(root):
        path=root/'PLAN.json'
        if path.exists():
            if m.read(path)!=plan:raise ValueError('FROZEN_PLAN_MISMATCH')
        else:m.save(path,plan)
        path=root/'PLAN_SHA256.json';obj={'sha256':m.sha(m.canonical(plan).encode())}
        if path.exists():
            if m.read(path)!=obj:raise ValueError('PLAN_HASH_MISMATCH')
        else:m.save(path,obj)
    return root

def frozen(root):
    plan=validate_plan(m.read(root/'PLAN.json'))
    if m.read(root/'PLAN_SHA256.json')!={'sha256':m.sha(m.canonical(plan).encode())}:raise ValueError('PLAN_HASH_MISMATCH')
    return plan

def check_interval(root,plan,cycle):
    selected={ep for s in plan['sources'] for ep in SOURCES[s]}
    earlier=[m.read(p) for p in paths(root) if m.read(p)['endpoint_id'] in selected and not m.read(p)['request_id'].startswith(cycle+'_')]
    if earlier:
        last=max(datetime.fromisoformat(x['reserved_at'].replace('Z','+00:00')) for x in earlier)
        if (datetime.now(timezone.utc)-last).total_seconds()<plan['interval_seconds']:raise ValueError('MINIMUM_INTERVAL')

def paths(root):return sorted((root/'HTTP').glob('*.reserve.json'))

def accounting(root):
    rr=paths(root);size=0
    for p in rr:
        ack=p.with_name(p.name.replace('.reserve.json','.ack.json'))
        size+=m.read(ack)['response_bytes'] if ack.exists() else m.MAX_BODY
    return len(rr),size

def acquire(root,endpoint,request_id,enable_network=False,fetcher=m.bounded_get,parser=None):
    if not enable_network:raise ValueError('NETWORK_DISABLED')
    root=setup(root)
    if endpoint not in ENDPOINTS or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',request_id):raise ValueError('REQUEST_IDENTITY')
    with m.owner_lock(root):
        stem=root/'HTTP'/request_id;reserve=Path(str(stem)+'.reserve.json');term=Path(str(stem)+'.terminal.json')
        if reserve.exists():return {'status':'ALREADY_RESERVED_NO_RETRY','request_id':request_id}
        if (root/'PLAN.json').exists():
            pinned=frozen(root);selected={ep for s in pinned['sources'] for ep in SOURCES[s]}
            match=re.fullmatch(r'(cycle_[0-9]{3})_'+re.escape(endpoint),request_id)
            if endpoint not in selected or not match:raise ValueError('NO_NEW_PROBES_AFTER_SELECTION')
            check_interval(root,pinned,match[1])
        for p in paths(root):
            r=m.read(p)
            if family(r['endpoint_id'])!=family(endpoint):continue
            t=p.with_name(p.name.replace('.reserve.json','.terminal.json'))
            if not t.exists() or m.read(t)['status'] in ('UNKNOWN','SOURCE_DENIED','RATE_LIMITED','REDIRECT_REFUSED'):
                return {'status':'SOURCE_PAUSED_NO_RETRY','request_id':request_id}
        spent,nbytes=accounting(root)
        if family(endpoint)=='bls_api' and sum(family(m.read(p)['endpoint_id'])=='bls_api' and m.read(p)['reserved_at'][:10]==m.now()[:10] for p in paths(root))>=25:raise ValueError('BLS_DAILY_EXPERIMENT_QUOTA')
        limits=frozen(root) if (root/'PLAN.json').exists() else {'max_requests':MAX_REQUESTS,'max_bytes':MAX_BYTES}
        if spent>=limits['max_requests'] or nbytes+m.MAX_BODY>limits['max_bytes']:raise ValueError('BUDGET_EXHAUSTED')
        m.save(reserve,{'request_id':request_id,'endpoint_id':endpoint,'url':ENDPOINTS[endpoint],'reserved_at':m.now(),'request_count':1,'reserved_bytes':m.MAX_BODY,'experiment_version':VERSION})
        started=m.now();ack_saved=False;stage='NETWORK';meta={};state='UNKNOWN';error=None;parsed=None
        try:
            meta,body=fetcher(ENDPOINTS[endpoint]);retrieved=m.now()
            if not isinstance(body,bytes) or len(body)>m.MAX_BODY:raise ValueError('BODY_LIMIT')
            http=meta['http_status']
            if http==200:
                with Path(str(stem)+'.body').open('xb') as out:out.write(body);out.flush();os.fsync(out.fileno())
            stage='ACK'
            ack={'request_id':request_id,'endpoint_id':endpoint,'url':ENDPOINTS[endpoint],'started_at':started,'retrieved_at':retrieved,'recorded_at':m.now(),'http':meta,'response_bytes':len(body),'response_sha256':m.sha(body) if meta.get('response_body_status')!='UNREAD_HTTP_ERROR_BODY' else None,'scope':'M31_ISOLATED_RESEARCH'}
            m.save(Path(str(stem)+'.ack.json'),ack);ack_saved=True
            state='SOURCE_DENIED' if http in (401,403,406) else 'RATE_LIMITED' if http in (429,503) else 'REDIRECT_REFUSED' if 300<=http<400 else 'HTTP_ERROR' if http!=200 else 'SUCCESS'
            if http==200 and parser:
                stage='PARSE';parsed=parser(endpoint,body)
                stage='PARSED_WRITE';m.save(Path(str(stem)+'.parsed.json'),{'request_id':request_id,'endpoint_id':endpoint,'retrieved_at':retrieved,'http_ack_recorded_at':ack['recorded_at'],'recorded_at':m.now(),'response_sha256':m.sha(body),'result':parsed})
        except Exception as e:
            state='PARSE_FAILED' if ack_saved and stage=='PARSE' else 'LOCAL_WRITE_FAILED' if ack_saved else 'UNKNOWN'
            error=type(e).__name__ # no raw exception or credentials
        result={'request_id':request_id,'endpoint_id':endpoint,'status':state,'http_status':meta.get('http_status'),'error_type':error,'completed_at':m.now()}
        m.save(term,result)
        return result

def run(root,plan,cycle,enable_network=False,parser=None,fetcher=m.bounded_get):
    if not enable_network:raise ValueError('NETWORK_DISABLED')
    root=pin(root,plan)
    if not re.fullmatch(r'cycle_[0-9]{3}',cycle):raise ValueError('CYCLE_ID')
    # Entire cycle under a distinct OS lock; per-request lock protects shared probe budget.
    (root/'CYCLE_LOCK').mkdir(exist_ok=True)
    with m.owner_lock(root/'CYCLE_LOCK'):
        # Successful selection probes are observations too: do not immediately repoll them.
        check_interval(root,plan,cycle)
        return [acquire(root,ep,cycle+'_'+ep,True,fetcher,parser) for s in plan['sources'] for ep in SOURCES[s]]

def main():
    p=argparse.ArgumentParser();p.add_argument('--root',required=True);p.add_argument('--probe',choices=ENDPOINTS);p.add_argument('--request-id');p.add_argument('--enable-network',action='store_true');a=p.parse_args()
    if not a.enable_network:
        print(json.dumps({'mode':'OFFLINE','network_requests':0,'existing_root':Path(a.root).exists()}));return
    if not a.probe or not a.request_id:raise ValueError('EXPLICIT_PROBE_REQUIRED')
    print(json.dumps(acquire(a.root,a.probe,a.request_id,True)))
if __name__=='__main__':main()
