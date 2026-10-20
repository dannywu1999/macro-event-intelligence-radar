"""Manual BEA research observation. Offline by default; no service or writer authority.

HTTP receipts use the unchanged M3.1 acquire/transport contract. Derived views are
recomputed from exclusive-write receipts, never backdated into production PIT.
"""
from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import urlsplit
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
import argparse,json,re
from research import m3_discovery as m,m31_access as a
from research.m31_economic import ReleaseList

VERSION='M3.4_BEA_READINESS_V1'
SCOPE='M34_RESEARCH_NOT_PROSPECTIVE_SUCCESS'
URLS={'terms':'https://www.bea.gov/help/faq/147','schedule':'https://www.bea.gov/news/schedule','current':'https://www.bea.gov/news/current-releases','rss_doc':'https://www.bea.gov/resources/for-developers','rss':'https://apps.bea.gov/rss/rss.xml'}
TARGETS={'GDP_Q3_2026_ADVANCE':'GDP (Advance Estimate), 3rd Quarter 2026','PIO_SEPTEMBER_2026':'Personal Income and Outlays, September 2026'}
SCHEDULED='2026-10-29T12:30:00Z'
MONTHS=['January','February','March','April','May','June','July','August','September','October','November','December']

def contract(urls=URLS):
    return a.AccessContract(VERSION,'M34','M34_IDENTITY.json',SCOPE,15,5_000_000,1,urls,{'bea':tuple(urls)},{k:'bea' for k in urls})

def utc(value):
    if not isinstance(value,str):raise ValueError('CLOCK_REQUIRED')
    d=datetime.fromisoformat(value.replace('Z','+00:00'))
    if d.tzinfo is None:raise ValueError('CLOCK_TIMEZONE_REQUIRED')
    return d.astimezone(timezone.utc)

def safe_url(url):
    u=urlsplit(url)
    if u.scheme!='https' or u.netloc not in ('www.bea.gov','bea.gov') or not re.fullmatch(r'/news/\d{4}/[a-z0-9-]+',u.path) or u.query or u.fragment:raise ValueError('ORIGINAL_URL_NOT_BEA_RELEASE')
    return url

def family(title):
    title=m.clean(title).replace('GDP, (','GDP (')
    p=re.fullmatch(r'Personal Income and Outlays, ([A-Za-z]+) (\d{4})',title)
    if p and p[1] in MONTHS:return 'PIO_'+p[1].upper()+'_'+p[2]
    g=re.match(r'^(?:GDP|Gross Domestic Product) \((Advance|Second|Third) Estimate\).*?, (1st|2nd|3rd|4th) Quarter (\d{4})(?:;.*)?$',title)
    if g:return 'GDP_Q'+g[2][0]+'_'+g[3]+'_'+g[1].upper()
    return None

def timestamp(raw):
    value,precision=m.date(raw)
    if precision in ('INVALID','TIMEZONE_UNKNOWN'):raise ValueError('SOURCE_CLOCK_INVALID')
    return value,precision

def metadata_hash(row):
    canonical={**row,'source_title_original':row['source_title_original'].replace('GDP, (','GDP (')}
    return m.sha(m.canonical(canonical).encode())

class StrictReleaseList(ReleaseList):
    def handle_starttag(self,tag,attrs):
        if tag=='time' and self.row is not None and 'published_raw' in self.row:raise ValueError('MULTIPLE_PUBLICATION_CLOCKS')
        super().handle_starttag(tag,attrs)

def release_list(endpoint,body):
    if endpoint=='current':
        p=StrictReleaseList();p.feed(body.decode('utf-8','strict'));p.close()
        if p.row is not None or not p.rows or len(p.rows)>500:raise ValueError('RELEASE_LIST_INVALID')
        rows=[{'title':r['title'],'url':r.get('url'),'raw':r.get('published_raw')} for r in p.rows]
    elif endpoint=='rss':
        rr,stats=m.parse_metadata(body,{'id':'bea','name':'BEA','article_hosts':['bea.gov'],'terms_status':'PUBLIC_DOMAIN_EXCEPTIONS'})
        import xml.etree.ElementTree as ET
        tree=ET.fromstring(body)
        for item in tree.iter():
            if item.tag.split('}')[-1] not in ('item','entry'):continue
            clocks=[n for n in item if n.tag.split('}')[-1] in ('pubDate','published','date')]
            if len(clocks)>1:raise ValueError('MULTIPLE_PUBLICATION_CLOCKS')
        rows=[{'title':r['title'],'url':r['url'],'raw':r['source_published_raw']} for r in rr]
    else:raise ValueError('NOT_ANNOUNCEMENT_LIST')
    out=[];seen=set()
    for r in rows:
        f=family(r['title'])
        if f is None:continue
        safe_url(r['url']);pub,precision=timestamp(r['raw'])
        if r['url'] in seen:raise ValueError('DUPLICATE_RELEASE_URL')
        seen.add(r['url'])
        out.append({'release_family':f,'source_url':r['url'],'source_title_original':r['title'],'source_reported_published_at':pub,'publication_precision':precision})
    return out

class Schedule(HTMLParser):
    def __init__(self):super().__init__();self.active=False;self.buf=[];self.rows=[];self.all=[]
    def handle_starttag(self,t,attrs):
        if t=='tr' and 'scheduled-releases-type-press' in dict(attrs).get('class','').split():self.active=True;self.buf=[]
    def handle_data(self,d):
        self.all.append(d)
        if self.active:self.buf.append(d)
    def handle_endtag(self,t):
        if t=='tr' and self.active:self.rows.append(m.clean(' '.join(self.buf)));self.active=False

def schedule(body):
    p=Schedule();p.feed(body.decode('utf-8','strict'));p.close()
    if '2026' not in ' '.join(p.all):raise ValueError('SCHEDULE_YEAR')
    rows=[]
    for f,title in TARGETS.items():
        found=[r for r in p.rows if title in r]
        if len(found)!=1 or not re.match(r'^October 29 8:30 AM\b',found[0]):raise ValueError('SCHEDULE_CHANGED_OR_MISSING')
        rows.append({'release_family':f,'source_title_original':title,'scheduled_release_at':SCHEDULED,'publisher_timezone':'America/New_York','schedule_source_url':URLS['schedule']})
    # Explicit timezone conversion, not a hardcoded fixed offset year round.
    assert datetime(2026,10,29,8,30,tzinfo=ZoneInfo('America/New_York')).astimezone(timezone.utc)==utc(SCHEDULED)
    return rows

class Document(HTMLParser):
    def __init__(self):super().__init__();self.depth=0;self.done=False;self.text=[];self.h1=False;self.title=[];self.titles=[];self.canonical=[]
    def handle_starttag(self,t,attrs):
        attrs=dict(attrs)
        if t=='link' and attrs.get('rel')=='canonical':self.canonical.append(attrs.get('href'))
        if t=='h1':self.h1=True;self.title=[]
        if t=='div':
            if self.depth:self.depth+=1
            elif not self.done and 'field--name-body' in attrs.get('class','').split():self.depth=1
    def handle_endtag(self,t):
        if t=='h1':self.h1=False;self.titles.append(m.clean(' '.join(self.title)))
        if t=='div' and self.depth:
            self.depth-=1
            if self.depth==0:self.done=True
    def handle_data(self,d):
        if self.depth:self.text.append(d)
        if self.h1:self.title.append(d)

def document(body,url):
    safe_url(url);p=Document();p.feed(body.decode('utf-8','strict'));p.close()
    titles=[t for t in p.titles if family(t)]
    if len(titles)!=1 or p.canonical!=[url] or not p.done or p.depth:raise ValueError('ORIGINAL_DOCUMENT_IDENTITY')
    # No 1500-char truncation: all normalized release body text is fingerprinted.
    text=' '.join(' '.join(p.text).split())
    if len(text)<80:raise ValueError('ORIGINAL_BODY_MISSING')
    return {'release_family':family(titles[0]),'source_url':url,'source_title_original':titles[0],'body_text':text,'content_sha256':m.sha(m.canonical({'title':titles[0],'body_text':text}).encode())}

def receipt(stem,c):
    """Verify source binding, complete immutable ACK and local clock order."""
    stem=Path(stem);a.validate_root(stem.parent.parent,c);reserve=m.read(Path(str(stem)+'.reserve.json'));ack=m.read(Path(str(stem)+'.ack.json'));term=m.read(Path(str(stem)+'.terminal.json'))
    for obj in (reserve,ack,term):
        if obj.get('request_id')!=stem.name or obj.get('endpoint_id')!=reserve['endpoint_id']:raise ValueError('RECEIPT_IDENTITY')
    ep=reserve['endpoint_id'];url=c.endpoints[ep]
    if reserve['url']!=url or ack['url']!=url or reserve['experiment_version']!=c.version or ack['scope']!=c.scope:raise ValueError('RECEIPT_SOURCE_SCOPE')
    times=[reserve['reserved_at'],ack['started_at'],ack['retrieved_at'],ack['recorded_at'],term['completed_at']]
    if [utc(t) for t in times]!=sorted(utc(t) for t in times):raise ValueError('LOCAL_CLOCK_ORDER')
    if term['status']!='SUCCESS' or term['http_status']!=200 or ack['http']['http_status']!=200:raise ValueError('SOURCE_NOT_SUCCESS')
    body=Path(str(stem)+'.body').read_bytes()
    if len(body)!=ack['response_bytes'] or m.sha(body)!=ack['response_sha256'] or len(body)>m.MAX_BODY:raise ValueError('BODY_HASH_MISMATCH')
    # ACK.recorded_at is sampled before its fsync. Terminal.completed_at is
    # sampled after ACK/body/parsed fsync, a conservative durable availability
    # boundary. Preserve the original raw bytes and expose this separately.
    return {**ack,'durable_recorded_at':term['completed_at']},body,m.sha(Path(str(stem)+'.ack.json').read_bytes())

def receipts(root):return sorted(Path(root).glob('**/HTTP/*.reserve.json'))
def budget(root):
    count=0;size=0
    for p in receipts(root):
        count+=1;ack=p.with_name(p.name.replace('.reserve.json','.ack.json'))
        size+=m.read(ack)['response_bytes'] if ack.exists() else m.MAX_BODY
    return count,size

def base(root):
    root=m.safe_root(root);m.assert_external_root(root);a.setup(root/'ACCESS',contract());return root

def acquire(root,namespace,c,ep,rid,enable_network=False,fetcher=m.bounded_get):
    if not enable_network:raise ValueError('NETWORK_DISABLED')
    root=base(root)
    if namespace!='ACCESS' and not re.fullmatch(r'ITEM_[a-f0-9]{64}',namespace):raise ValueError('NAMESPACE')
    if namespace=='ACCESS' and c!=contract():raise ValueError('CONTRACT_SUBSTITUTION')
    if namespace!='ACCESS':
        url=c.endpoints.get('original');safe_url(url)
        if c!=contract({'original':url}) or namespace!='ITEM_'+m.sha(url.encode()):raise ValueError('ITEM_CONTRACT_SUBSTITUTION')
        binding=m.read(root/namespace/'BINDING.json')
        source_ack,source_body,source_h=receipt(root/'ACCESS/HTTP'/binding['source_list_id'],contract())
        if source_h!=binding['source_receipt_sha256'] or binding['row'] not in release_list(source_ack['endpoint_id'],source_body) or binding['row']['source_url']!=url:raise ValueError('ORIGINAL_DISCOVERY_PROOF')
    lock=root/'BUDGET_LOCK';lock.mkdir(exist_ok=True)
    with m.owner_lock(lock):
        for p in receipts(root):
            term=p.with_name(p.name.replace('.reserve.json','.terminal.json'))
            if not term.exists() or m.read(term)['status']!='SUCCESS':raise ValueError('EXPERIMENT_PAUSED_NO_RETRY')
        n,b=budget(root)
        if n>=15 or b+m.MAX_BODY>5_000_000:raise ValueError('GLOBAL_BUDGET_EXHAUSTED')
        # Every resource has its own conservative minimum revisit interval.
        for p in receipts(root):
            r=m.read(p)
            if r['url']==c.endpoints[ep] and (utc(m.now())-utc(r['reserved_at'])).total_seconds()<1800 and r['request_id']!=rid:raise ValueError('MINIMUM_INTERVAL')
        def parse(endpoint,body):
            if endpoint in ('current','rss'):return release_list(endpoint,body)
            if endpoint=='schedule':return schedule(body)
            if endpoint=='original':return document(body,c.endpoints[endpoint])
            if endpoint=='terms' and b'information posted on this web site is in the public domain' not in body:raise ValueError('RIGHTS_CHANGED')
            if endpoint=='rss_doc' and URLS['rss'].encode() not in body:raise ValueError('RSS_NOT_ADVERTISED')
            return {'status':'SOURCE_CONTRACT_TEXT_PRESENT'}
        return a.acquire(root/namespace,ep,rid,True,fetcher=fetcher,parser=parse,contract=c)

def pin(root,schedule_id,terms_id,docs_id):
    root=base(root);proven={}
    for ep,rid in [('schedule',schedule_id),('terms',terms_id),('rss_doc',docs_id)]:
        ack,body,h=receipt(root/'ACCESS/HTTP'/rid,contract());proven[ep]={'receipt_id':rid,'receipt_sha256':h,'body_sha256':m.sha(body),'retrieved_at':ack['retrieved_at']}
        if ack['endpoint_id']!=ep:raise ValueError('WRONG_PREFLIGHT_RECEIPT')
        if ep=='schedule':targets=schedule(body)
        if ep=='terms' and b'information posted on this web site is in the public domain' not in body:raise ValueError('RIGHTS_CHANGED')
        if ep=='rss_doc' and URLS['rss'].encode() not in body:raise ValueError('RSS_NO_LONGER_ADVERTISED')
    path=root/'M34_PLAN.json'
    created=m.read(path)['created_at'] if path.exists() else m.now()
    plan={'version':VERSION,'targets':targets,'proof':proven,'created_at':created,'max_requests':15,'max_bytes':5_000_000,'min_resource_interval_seconds':1800,'scope':SCOPE}
    digest={'sha256':m.sha(m.canonical(plan).encode())}
    if path.exists():
        if m.read(path)!=plan or m.read(root/'M34_PLAN_SHA256.json')!=digest:raise ValueError('FROZEN_PLAN_MISMATCH')
    else:m.save(path,plan);m.save(root/'M34_PLAN_SHA256.json',digest)
    return plan

def frozen(root):
    plan=m.read(Path(root)/'M34_PLAN.json')
    if m.read(Path(root)/'M34_PLAN_SHA256.json')!={'sha256':m.sha(m.canonical(plan).encode())}:raise ValueError('PLAN_HASH_MISMATCH')
    # Re-pin revalidates all proof receipts without overwriting.
    return pin(root,*[plan['proof'][ep]['receipt_id'] for ep in ('schedule','terms','rss_doc')])

def observe(root,cycle,enable_network=False,fetcher=m.bounded_get):
    if not enable_network:raise ValueError('NETWORK_DISABLED')
    root=base(root);frozen(root)
    if not re.fullmatch(r'cycle_[0-9]{3}',cycle):raise ValueError('CYCLE_ID')
    lock=root/'CYCLE_LOCK';lock.mkdir(exist_ok=True)
    with m.owner_lock(lock):
        out=[]
        for ep in ('current','rss'):
            result=acquire(root,'ACCESS',contract(),ep,cycle+'_'+ep,True,fetcher)
            out.append(result)
            if result['status']!='SUCCESS':break
        return out

def original(root,list_id,url,rid,enable_network=False,fetcher=m.bounded_get):
    if not enable_network:raise ValueError('NETWORK_DISABLED')
    root=base(root);frozen(root);safe_url(url)
    ack,body,h=receipt(root/'ACCESS/HTTP'/list_id,contract())
    rows=[r for r in release_list(ack['endpoint_id'],body) if r['source_url']==url]
    if len(rows)!=1:raise ValueError('URL_NOT_IN_OFFICIAL_LIST')
    namespace='ITEM_'+m.sha(url.encode());c=contract({'original':url});a.setup(root/namespace,c)
    binding={'source_list_id':list_id,'source_receipt_sha256':h,'row':rows[0]}
    path=root/namespace/'BINDING.json'
    if path.exists():
        old=m.read(path)
        if old['row']['source_url']!=url:raise ValueError('ITEM_BINDING_CHANGED')
        # Original discovery binding stays immutable; later list revisions stay separate receipts.
    else:m.save(path,binding)
    return acquire(root,namespace,c,'original',rid,True,fetcher)

def transitions(entries,as_of=None,synthetic=False):
    """Pure replay: caller must supply validated receipts, never trust external rows."""
    last={};first={};out=[];families={}
    for e in sorted(entries,key=lambda r:(utc(r['recorded_at']),r['receipt_sha256'])):
        clocks=[utc(e[k]) for k in ('request_started_at','response_observed_at','retrieved_at','recorded_at')]
        if clocks!=sorted(clocks):raise ValueError('CLOCK_ORDER')
        if as_of and utc(e['recorded_at'])>utc(as_of):continue
        pub=e['source_reported_published_at'];precision=e['publication_precision']
        normalized,p=timestamp(pub)
        if p!=precision:raise ValueError('PUBLICATION_PRECISION_MISMATCH')
        if pub and (utc(pub) if precision=='EXACT_SOURCE_REPORTED' else datetime.fromisoformat(pub).replace(tzinfo=timezone.utc))>utc(e['retrieved_at']):raise ValueError('PUBLICATION_IN_FUTURE')
        key=e['source_url'];prior=last.get(key)
        if key in families and families[key]!=e['release_family']:raise ValueError('URL_FAMILY_CONFLICT')
        families[key]=e['release_family'];first.setdefault(key,e['retrieved_at'])
        content={k:e[k] for k in ('release_family','source_title_original','source_reported_published_at','publication_precision','content_sha256')}
        content['source_title_original']=content['source_title_original'].replace('GDP, (','GDP (')
        fp=m.sha(m.canonical(content).encode())
        kind='NEW' if prior is None else 'DUPLICATE' if prior==fp else 'UPDATED'
        row={**e,'first_observed_in_experiment':first[key],'last_observed_at':e['retrieved_at'],'observation_kind':kind,'availability_scope':'SYNTHETIC_HISTORICAL_REHEARSAL' if synthetic else SCOPE,'official_proposition_status':'NOT_ADJUDICATED','detection_latency':'UNKNOWN'}
        out.append(row);last[key]=fp
    return out

def failure_status(stem,as_of):
    term=Path(str(stem)+'.terminal.json')
    if not term.exists():return {'request_id':stem.name,'status':'INTERRUPTED_UNKNOWN_ACK'} if as_of is None else None
    result=m.read(term)
    if as_of and utc(result['completed_at'])>utc(as_of):return None
    return {'request_id':stem.name,'status':result['status']}

def project(root,as_of=None):
    root=m.safe_root(root);a.validate_root(root/'ACCESS',contract());plan=frozen(root);entries=[];failures=[]
    if as_of and utc(as_of)<utc(plan['created_at']):return {'scope':SCOPE,'status':'UNAVAILABLE_BEFORE_PLAN','observations':[],'documents':[]}
    # List announcements and original documents are separate evidence layers.
    for path in sorted((root/'ACCESS/HTTP').glob('*.reserve.json')):
        stem=path.with_name(path.name.replace('.reserve.json',''));r=m.read(path)
        if r['endpoint_id'] not in ('current','rss'):continue
        term=Path(str(stem)+'.terminal.json')
        if not term.exists() or m.read(term)['status']!='SUCCESS':
            status=failure_status(stem,as_of)
            if status:failures.append(status)
            continue
        ack,body,h=receipt(stem,contract())
        if as_of and utc(ack['durable_recorded_at'])>utc(as_of):continue
        for row in release_list(ack['endpoint_id'],body):
            entries.append({**row,'source_list_receipt_id':ack['request_id'],'scheduled_release_at':SCHEDULED if row['release_family'] in TARGETS else None,'schedule_source_url':URLS['schedule'],'schedule_retrieved_at':plan['proof']['schedule']['retrieved_at'],'request_started_at':ack['started_at'],'response_observed_at':ack['retrieved_at'],'retrieved_at':ack['retrieved_at'],'recorded_at':ack['durable_recorded_at'],'ack_prewrite_recorded_at':ack['recorded_at'],'receipt_sha256':h,'content_sha256':metadata_hash(row),'evidence_layer':'ANNOUNCEMENT_METADATA'})
    result=transitions(entries,as_of)
    documents=[]
    for namespace in root.glob('ITEM_*'):
        binding=m.read(namespace/'BINDING.json');url=binding['row']['source_url'];c=contract({'original':url})
        source_ack,source_body,source_h=receipt(root/'ACCESS/HTTP'/binding['source_list_id'],contract())
        if source_h!=binding['source_receipt_sha256'] or binding['row'] not in release_list(source_ack['endpoint_id'],source_body):raise ValueError('ORIGINAL_DISCOVERY_PROOF')
        for path in namespace.glob('HTTP/*.reserve.json'):
            stem=path.with_name(path.name.replace('.reserve.json',''));term=Path(str(stem)+'.terminal.json')
            if not term.exists() or m.read(term)['status']!='SUCCESS':
                status=failure_status(stem,as_of)
                if status:failures.append(status)
                continue
            ack,body,h=receipt(stem,c)
            if as_of and utc(ack['durable_recorded_at'])>utc(as_of):continue
            doc=document(body,url)
            if doc['release_family']!=binding['row']['release_family']:raise ValueError('DOCUMENT_FAMILY_MISMATCH')
            documents.append({**doc,'request_started_at':ack['started_at'],'response_observed_at':ack['retrieved_at'],'receipt_sha256':h,'retrieved_at':ack['retrieved_at'],'recorded_at':ack['durable_recorded_at'],'ack_prewrite_recorded_at':ack['recorded_at'],'source_reported_published_at':binding['row']['source_reported_published_at'],'publication_precision':binding['row']['publication_precision'],'source_time_basis':'FIRST_DISCOVERY_LIST_NOT_REVISION_PUBLICATION_TIME','schedule_source_url':URLS['schedule'],'schedule_retrieved_at':plan['proof']['schedule']['retrieved_at'],'scheduled_release_at':SCHEDULED if doc['release_family'] in TARGETS else None,'evidence_layer':'ORIGINAL_DOCUMENT_NOT_AUTOMATIC_PROPOSITION_VERIFICATION'})
    observed={x['release_family'] for x in result}
    return {'scope':SCOPE,'targets':[{'release_family':f,'scheduled_release_at':SCHEDULED,'status':'OBSERVED_ANNOUNCEMENT' if f in observed else 'PLANNED_NOT_OBSERVED'} for f in TARGETS],'observations':result,'documents':transitions(documents,as_of),'source_failures':failures,'network_accounting':budget(root) if as_of is None else None,'network_accounting_scope':'CURRENT_OPERATIONAL_NOT_ASOF','current_prospective_detection':'NOT_TESTED','global_first_seen_proven':False,'frozen_macroview':'UNAVAILABLE','production_capture_enabled':False}

def income_fact(verified_document):
    """A narrow statement extractor, not generic promotion of official-origin news.

    Caller must validate the original receipt before passing this document.
    The value is a statement in this exact retrieved vintage, not final truth.
    """
    d=verified_document
    if d.get('evidence_layer')!='ORIGINAL_DOCUMENT_NOT_AUTOMATIC_PROPOSITION_VERIFICATION' or not d.get('receipt_sha256'):raise ValueError('ORIGINAL_RECEIPT_REQUIRED')
    family_id=d['release_family']
    match=re.fullmatch(r'PIO_([A-Z]+)_(\d{4})',family_id)
    if not match:raise ValueError('NOT_MONTHLY_PIO')
    month=match[1].title()
    sentence=re.search(r'\bPersonal income increased \$(\d+(?:\.\d+)?) billion \((\d+(?:\.\d+)?) percent at a monthly rate\) in '+month+r'\b',d['body_text'])
    if not sentence:raise ValueError('SPECIFIC_PROPOSITION_NOT_FOUND')
    return {'official_proposition_status':'VERIFIED_DOCUMENT_STATEMENT','claim_scope':'SOURCE_REPORTED_ESTIMATE_IN_THIS_RETRIEVED_VINTAGE','indicator':'NOMINAL_PERSONAL_INCOME_NOT_PCE_PRICE_NOT_CPI','reference_month':month,'reference_year':match[2],'change_usd_billion':sentence[1],'change_percent_monthly':sentence[2],'evidence_excerpt':sentence[0],'source_url':d['source_url'],'receipt_sha256':d['receipt_sha256'],'content_sha256':d['content_sha256'],'retrieved_at':d['retrieved_at'],'recorded_at':d['recorded_at'],'source_published_at':d['source_reported_published_at'],'macroview':{'status':'RESEARCH_PREVIEW_NOT_FROZEN','surprise':'UNKNOWN','polymarket':'UNAVAILABLE','market_reaction':'NOT_MEASURED','causality':'NOT_ESTABLISHED','trading':'NOT_AUTHORIZED'}}

def handoff(root,as_of=None):
    projection=project(root,as_of);facts=[];pending=[];latest={}
    for d in projection['documents']:latest[d['source_url']]=d
    for d in latest.values():
        try:facts.append(income_fact(d))
        except ValueError:pending.append({'source_url':d['source_url'],'release_family':d['release_family'],'status':'SPECIFIC_PROPOSITION_REQUIRES_MANUAL_REVIEW','receipt_sha256':d['receipt_sha256']})
    return {'scope':SCOPE,'official_statements':facts,'pending':pending,'macroview':'RESEARCH_PREVIEW_NOT_FROZEN','frozen_macroview':'UNAVAILABLE','polymarket':'UNAVAILABLE','surprise':'UNKNOWN','detection_latency':'UNKNOWN','causality':'NOT_ESTABLISHED','trading':'NOT_AUTHORIZED'}

def main():
    p=argparse.ArgumentParser();p.add_argument('--root',required=True);p.add_argument('--enable-network',action='store_true');p.add_argument('--probe',choices=URLS);p.add_argument('--request-id');p.add_argument('--pin',nargs=3,metavar=('SCHEDULE_ID','TERMS_ID','RSS_DOC_ID'));p.add_argument('--cycle');p.add_argument('--original-url');p.add_argument('--list-id');p.add_argument('--project',action='store_true');p.add_argument('--handoff',action='store_true');p.add_argument('--as-of');p.add_argument('--snapshot');v=p.parse_args()
    actions=sum(bool(x) for x in (v.probe,v.pin,v.cycle,v.original_url,v.project,v.handoff))
    if actions>1:raise ValueError('ONE_ACTION_ONLY')
    if v.probe:r=acquire(v.root,'ACCESS',contract(),v.probe,v.request_id,v.enable_network)
    elif v.pin:r=pin(v.root,*v.pin)
    elif v.cycle:r=observe(v.root,v.cycle,v.enable_network)
    elif v.original_url:r=original(v.root,v.list_id,v.original_url,v.request_id,v.enable_network)
    elif v.project:r=project(v.root,v.as_of)
    elif v.handoff:r=handoff(v.root,v.as_of)
    else:r={'mode':'OFFLINE','network_requests':0,'existing_root':Path(v.root).exists()}
    if v.snapshot:
        if not v.project or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',v.snapshot):raise ValueError('SNAPSHOT_ID')
        m.save(Path(v.root)/'SNAPSHOTS'/(v.snapshot+'.json'),{'snapshot_recorded_at':m.now(),'plan_sha256':m.read(Path(v.root)/'M34_PLAN_SHA256.json')['sha256'],'projection':r})
    print(json.dumps(r,ensure_ascii=True,sort_keys=True))
    if isinstance(r,dict) and 'status' in r and r['status']!='SUCCESS' or isinstance(r,list) and any(x.get('status')!='SUCCESS' for x in r):raise SystemExit(2)
if __name__=='__main__':main()
