"""Offline-first M3 public news discovery harness. Network is explicit opt-in."""
from __future__ import annotations
import argparse, contextlib, hashlib, json, os, re, socket, time, urllib.error, urllib.request
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from html import unescape
from pathlib import Path
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET

# Pure identity/time helpers are reused from the existing research contract.
from tools.stage1b_historical_campaign.radar_news_prospective import article_identity, content_identity, normalized_url, source_time, owner_lock
from tools.stage1b_historical_campaign.global_event_radar_read_adapter import build_canonical_events
from tools.stage1b_historical_campaign.broad_news_ingestion import macro_relevant_title

MAX_BODY=2*1024*1024
REGISTRY={
 'ecb':'https://www.ecb.europa.eu/rss/press.html','globalvoices':'https://globalvoices.org/feed/',
 'fed_monetary':'https://www.federalreserve.gov/feeds/press_monetary.xml','bls_cpi':'https://www.bls.gov/feed/cpi.rss',
 'bls_employment':'https://www.bls.gov/feed/empsit.rss','360info':'https://360info.org/feed/' }
def canonical(x): return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def sha(data): return hashlib.sha256(data).hexdigest()
def now(): return datetime.now(timezone.utc).isoformat(timespec='microseconds').replace('+00:00','Z')
def save(path,obj):
    b=(canonical(obj)+'\n').encode(); path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('xb') as f: f.write(b); f.flush(); os.fsync(f.fileno())
def read(path): return json.loads(path.read_text(encoding='utf-8'))
def safe_root(value):
    raw=Path(value).expanduser().absolute()
    for part in (raw,*raw.parents):
        if part.exists():
            st=part.stat(follow_symlinks=False)
            if part.is_symlink() or (getattr(st,'st_file_attributes',0)&getattr(__import__('stat'),'FILE_ATTRIBUTE_REPARSE_POINT',0)):
                raise ValueError('EVIDENCE_ROOT_REPARSE_POINT')
    return raw.resolve()
def assert_external_root(root):
    repo=Path(__file__).resolve().parents[1]
    if root==repo or root in repo.parents or repo in root.parents:raise ValueError('EVIDENCE_ROOT_MUST_BE_OUTSIDE_REPOSITORY')
def pinned_plan(root):
    plan=validate_plan(read(Path(root)/'plan.json'))
    digest=read(Path(root)/'plan.sha256').get('sha256')
    if digest!=sha(canonical(plan).encode()):raise ValueError('PLAN_FINGERPRINT_MISMATCH')
    return plan

def validate_plan(p):
    if not isinstance(p,dict) or set(p)!={'experiment_id','interval_seconds','max_requests','max_total_bytes','sources'}: raise ValueError('PLAN_SCHEMA')
    if not isinstance(p['experiment_id'],str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',p['experiment_id']): raise ValueError('EXPERIMENT_ID')
    if any(type(p[k]) is not int for k in ('interval_seconds','max_requests','max_total_bytes')): raise ValueError('PLAN_BOUNDS')
    if p['interval_seconds']<1800 or not 1<=p['max_requests']<=200 or not 1<=p['max_total_bytes']<=50_000_000: raise ValueError('PLAN_BOUNDS')
    if not isinstance(p['sources'],list) or len(p['sources'])!=6: raise ValueError('REGISTRY_SIZE')
    ids=set()
    for s in p['sources']:
        if set(s)!={'id','name','url','kind','article_hosts','terms_status'} or s['id'] in ids or s['id'] not in REGISTRY or s['url']!=REGISTRY[s['id']]: raise ValueError('SOURCE_REGISTRY_MISMATCH')
        ids.add(s['id'])
        if not isinstance(s['article_hosts'],list) or not s['article_hosts'] or not all(isinstance(h,str) and h for h in s['article_hosts']): raise ValueError('ARTICLE_HOSTS')
    if ids!=set(REGISTRY): raise ValueError('SOURCE_SET_MISMATCH')
    return p

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*a,**kw): return None
def bounded_get(url):
    req=urllib.request.Request(url,headers={'User-Agent':'M3-News-Discovery-Research/1.0','Accept-Encoding':'identity'})
    started=time.monotonic(); opener=urllib.request.build_opener(NoRedirect())
    try:
        response=opener.open(req,timeout=10)
    except urllib.error.HTTPError as e:
        e.close() # denial body is deliberately not consumed or represented as a body hash
        return {'http_status':e.code,'retry_after':e.headers.get('Retry-After') if e.headers else None,
                'response_body_status':'UNREAD_HTTP_ERROR_BODY'},b''
    meta={'http_status':response.status,'retry_after':response.headers.get('Retry-After'),'content_type':response.headers.get('Content-Type')}
    chunks=[]; size=0; legacy_private_socket_access_would_fail=False
    with response:
        while True:
            if time.monotonic()-started>13: raise TimeoutError('TOTAL_READ_DEADLINE')
            # Diagnostic only: the retired fp.raw._sock expression would fail
            # when fp is None. This reader never dereferences private socket state.
            if getattr(response,'fp',object()) is None:legacy_private_socket_access_would_fail=True
            part=response.read(min(65536,MAX_BODY+1-size)) # portable public API; no fp/_sock inspection
            if not part: break
            chunks.append(part);size+=len(part)
            if size>MAX_BODY: raise ValueError('RESPONSE_SIZE_LIMIT')
    meta['response_body_status']='COMPLETE_READ'
    meta['legacy_private_socket_access_would_fail']=legacy_private_socket_access_would_fail
    return meta,b''.join(chunks)

# Metadata-only feed parser. Date and clean semantics were copied from
# NEWS-COVERAGE-ACCEPTANCE-20261018/http_child.py (pure functions, no runtime path dependency).
def clean(value): return ' '.join(unescape(str(value or '')).split())[:1500]
def date(value):
    value=clean(value)
    if not value:return None,'UNKNOWN'
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}',value):
        try: datetime.strptime(value,'%Y-%m-%d')
        except ValueError:return None,'INVALID'
        return value,'DATE_ONLY'
    try:
        try:d=parsedate_to_datetime(value)
        except (ValueError,TypeError,OverflowError):d=datetime.fromisoformat(value.replace('Z','+00:00'))
        if d.tzinfo is None:return None,'TIMEZONE_UNKNOWN'
        return d.astimezone(timezone.utc).isoformat().replace('+00:00','Z'),'EXACT_SOURCE_REPORTED'
    except (ValueError,TypeError,OverflowError):return None,'INVALID'
def parse_metadata(data,source):
    if b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper(): raise ValueError('UNSAFE_XML_DECLARATION')
    doc=ET.fromstring(data); local=lambda t:t.split('}')[-1]
    items=[n for n in doc.iter() if local(n.tag) in ('item','entry')]
    if len(items)>5000:raise ValueError('ITEM_LIMIT')
    if local(doc.tag) not in ('rss','RDF','feed'):raise ValueError('NOT_FEED_XML')
    out=[]; rejected={}
    def reject(reason):rejected[reason]=rejected.get(reason,0)+1
    for item in items:
        f={}
        for n in item:
            k=local(n.tag)
            if k in ('title','link','id','guid','pubDate','published','updated','date','creator','author'):
                v=clean(n.attrib.get('href') if k=='link' and n.attrib.get('href') else ''.join(n.itertext()))
                if v and (k not in f or k=='link'):f[k]=v
        url=f.get('link') or (f.get('guid') if (f.get('guid') or '').startswith('https://') else None)
        if not f.get('title'):reject('MISSING_TITLE');continue
        if not url:reject('MISSING_URL');continue
        try:
            u=urlsplit(url)
            safe=(u.scheme=='https' and bool(u.hostname) and not u.username and not u.password and u.port in (None,443)
                  and any(u.hostname==h or u.hostname.endswith('.'+h) for h in source['article_hosts']))
        except ValueError:safe=False
        if not safe:reject('UNSAFE_OR_OFF_HOST_URL');continue
        raw=f.get('pubDate') or f.get('published') or f.get('date'); published,precision=date(raw)
        author=f.get('creator') or f.get('author')
        if 'AUTHOR_ATTRIBUTION_REQUIRED' in source['terms_status'] and not author:reject('MISSING_ATTRIBUTION');continue
        out.append({'source_id':source['id'],'source_name':source['name'],'title':f['title'],'url':url,'author':author,'source_published_raw':raw,'source_published_at':published,'publication_precision':precision,'terms_status':source['terms_status']})
    return out,{'raw_article_count':len(items),'retained_article_count':len(out),'rejected_by_reason':rejected,'feed_format':local(doc.tag)}

def research_relevance(row):
    """Discovery-only named-release exception; does not alter production filter."""
    title=row.get('title','')
    if row.get('source_id')=='bls_cpi' and re.search(r'\b(?:CPI|Consumer Price Index)\b',title,re.I):
        return True,'NAMED_BLS_CPI_SOURCE_INFLATION_INDICATOR'
    if row.get('source_id')=='bls_employment' and re.search(r'\b(?:Employment Situation|Employment Summary|Unemployment Rate|Payroll Employment)\b',title,re.I):
        return True,'NAMED_BLS_EMPLOYMENT_SOURCE_LABOR_INDICATOR'
    if row.get('source_id')=='fed_monetary' and re.search(r"^Minutes of (?:the Board['’]s discount rate meetings|the Federal Open Market Committee(?:,|$))",title):
        return True,'NAMED_FED_POLICY_MINUTES_CONTEXT_NOT_NEW_RATE_DECISION'
    return macro_relevant_title(title),'EXISTING_CONSERVATIVE_MACRO_TITLE_RULE' if macro_relevant_title(title) else 'NOT_SELECTED_BY_RESEARCH_RULE'

def project(root):
    root=safe_root(root);assert_external_root(root);plan=pinned_plan(root);acks=[];terminals=[];reservations=[]
    for p in sorted((root/'cycles').glob('*/*.json')):
        v=read(p)
        if p.name.endswith('.parsed.json'):acks.append(v)
        elif p.name.endswith('.terminal.json'):terminals.append(v)
        elif p.name.endswith('.reserve.json'):reservations.append(v)
    seen={}; observations=[]; first={}
    for ack in sorted(acks,key=lambda x:x['retrieved_at']):
        for row in ack.get('articles',[]):
            aid=article_identity(row['url']); cid=content_identity({'title':row['title'],'news_source':{'url':row['url'],'name':row['source_name']},'source_published_at':row['source_published_at'],'source_timestamp_precision':row['publication_precision']})
            prior=seen.get(aid); kind='duplicate' if prior and prior['cid']==cid else 'updated' if prior else 'new'
            if aid not in first:first[aid]=ack['retrieved_at']
            item={**row,'article_identity':aid,'content_identity':cid,'observed_at':first[aid],'first_observed_at':first[aid],
                  'retrieved_at':ack['retrieved_at'],'recorded_at':ack['recorded_at'],'observation_kind':kind,
                  'cycle_id':ack['cycle_id'],'source_url':ack['source_url'],'plan_fingerprint':ack['plan_fingerprint'],
                  'provenance_scope':ack['provenance_scope']}
            relevant,basis=research_relevance(row);item['research_relevant']=relevant;item['research_relevance_basis']=basis
            published,precision=source_time(row.get('source_published_at'))
            item['source_to_observation_seconds']=None
            disputed='www.bls.gov/news.release/archives/cpi_10142026.htm' in row['url'].lower()
            item['source_to_observation_status']='CLOCK_DISPUTED' if disputed else 'UNKNOWN'
            if not disputed and precision in ('SECOND','MINUTE','EXACT_SOURCE_REPORTED') and published:
                pubdt=datetime.fromisoformat(published.replace('Z','+00:00')); obdt=datetime.fromisoformat(ack['retrieved_at'].replace('Z','+00:00'))
                if pubdt<=obdt:
                    item['source_to_observation_seconds']=(obdt-pubdt).total_seconds();item['source_to_observation_status']='SOURCE_REPORTED_INTERVAL_NOT_DETECTION_LATENCY'
                else:item['source_to_observation_status']='FUTURE_OR_CLOCK_DISPUTED'
            seen[aid]={'cid':cid,'row':item};observations.append(item)
    current=[v['row'] for v in seen.values() if v['row'].get('research_relevant',research_relevance(v['row'])[0])]
    candidates=build_canonical_events([{'article_reference':r['url'],'title':r['title'],'reported_at':r['source_published_at'] if r['publication_precision']=='EXACT_SOURCE_REPORTED' else None,'reported_time_kind':'REPORTED_TIME' if r['publication_precision']=='EXACT_SOURCE_REPORTED' else 'SOURCE_DATE_PROXY' if r['publication_precision']=='DATE_ONLY' else 'UNKNOWN','observed_at':r['observed_at'],'news_source':{'name':r['source_name']}} for r in current])
    states={s['id']:'UNKNOWN' for s in plan['sources']}
    for t in sorted(terminals,key=lambda x:x.get('completed_at','')):states[t['source_id']]=t['status']
    return {'observations':observations,'source_states':states,'new_count':sum(x['observation_kind']=='new' for x in observations),'updated_count':sum(x['observation_kind']=='updated' for x in observations),'duplicate_count':sum(x['observation_kind']=='duplicate' for x in observations),'canonical_candidates':candidates,'first_observed_scope':'M3_ONLY','first_observed_at':first}

def _retry_until(value,observed_at):
    if not value:return None
    if 'T' in value:
        try:return datetime.fromisoformat(value.replace('Z','+00:00')).astimezone(timezone.utc).isoformat().replace('+00:00','Z')
        except (ValueError,AttributeError):pass
    try:
        seconds=int(value)
        if seconds<0:return None
        return (datetime.fromisoformat(observed_at.replace('Z','+00:00'))+timedelta(seconds=seconds)).isoformat().replace('+00:00','Z')
    except (ValueError,TypeError,OverflowError):
        try:return parsedate_to_datetime(value).astimezone(timezone.utc).isoformat().replace('+00:00','Z')
        except (ValueError,TypeError,OverflowError):return None

def _failure_class(error):
    if isinstance(error,(TimeoutError,socket.timeout)):return 'NETWORK_TIMEOUT'
    if isinstance(error,urllib.error.URLError):return 'NETWORK_DNS_TLS'
    if isinstance(error,ET.ParseError):return 'PARSER_DEFECT'
    if isinstance(error,OSError):return 'NETWORK_DNS_TLS'
    if isinstance(error,ValueError):return 'PARSER_DEFECT'
    return 'LOCAL_READ_DEFECT'

def run(root,plan,cycle,enable_network=False,fetcher=bounded_get):
    root=safe_root(root);assert_external_root(root);plan=validate_plan(plan)
    if not isinstance(cycle,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',cycle):raise ValueError('UNSAFE_CYCLE_ID')
    if not enable_network: raise ValueError('NETWORK_DISABLED')
    pinned=pinned_plan(root)
    if canonical(pinned)!=canonical(plan):raise ValueError('PLAN_FINGERPRINT_MISMATCH')
    cdir=root/'cycles'/cycle; cdir.mkdir(parents=True,exist_ok=True)
    with owner_lock(root):
        reservations=list(root.glob('cycles/*/*.reserve.json'))
        accounting_reservations=reservations+sorted(root.glob('auxiliary/*.reserve.json'))
        acks=list(root.glob('cycles/*/*.ack.json'))
        uncertain=set()
        for reservation in reservations:
            terminal=reservation.with_name(reservation.name.replace('.reserve.json','.terminal.json'))
            ack=reservation.with_name(reservation.name.replace('.reserve.json','.ack.json'))
            if not ack.exists() or not terminal.exists() or read(terminal).get('status')=='UNKNOWN':uncertain.add(read(reservation)['source_id'])
        spent=sum(read(x).get('request_count',0) for x in accounting_reservations)
        nbytes=0
        for reserve in accounting_reservations:
            ack=reserve.with_name(reserve.name.replace('.reserve.json','.ack.json'))
            nbytes+=read(ack).get('response_bytes',0) if ack.exists() else MAX_BODY
        latest_terminals={}
        for tpath in root.glob('cycles/*/*.terminal.json'):
            t=read(tpath); old=latest_terminals.get(t['source_id'])
            if old is None or t.get('completed_at','')>old.get('completed_at',''):latest_terminals[t['source_id']]=t
        other_cycles=[read(x) for x in reservations if Path(x).parent.name!=cycle]
        if other_cycles:
            latest=max(datetime.fromisoformat(v['reserved_at'].replace('Z','+00:00')) for v in other_cycles)
            if (datetime.now(timezone.utc)-latest).total_seconds()<plan['interval_seconds']:raise ValueError('MINIMUM_CYCLE_INTERVAL_NOT_MET')
        for s in plan['sources']:
            prefix=f'{s["id"]}.'
            if s['id'] in uncertain:continue # ambiguous request is never automatically retried
            previous=latest_terminals.get(s['id'],{})
            if previous.get('status') in ('PAUSED_HTTP_403','PAUSED_HTTP_406'):continue
            if previous.get('status') in ('PAUSED_HTTP_429','PAUSED_HTTP_503'):
                until=previous.get('retry_after_until')
                if not until or datetime.now(timezone.utc)<datetime.fromisoformat(until.replace('Z','+00:00')):continue
            if list(cdir.glob(prefix+'*.reserve.json')):continue # interrupted means UNKNOWN; never refetch
            if spent>=plan['max_requests'] or nbytes+MAX_BODY>plan['max_total_bytes']:raise ValueError('BUDGET_EXHAUSTED')
            stem=cdir/(s['id']+'.'+str(len(reservations)))
            fingerprint=sha(canonical(plan).encode())
            save(Path(str(stem)+'.reserve.json'),{'source_id':s['id'],'cycle_id':cycle,'source_url':s['url'],'request_count':1,'reserved_bytes':MAX_BODY,'plan_fingerprint':fingerprint,'provenance_scope':'M3_ISOLATED_RESEARCH','reserved_at':now()});spent+=1;nbytes+=MAX_BODY
            ackpath=Path(str(stem)+'.ack.json');term=Path(str(stem)+'.terminal.json')
            ack_saved=False; stage='NETWORK'; request_started=now(); status='UNKNOWN'; failure_class=None; error_type=None; meta={}; body=b''
            try:
                meta,body=fetcher(s['url'])
                if nbytes-MAX_BODY+len(body)>plan['max_total_bytes']: raise ValueError('TOTAL_BYTE_BUDGET_EXCEEDED')
                retrieved_at=now()
                body_status=meta.get('response_body_status','COMPLETE_READ')
                ack={'source_id':s['id'],'cycle_id':cycle,'source_url':s['url'],'plan_fingerprint':fingerprint,'provenance_scope':'M3_ISOLATED_RESEARCH',
                     'request_started_at':request_started,'retrieved_at':retrieved_at,'recorded_at':now(),'http':meta,
                     'response_body_status':body_status,'response_bytes':len(body),
                     'response_sha256':None if body_status=='UNREAD_HTTP_ERROR_BODY' else sha(body),'articles':[]}
                stage='ACK_WRITE';save(ackpath,ack) # durable transport receipt before parsing
                ack_saved=True
                nbytes+=len(body)-MAX_BODY
                if meta.get('http_status')!=200:
                    code=meta.get('http_status');failure_class='HTTP_STATUS_SOURCE_DENIAL' if code in (403,406) else 'HTTP_STATUS'
                    status='PAUSED_HTTP_'+str(code) if code in (403,406,429,503) else 'HTTP_STATUS_'+str(code)
                else:
                    stage='PARSER'
                    articles,diagnostics=parse_metadata(body,s);ack['articles']=articles
                    # replace forbidden; persist parsed companion as a new append-only receipt
                    stage='PARSED_WRITE';save(Path(str(stem)+'.parsed.json'),{**ack,'recorded_at':now(),'articles':articles,'parse_diagnostics':diagnostics})
                    status='SUCCESS'
            except Exception as error:
                failure_class='LOCAL_READ_DEFECT' if stage in ('ACK_WRITE','PARSED_WRITE') else 'PARSER_DEFECT' if stage=='PARSER' else _failure_class(error)
                error_type=type(error).__name__
                status=('PARSER_DEFECT' if failure_class=='PARSER_DEFECT' else 'LOCAL_READ_DEFECT') if ack_saved else 'UNKNOWN'
            retry_until=_retry_until(meta.get('retry_after'),retrieved_at) if ack_saved and 'retrieved_at' in locals() else None
            terminal={'source_id':s['id'],'cycle_id':cycle,'source_url':s['url'],'plan_fingerprint':fingerprint,'provenance_scope':'M3_ISOLATED_RESEARCH',
                      'status':status,'failure_class':failure_class,'error_type':error_type,'http_status':meta.get('http_status'),
                      'retry_after_until':retry_until if status in ('PAUSED_HTTP_429','PAUSED_HTTP_503') else None,'completed_at':now()}
            save(term,terminal)
    return project(root)

def main():
    p=argparse.ArgumentParser();p.add_argument('--root',required=True);p.add_argument('--plan',required=True);p.add_argument('--initialize',action='store_true');p.add_argument('--cycle');p.add_argument('--enable-network',action='store_true');a=p.parse_args()
    root=safe_root(a.root); plan=validate_plan(read(Path(a.plan)))
    assert_external_root(root)
    if a.initialize:
        if root.exists() and any(root.iterdir()):raise ValueError('INITIALIZATION_ROOT_NOT_EMPTY')
        root.mkdir(parents=True,exist_ok=True);save(root/'plan.json',plan);save(root/'plan.sha256',{'sha256':sha(canonical(plan).encode())})
    if a.cycle: result=run(root,plan,a.cycle,a.enable_network)
    else: result=project(root) if (root/'plan.json').exists() else {'initialized':True}
    print(json.dumps(result,ensure_ascii=False,sort_keys=True))
if __name__=='__main__':main()
