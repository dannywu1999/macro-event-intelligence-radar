"""Static research projection of explicitly reviewed saved evidence. No acquisition."""
from pathlib import Path
from datetime import datetime,timezone
from urllib.parse import urlsplit
import copy,hashlib,html,json
from contracts_v0 import build_canonical_events,build_official_evidence_projection

SLUG='m2-cpi-20261014'
CASE_FILES=frozenset(('index.html','case.json','case.txt','case.md','asof-examples.json','manifest.json'))
def sha(raw):return hashlib.sha256(raw).hexdigest()
def encoded(x):return (json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode()
def instant(s):
    d=datetime.fromisoformat(s.replace('Z','+00:00'))
    if d.tzinfo is None:raise ValueError('TIMEZONE_REQUIRED')
    return d.astimezone(timezone.utc)
def validate(c):
    if c['scope']!='ONE_SHOT_SAVED_RESEARCH_CASE_NOT_LIVE' or c['live_feed'] is not False or c['trading_signal'] is not False:raise ValueError('SCOPE')
    if c['preview']['status']!='PREVIEW' or c['frozen_macroview_status']!='UNAVAILABLE_NO_APPROVED_LEDGER' or c['durable_first_seen_status']!='FIRST_SEEN_NOT_PROVEN':raise ValueError('PIT_BOUNDARY')
    if c['detection_latency']!='UNKNOWN' or c['market_reaction']['value'] is not None or c['polymarket']['value'] is not None:raise ValueError('UNKNOWN_REQUIRED')
    if c['rights']['policy_status']!='PUBLIC_ELIGIBLE_ATTRIBUTED_BLS_TEXT_ONLY':raise ValueError('RIGHTS')
    doc=c['official_document'];d=c['discovery'];item=d['item']
    expected='https://www.bls.gov/news.release/archives/cpi_10142026.htm'
    if doc['source_url']!=expected or item['article_reference']!=expected:raise ValueError('OFFICIAL_URL_BINDING')
    if doc['published_at'] is not None or doc['publication_precision']!='DATE_ONLY' or c['time_conflict']['status']!='UNRESOLVED_SOURCE_CLOCK_CONFLICT':raise ValueError('PUBLICATION_UNPROVEN')
    for obj in (doc,d):
        if instant(obj['recorded_at'])<instant(obj['retrieved_at']):raise ValueError('RECORD_BEFORE_RETRIEVAL')
    if instant(c['as_of'])<max(instant(doc['recorded_at']),instant(d['recorded_at'])):raise ValueError('PREVIEW_BEFORE_EVIDENCE')
    if instant(c['preview']['available_at'])<instant(doc['recorded_at']):raise ValueError('PREVIEW_CLOCK')
    canonical=build_canonical_events([item])['events'][0]
    if canonical['event_id']!=c['canonical_event']['event_id'] or canonical['article_count']!=1:raise ValueError('CANONICAL_ID')
    projection=build_official_evidence_projection(c['official_packets'],[item],[canonical])
    for e in projection['official_evidence']:
        e.update(first_seen_scope='THIS_M2_DOCUMENT_OBSERVATION_ONLY',durable_first_seen_proven=False)
    projection['events'][0].update(first_detected_scope='SAVED_LOCAL_OBSERVATION_NOT_GLOBAL_FIRST_SEEN',durable_first_seen_proven=False)
    if projection['official_evidence']!=c['official_evidence'] or projection['events'][0]!=c['canonical_event']:raise ValueError('OFFICIAL_CONTRACT')
    if len(c['propositions'])!=4 or len({p['id'] for p in c['propositions']})!=4:raise ValueError('PROPOSITION_COUNT')
    for p in c['propositions']:
        if p['support']!='DIRECTLY_SUPPORTED' or p['source_url']!=expected or p['response_sha256']!=doc['response_sha256'] or p['available_at']!=c['created_at']:raise ValueError('SUPPORT_BINDING')
    if any(r.get('official_project_first_seen_scope')!='THIS_M2_DOCUMENT_OBSERVATION_ONLY' for r in c['official_packets']):raise ValueError('LOCAL_SCOPE_REQUIRED')
    if c['canonical_event']['verification_status']!='UNVERIFIED_NEWS':raise ValueError('NEWS_NOT_AUTHORITY')
    return c

def project_as_of(c,as_of):
    """Saved-receipt availability only; not a production historical ledger."""
    validate(c);at=instant(as_of);d=c['discovery'];doc=c['official_document']
    news=at>=max(instant(d['retrieved_at']),instant(d['recorded_at']))
    official=news and at>=max(instant(doc['retrieved_at']),instant(doc['recorded_at']))
    propositions=[copy.deepcopy(p) for p in c['propositions'] if official and at>=instant(p['available_at'])]
    preview=official and len(propositions)==4 and at>=instant(c['preview']['available_at'])
    return {'as_of':as_of,'scope':'SAVED_RECEIPT_AVAILABILITY_NOT_PRODUCTION_REPLAY','ledger_status':'UNAVAILABLE_NO_APPROVED_LEDGER','event_id':c['canonical_event']['event_id'] if news else None,'discovery':copy.deepcopy(d) if news else None,'official_document':copy.deepcopy(doc) if official else None,'propositions':propositions,'preview':copy.deepcopy(c['preview']) if preview else None,'title_zh':c['title_zh'] if preview else None,'status':'PREVIEW' if preview else 'OFFICIAL_DOCUMENT_ONLY_NOT_YET_REVIEWED' if official else 'NEWS_ONLY' if news else 'UNAVAILABLE','durable_first_seen_status':'FIRST_SEEN_NOT_PROVEN'}

def inventory(path):
    if not path.exists():return
    if path.is_symlink():raise ValueError('PUBLIC_SYMLINK')
    for p in path.rglob('*'):
        if p.is_symlink():raise ValueError('PUBLIC_SYMLINK')
        relative=p.relative_to(path).as_posix()
        if p.is_dir():
            if relative!=SLUG:raise ValueError('UNREVIEWED_RESEARCH_DIRECTORY')
        elif relative not in {SLUG+'/'+name for name in CASE_FILES}:raise ValueError('UNREVIEWED_RESEARCH_ASSET')

def render(c):
    validate(c);d=c['discovery'];doc=c['official_document'];v=c['preview'];e=c['canonical_event']
    timeline=[{'role':'REFERENCE_PERIOD_DATE_ONLY','value':'2026-09','meaning_zh':'統計參考月，不是系統觀測時間。'},
      {'role':'SOURCE_REPORTED_PUBLICATION_CONFLICTING','value':d['item']['reported_at'],'meaning_zh':'Feed 自報；比文件禁發時間早，可靠性未釐清。'},
      {'role':'SCHEDULED_EMBARGO_NOT_ACTUAL_PUBLICATION','value':doc['scheduled_embargo_release_at'],'meaning_zh':'官方文件標示禁發時間；未實測當時上線。'},
      {'role':'SAVED_NEWS_OBSERVED','value':d['retrieved_at'],'meaning_zh':'既存10月18日Feed實際取得時間，原樣保留。'},
      {'role':'SAVED_NEWS_RECORDED','value':d['recorded_at'],'meaning_zh':'既存新聞metadata記錄時間，不是全球首次。'},
      {'role':'OFFICIAL_DOCUMENT_RETRIEVED_IN_M2','value':doc['retrieved_at'],'meaning_zh':'本輪取得官方原文，這之前不能視為系統已核實。'},
      {'role':'OFFICIAL_DOCUMENT_RECORDED_IN_M2','value':doc['recorded_at'],'meaning_zh':'原文收據落地時間，保存投影以此為可得性下限。'},
      {'role':'PROPOSITION_REVIEW_AND_PREVIEW_AS_OF','value':c['as_of'],'meaning_zh':'命題核對、翻譯與研究解讀建立時間；不回填到原文取得時，非正式凍結。'}]
    data=copy.deepcopy(c);data['timeline']=timeline
    examples=[project_as_of(c,'2026-10-14T12:30:00Z'),project_as_of(c,d['recorded_at']),project_as_of(c,doc['recorded_at']),project_as_of(c,c['as_of'])]
    lines=['# '+c['title_zh'],'',c['title_en'],'','M2 · 獨立研究案例 · PREVIEW · 非即時新聞 · 非交易訊號',
      '這是保存觀測與本輪官方核對，不是剛發現的突發新聞。原 M1 七篇快照保持不變。','',
      '## 為什麼值得研究',c['why_it_matters_zh'],'',
      '事件／發布日期：2026-10-14；統計參考月：2026-09。實際上線分鐘 UNKNOWN。',
      'As-of (UTC): '+c['as_of'],'Canonical article-set identity: '+e['event_id'],
      'Grouping: SINGLE_ARTICLE_INSUFFICIENT_MERGE_EVIDENCE（沒有跨稿強制合併）','',
      '## 發現與官方核實的角色',
      '發現：BLS CPI Feed 保存線索，仍為 UNVERIFIED_NEWS。不是獨立媒體報導或多來源交叉驗證。',
      '發現原文：'+d['item']['article_reference'],
      '官方核實：本輪另讀 BLS 文件 USDL-26-1574，只支持下列四個統計命題。',
      '原始觀測維持：'+d['retrieved_at'],'', '## 官方直接支持的命題（不是整個事件的背書）']
    for p in c['propositions']:lines.extend(['','- '+p['statement_zh'],'  DIRECTLY_SUPPORTED · '+p['source_url'],'  原文：'+p['supporting_excerpt_en']])
    lines.extend(['','## 時間與未知','官方精確 published_at: UNKNOWN / null；DATE_ONLY=2026-10-14。',c['time_conflict']['explanation_zh'],'DETECTION_LATENCY=UNKNOWN；不是39分鐘延遲或即時偵測證明。'])
    for row in timeline:lines.append('- '+row['role']+': '+row['value']+' — '+row['meaning_zh'])
    lines.extend(['','## MacroView PREVIEW：條件傳導假設',*['- '+x for x in v['hypotheses_zh']], '','## 未知與不支持的推論',*['- '+x for x in v['unknowns_zh']],*['- '+x['claim_zh']+'：'+x['status'] for x in c['unsupported_claims']], '', '## 接下來的證據',*['- '+x for x in v['next_evidence_zh']], '', '## PIT 與研究門檻',*['- '+x for x in c['pit_limitations_zh']], 'FROZEN: UNAVAILABLE_NO_APPROVED_LEDGER','Global first-seen: FIRST_SEEN_NOT_PROVEN','Polymarket: UNAVAILABLE','Market reaction: NOT_MEASURED','CAUSALITY: NOT_ESTABLISHED','Research gate: '+v['research_gate'],'', '## 收據與使用範圍','官方回應 SHA256: '+doc['response_sha256'],'本輪官方收據 SHA256: '+doc['receipt_sha256'],'發現收據 SHA256: '+d['receipt_sha256'],'BLS 來源與公開使用政策：'+c['rights']['policy_url'],c['rights']['scope'],c['rights']['translation'],'','Hash只證明保存位元組，不保證官方網頁永久不變，也不代表市場因果已成立。','', '## 可讀格式','./case.json · ./case.txt · ./asof-examples.json · ./manifest.json','原M1歷史快照：/events.txt（七篇及原時間未改）',''])
    text='\n'.join(lines).encode()
    h=html.escape
    facts=''.join('<article><strong>'+h(p['statement_zh'])+'</strong><p lang="en">'+h(p['supporting_excerpt_en'])+'</p><a href="'+h(p['source_url'],quote=True)+'">BLS 原文 · DIRECTLY_SUPPORTED</a></article>' for p in c['propositions'])
    times=''.join('<tr><th scope="row">'+h(r['role'])+'</th><td>'+h(r['value'])+'</td><td>'+h(r['meaning_zh'])+'</td></tr>' for r in timeline)
    def bullets(xs):return '<ul>'+''.join('<li>'+h(x)+'</li>' for x in xs)+'</ul>'
    page=f'''<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{h(c['title_zh'])} | Macro Radar M2</title><meta name="description" content="BLS CPI 官方命題核對、真實觀測時間與條件式研究預覽；不是交易訊號。"><style>body{{margin:0;background:#f3f5f8;color:#17253a;font:16px/1.7 system-ui,sans-serif}}main{{max-width:1000px;margin:auto;padding:28px 20px}}header,section{{background:#fff;border:1px solid #dae1ea;border-radius:12px;padding:24px;margin:0 0 18px}}h1{{font-size:clamp(26px,4vw,40px);line-height:1.3}}h2{{line-height:1.4}}a{{color:#1759a7;overflow-wrap:anywhere}}a:focus-visible{{outline:3px solid #a34904}}.tag{{font-size:13px;color:#52627d}}.notice{{border-left:4px solid #a56617;padding-left:14px}}article{{padding:16px 0;border-bottom:1px solid #dae1ea}}article strong{{font-size:20px}}article p{{color:#52627d}}code{{overflow-wrap:anywhere}}.table{{overflow-x:auto}}table{{width:100%;border-collapse:collapse;font-size:13px}}td,th{{padding:10px;text-align:left;vertical-align:top;border-bottom:1px solid #dae1ea;overflow-wrap:anywhere}}th{{width:25%}}.formats{{display:flex;flex-wrap:wrap;gap:10px 20px}}@media(max-width:550px){{main{{padding:14px 10px}}header,section{{padding:17px}}table,tbody,tr,th,td{{display:block}}th{{width:auto}}td{{border:0}}tr{{border-bottom:1px solid #ddd}}}}</style></head><body><main>
<header><p class="tag">M2 · SAVED RESEARCH CASE · PREVIEW</p><h1>{h(c['title_zh'])}</h1><p lang="en">{h(c['title_en'])}</p><p class="notice"><strong>四項官方統計命題已核對；政策與市場結果仍未知。</strong><br>2026-09統計，2026-10-14發布日期。不是即時新聞、正式Frozen或交易訊號。</p><p>{h(c['why_it_matters_zh'])}</p><p>As-of UTC：<code>{h(c['as_of'])}</code></p><nav aria-label="案例格式" class="formats"><a href="case.txt">純文字／LLM</a><a href="case.json">JSON</a><a href="asof-examples.json">as-of可得性範例</a><a href="manifest.json">SHA256清單</a><a href="/">原M1快照</a></nav></header>
<section><h2>先分清楚：發現不是核實</h2><p>保存的 BLS CPI Feed 提供發現線索，仍是 UNVERIFIED_NEWS。本輪另外取得 BLS 官方原文，逐項核對統計命題；不是兩家獨立來源交叉證實，也不升級整則新聞或其市場推論。</p><p><a href="{h(doc['source_url'],quote=True)}">BLS USDL-26-1574 官方原文</a> · 原發現觀測：<code>{h(d['retrieved_at'])}</code></p>{facts}</section>
<section><h2>我們何時才知道？</h2><p class="notice">{h(c['time_conflict']['explanation_zh'])}<br><strong>精確發布時間與偵測延遲 UNKNOWN。</strong></p><div class="table"><table><thead><tr><th>時間角色</th><th>原始UTC／日期</th><th>正確解讀</th></tr></thead><tbody>{times}</tbody></table></div><p>Identity：<code>{h(e['event_id'])}</code>；單篇保守article-set，未強制合併其他事件。</p></section>
<section><h2>MacroView PREVIEW：可能如何傳導？</h2><p>以下為條件假設，並非已觀測到的因果。</p>{bullets(v['hypotheses_zh'])}<h2>哪些還不知道？</h2>{bullets(v['unknowns_zh'])}<h2>下一步該看什麼？</h2>{bullets(v['next_evidence_zh'])}</section>
<section><h2>為何能研究、仍不能交易？</h2>{bullets(c['pit_limitations_zh'])}<p>RESEARCH_ONLY · CAUSALITY_NOT_ESTABLISHED<br>Polymarket：UNAVAILABLE · Market reaction：NOT_MEASURED<br>Frozen：UNAVAILABLE_NO_APPROVED_LEDGER</p><p>沒有持久歷史、執行證據、策略與風險驗證，不得進入 Paper／Live。</p></section>
<section><h2>查回來源與保存內容</h2><p>署名來源：U.S. Bureau of Labor Statistics。<a href="{h(c['rights']['policy_url'],quote=True)}">公開使用政策</a>。僅引用機構文字、標題、短節錄與統計，沒有圖片、標誌或第三方內容。繁中翻譯及解讀由 Macro Trading OS / Codex 整理，非官方譯文，只供展示。</p><p>官方回應SHA256：<code>{h(doc['response_sha256'])}</code></p><p>完整保存時間、命題與來源見 <a href="case.json">case.json</a>；可得性範例只是保存收據投影，不是正式PIT服務。M1七篇快照原時間與位元組未變。</p></section></main></body></html>'''.encode()
    out={'index.html':page,'case.json':encoded(data),'case.txt':text,'case.md':text,'asof-examples.json':encoded(examples)}
    out['manifest.json']=encoded({'schema':'M2_CASE_MANIFEST_V1','self_excluded':True,'case_release':c['release'],'files':{n:{'sha256':sha(b),'bytes':len(b)} for n,b in sorted(out.items())}})
    return out

def build(root,output):
    root=Path(root);output=Path(output);pin=json.loads((root/'event_release.json').read_bytes())
    for name,digest in pin['inputs'].items():
        if sha((root/name).read_bytes())!=digest:raise ValueError('PINNED_M2_INPUT_MISMATCH:'+name)
    preserved=json.loads((root/'m1_preservation.json').read_bytes())['files']
    for name,digest in preserved.items():
        if sha((output/name).read_bytes())!=digest:raise ValueError('M1_BYTES_CHANGED:'+name)
    inventory(output/'research')
    case=json.loads((root/'event_case.json').read_bytes());values=render(case)
    dest=output/'research'/SLUG;dest.mkdir(parents=True,exist_ok=True)
    for n,b in values.items():(dest/n).write_bytes(b)
    inventory(output/'research')
    if {p.name for p in dest.iterdir()}!=CASE_FILES:raise ValueError('INCOMPLETE_CASE')
    return values
if __name__=='__main__':
    root=Path(__file__).resolve().parent
    values=build(root,root/'public');print('M2_CASE_BUILD=PASS; files='+str(len(values)))
