"""Discovery-only BLS values / BEA announcements. No automatic official promotion."""
from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import urljoin,urlsplit
from decimal import Decimal,InvalidOperation
from datetime import datetime,timezone
import argparse,json,re
from research import m3_discovery as m
from research import m31_access as access

SERIES={
 'bls_cpi':('CUUR0000SA0','CPI_U_ALL_ITEMS_US_CITY_AVERAGE_NSA','INFLATION_CPI','INDEX_1982_84_100'),
 'bls_payroll':('CES0000000001','TOTAL_NONFARM_PAYROLL_EMPLOYMENT_SA','EMPLOYMENT_NFP_LEVEL','THOUSANDS_OF_PERSONS'),
}
RIGHTS='US_GOVERNMENT_DATA_ATTRIBUTION_THIRD_PARTY_EXCEPTIONS'

def bls(data,endpoint):
    doc=json.loads(data)
    if not isinstance(doc,dict) or doc.get('status')!='REQUEST_SUCCEEDED' or doc.get('message') not in ([],None):raise ValueError('BLS_ERROR_PAYLOAD')
    series=doc.get('Results',{}).get('series',[]);expected,label,category,unit=SERIES[endpoint]
    if len(series)!=1 or series[0].get('seriesID')!=expected or not series[0].get('data'):raise ValueError('BLS_SERIES_MISMATCH_OR_EMPTY')
    if len(series[0]['data'])>500:raise ValueError('RECORD_LIMIT')
    rows=[];keys=set()
    for raw in series[0]['data']:
        year=raw.get('year');period=raw.get('period');value=raw.get('value')
        if not isinstance(year,str) or not re.fullmatch(r'\d{4}',year) or not isinstance(period,str) or not re.fullmatch(r'M(0[1-9]|1[0-3])',period):raise ValueError('BLS_PERIOD_INVALID')
        if not isinstance(value,str):raise ValueError('BLS_VALUE_TYPE')
        try: valid=value=='-' or Decimal(value).is_finite()
        except InvalidOperation:valid=False
        if not valid:raise ValueError('BLS_VALUE_INVALID')
        key='BLS:'+expected+':'+year+':'+period
        if key in keys:raise ValueError('CONFLICTING_PERIOD')
        keys.add(key)
        footnotes=raw.get('footnotes',[])
        if not isinstance(footnotes,list) or not all(isinstance(x,dict) and all(k in ('code','text') and isinstance(v,str) for k,v in x.items()) for x in footnotes):raise ValueError('BLS_FOOTNOTES_INVALID')
        rows.append({'record_id':key,'record_type':'STATISTICAL_VALUE_NOT_RELEASE_ANNOUNCEMENT','endpoint_id':endpoint,'source_publisher':'U.S. Bureau of Labor Statistics','original_data_authority':'BLS','source_url':access.ENDPOINTS[endpoint],'series_id':expected,'indicator':label,'category':category,'unit':unit,'reference_year':year,'reference_period':period,'reference_period_precision':'ANNUAL_AVERAGE' if period=='M13' else 'MONTH_ONLY','value':None if value=='-' else value,'value_raw':value,'value_status':'SOURCE_UNAVAILABLE' if value=='-' else 'AVAILABLE','footnotes':footnotes,'source_published_raw':None,'source_published_at':None,'publication_precision':'UNKNOWN','rights':RIGHTS,'authority_status':'DISCOVERY_ONLY_OFFICIAL_PROPOSITION_NOT_ADJUDICATED'})
    return {'records':rows,'raw_count':len(rows),'rejected_count':0,'publication_semantics':'REFERENCE_PERIOD_IS_NOT_PUBLICATION_TIME','release_detection_capability':'NOT_PROVEN_API_MAY_LAG_PUBLICATION','upstream_message':doc.get('message',[])}

class ReleaseList(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True);self.row=None;self.anchor=False;self.in_time=False;self.rows=[];self.title=[];self.time_text=[]
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag=='tr' and 'release-row' in a.get('class','').split():
            if self.row is not None:raise ValueError('NESTED_RELEASE_ROW')
            self.row={};self.title=[];self.time_text=[]
        if self.row is None:return
        if tag=='a':
            if 'url' in self.row:raise ValueError('MULTIPLE_RELEASE_LINKS')
            self.row['url']=urljoin(access.ENDPOINTS['bea_releases'],a.get('href',''));self.anchor=True
        if tag=='time':self.row['published_raw']=a.get('datetime');self.in_time=True
    def handle_data(self,data):
        if self.row is not None:
            if self.anchor:self.title.append(data)
            if self.in_time:self.time_text.append(data)
    def handle_endtag(self,tag):
        if tag=='a':self.anchor=False
        if tag=='time':self.in_time=False
        if tag=='tr' and self.row is not None:
            self.row['title']=m.clean(''.join(self.title));self.row['published_display']=m.clean(''.join(self.time_text));self.rows.append(self.row);self.row=None

def bea(data):
    parser=ReleaseList();parser.feed(data.decode('utf-8','strict'));parser.close()
    if parser.row is not None or not parser.rows or len(parser.rows)>500:raise ValueError('NOT_BEA_RELEASE_LIST_OR_TRUNCATED')
    rows=[];rejected={};urls=set()
    for raw in parser.rows:
        u=urlsplit(raw.get('url',''))
        if u.scheme!='https' or u.hostname not in ('www.bea.gov','bea.gov') or not u.path.startswith('/news/') or u.username or u.password or u.port not in (None,443):raise ValueError('BEA_LINK_IDENTITY')
        if not raw['title'] or len(raw['title'])>1500:raise ValueError('BEA_TITLE_INVALID')
        if raw['url'] in urls:raise ValueError('DUPLICATE_RELEASE_URL')
        urls.add(raw['url']);published,precision=m.date(raw.get('published_raw'))
        selected=bool(re.match(r'^Personal Income and Outlays,\s',raw['title']))
        if not selected:rejected['NOT_MONTHLY_PERSONAL_INCOME_OUTLAYS']=rejected.get('NOT_MONTHLY_PERSONAL_INCOME_OUTLAYS',0)+1;continue
        rows.append({'record_id':m.article_identity(raw['url']),'record_type':'RELEASE_ANNOUNCEMENT_METADATA','endpoint_id':'bea_releases','source_publisher':'U.S. Bureau of Economic Analysis','original_data_authority':'BEA','source_url':raw['url'],'title_original':raw['title'],'indicator':'PERSONAL_INCOME_AND_OUTLAYS_INCLUDING_PCE','category':'INFLATION_PCE_NOT_CPI','source_published_raw':raw.get('published_raw'),'source_published_at':published,'publication_precision':precision,'source_date_display':raw['published_display'],'rights':RIGHTS,'authority_status':'DISCOVERY_ONLY_OFFICIAL_PROPOSITION_NOT_ADJUDICATED'})
    return {'records':rows,'raw_count':len(parser.rows),'rejected_count':len(parser.rows)-len(rows),'rejected_by_reason':rejected,'publication_semantics':'SOURCE_REPORTED_DATETIME_NOT_PROOF_OF_FIRST_PUBLIC_AVAILABILITY','release_detection_capability':'CURRENT_LIST_MAY_REPLACE_OLD_RELEASES_NOT_COMPLETE_ARCHIVE'}

def parse(endpoint,body):
    if endpoint in SERIES:return bls(body,endpoint)
    if endpoint=='bea_releases':return bea(body)
    raise ValueError('NO_SELECTED_ADAPTER')

def parse_saved_probe(root,endpoint):
    """New derived receipt for previously acquired bytes; never re-date old ACKs."""
    root=access.setup(root);stem=root/'HTTP'/('probe_'+endpoint)
    with m.owner_lock(root):
        ack=m.read(Path(str(stem)+'.ack.json'));body=Path(str(stem)+'.body').read_bytes()
        if ack['http']['http_status']!=200 or m.sha(body)!=ack['response_sha256']:raise ValueError('PROBE_INTEGRITY')
        target=Path(str(stem)+'.parsed.json')
        if target.exists():return
        result=parse(endpoint,body)
        m.save(target,{'request_id':'probe_'+endpoint,'endpoint_id':endpoint,'retrieved_at':ack['retrieved_at'],'http_ack_recorded_at':ack['recorded_at'],'recorded_at':m.now(),'response_sha256':ack['response_sha256'],'result':result,'parse_scope':'POST_SELECTION_DERIVATION_OF_UNCHANGED_PROBE_BODY'})

def project(root):
    root=m.safe_root(root);m.assert_external_root(root)
    if m.read(root/'M31_IDENTITY.json').get('version')!=access.VERSION:raise ValueError('NOT_M31_ROOT')
    access.frozen(root)
    first={};durable={};metadata_recorded={};latest={};observations=[]
    for path in sorted((root/'HTTP').glob('*.parsed.json'),key=lambda p:(m.read(p)['retrieved_at'],p.name)):
        ack=m.read(path)
        stem=path.with_name(path.name.replace('.parsed.json',''))
        transport=m.read(Path(str(stem)+'.ack.json'));body=Path(str(stem)+'.body').read_bytes()
        if transport['http']['http_status']!=200 or ack['response_sha256']!=transport['response_sha256'] or m.sha(body)!=ack['response_sha256'] or ack['retrieved_at']!=transport['retrieved_at'] or ack['http_ack_recorded_at']!=transport['recorded_at'] or ack['endpoint_id']!=transport['endpoint_id'] or ack['request_id']!=transport['request_id'] or transport['url']!=access.ENDPOINTS[ack['endpoint_id']] or ack['result']!=parse(ack['endpoint_id'],body):raise ValueError('RECEIPT_INTEGRITY')
        times=[datetime.fromisoformat(v.replace('Z','+00:00')) for v in (ack['retrieved_at'],ack['http_ack_recorded_at'],ack['recorded_at'])]
        if times!=sorted(times):raise ValueError('LOCAL_CLOCK_ORDER')
        for row in ack['result']['records']:
            key=row['record_id'];fingerprint=m.sha(m.canonical(row).encode());prior=latest.get(key)
            kind='new' if prior is None else 'duplicate' if prior['content_sha256']==fingerprint else 'updated'
            first.setdefault(key,ack['retrieved_at']);durable.setdefault(key,ack['http_ack_recorded_at']);metadata_recorded.setdefault(key,ack['recorded_at']);pub=row.get('source_published_at');interval=None;interval_status='UNKNOWN_PUBLICATION_TIME'
            if row['publication_precision']=='EXACT_SOURCE_REPORTED' and pub:
                delta=(datetime.fromisoformat(ack['retrieved_at'].replace('Z','+00:00'))-datetime.fromisoformat(pub.replace('Z','+00:00'))).total_seconds()
                if delta>=0:interval=delta;interval_status='SOURCE_REPORTED_TO_RETRIEVAL_NOT_DETECTION_LATENCY'
                else:interval_status='FUTURE_OR_CLOCK_DISPUTED'
            item={**row,'content_sha256':fingerprint,'first_observed_at_in_M31':first[key],'first_durable_http_ack_at_in_M31':durable[key],'first_metadata_recorded_at_in_M31':metadata_recorded[key],'retrieved_at':ack['retrieved_at'],'http_ack_recorded_at':ack['http_ack_recorded_at'],'recorded_at':ack['recorded_at'],'request_id':ack['request_id'],'observation_kind':kind,'first_observed_scope':'M31_ONLY_NOT_GLOBAL_FIRST_SEEN','source_to_observation_seconds':interval,'source_to_observation_status':interval_status}
            latest[key]=item;observations.append(item)
    return {'scope':access.VERSION,'observations':observations,'latest':list(latest.values()),'first_observed_at':first,'global_first_seen_proven':False,'breaking_detection_proven':False,'as_of_api':False}

def main():
    p=argparse.ArgumentParser();p.add_argument('--root',required=True);p.add_argument('--plan');p.add_argument('--parse-probes',action='store_true');p.add_argument('--cycle');p.add_argument('--enable-network',action='store_true');a=p.parse_args()
    if a.cycle:
        if not a.plan:raise ValueError('PLAN_REQUIRED')
        access.run(a.root,m.read(Path(a.plan)),a.cycle,a.enable_network,parse)
    elif a.parse_probes:
        for endpoint in ('bls_cpi','bls_payroll','bea_releases'):parse_saved_probe(a.root,endpoint)
    print(json.dumps(project(a.root),ensure_ascii=False,sort_keys=True))
if __name__=='__main__':main()
