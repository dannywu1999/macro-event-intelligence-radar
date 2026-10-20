"""M3.6 static event presentation of pinned public metadata; no acquisition."""
from pathlib import Path
import copy,html,json,re
from urllib.parse import urlsplit
import build_gateway as g
import build_workbench as w
ROOT=Path(__file__).resolve().parent
SCHEMA='MACRO_RADAR_GLOBAL_EVENT_PROJECTION_V1'
CATEGORIES={
 'central_banks':('央行與貨幣政策','Central Banks & Monetary Policy'),
 'geopolitics':('地緣政治','Geopolitics'),
 'trade':('貿易與關稅','Trade & Tariffs'),
 'energy':('能源與商品','Energy & Commodities'),
 'economic_data':('經濟數據','Economic Data'),
 'expectations':('市場預期','Market Expectations'),
 'context':('宏觀脈絡','Macro Context')}
FAMILY={'ENERGY':'energy','MACRO_CONTEXT':'context','MACRO_DATA':'economic_data','TRADE_POLICY':'trade'}
BASE_FILES=frozenset(('index.html','events.json','events.txt','v1/radar.css','v1/radar.js','v1/manifest.json'))
def enc(x):return g.encoded(x)
def h(x):return html.escape('UNKNOWN' if x is None else str(x),quote=True)
def date(x):return 'UNKNOWN' if x is None else str(x)
def path(e):return 'events/'+e['candidate_id']+'/'
def files_for(ids):
 return BASE_FILES|frozenset('events/'+i+'/'+n for i in ids for n in ('index.html','event.json','event.md','citation.txt'))
def source_ids(root=ROOT):
 return [x['event_id'] for x in json.loads((Path(root)/'source_snapshot.json').read_bytes())['snapshot']['event_candidates']]
def inventory(folder,root=ROOT):
 folder=Path(folder)
 if not folder.exists():return
 allowed=files_for(source_ids(root));dirs={str(Path(n).parent).replace('\\','/') for n in allowed}
 dirs|={'events','v1'}
 if folder.is_symlink():raise ValueError('RADAR_SYMLINK')
 for p in folder.rglob('*'):
  if p.is_symlink():raise ValueError('RADAR_SYMLINK')
  rel=p.relative_to(folder).as_posix()
  if p.is_file() and rel not in allowed:raise ValueError('UNREVIEWED_RADAR_FILE:'+rel)
  if p.is_dir() and rel not in dirs:raise ValueError('UNREVIEWED_RADAR_DIRECTORY:'+rel)
def archive(output,root=ROOT):
 pin=json.loads((Path(root)/'m36_archive_preservation.json').read_bytes())
 if len(pin['files'])!=23:raise ValueError('ARCHIVE_COUNT')
 for n,digest in pin['files'].items():
  if g.digest((Path(output)/n).read_bytes())!=digest:raise ValueError('ARCHIVE_CHANGED:'+n)
 return pin
def derive(root=ROOT):
 root=Path(root);saved=w.derive(root);source=json.loads((root/'source_snapshot.json').read_bytes())
 c=saved['case'];s=source['snapshot'];by_url={a['source_url']:a for a in s['articles']}
 if len(by_url)!=7 or len(s['event_candidates'])!=7:raise ValueError('SNAPSHOT_COUNT')
 ids=[e['event_id'] for e in s['event_candidates']]
 if len(set(ids))!=7 or any(not re.fullmatch(r'canonical-event-v0-[0-9a-f]{64}',i) for i in ids):raise ValueError('CANDIDATE_ID')
 cpi_matches=[e for e in s['event_candidates'] if e['event_id']==c['canonical_event']['event_id']]
 if len(cpi_matches)!=1 or cpi_matches[0]['article_references']!=c['canonical_event']['article_references']:raise ValueError('AMBIGUOUS_CPI_JOIN')
 rows=[]
 for e in s['event_candidates']:
  if e['article_count']!=1 or len(e['article_references'])!=1:raise ValueError('UNREVIEWED_GROUPING')
  a=by_url[e['article_references'][0]]
  if e['event_title']!=a['headline_original']:raise ValueError('TITLE_JOIN')
  if a['event_family'] not in FAMILY:raise ValueError('UNREVIEWED_FAMILY')
  is_cpi=e['event_id']==c['canonical_event']['event_id']
  if is_cpi and (a['source_url']!=c['discovery']['item']['article_reference'] or a['headline_original']!=c['title_en']):raise ValueError('CPI_REFERENCE_JOIN')
  row={'candidate_id':e['event_id'],'candidate_identity_type':'CONSERVATIVE_SINGLE_ARTICLE_SET_NOT_PROVEN_DISTINCT_WORLD_EVENT',
   'original_title':a['headline_original'],'translated_title':a['headline_zh'],
   'translation_status':a['translation_status'],'translation_presentation_only':True,
   'category':FAMILY[a['event_family']],'original_event_family':a['event_family'],
   'article_references':copy.deepcopy(e['article_references']),'articles':[copy.deepcopy(a)],
   'source_names':[a['source']],'source_urls':[a['source_url']],
   'source_published_at':a['source_reported_at'],'publication_precision':'SOURCE_REPORTED_TIMESTAMP_NOT_INDEPENDENTLY_PROVEN',
   'first_observed_scope':'SAVED_LOCAL_OBSERVATION_NOT_GLOBAL_FIRST_SEEN',
   'observed_at':a['observed_at'],'recorded_at':a['recorded_at'],
   'article_verification_status':e['verification_status'],'original_official_evidence_status':e['official_evidence_status'],
   'official_proposition_status':'FACT_PROPOSITIONS_LINKED' if is_cpi else 'NO_OFFICIAL_EVIDENCE_LINKED',
   'supported_proposition_count':4 if is_cpi else 0,'rights_status':'PUBLIC_ELIGIBLE_METADATA_ONLY',
   'rights':[copy.deepcopy(r) for r in source['rights'] if r['source_url']==a['source_url']],
   'research_status':'SAVED_RESEARCH_PREVIEW' if is_cpi else 'METADATA_ONLY_PENDING',
   'macroview_status':'PREVIEW' if is_cpi else 'UNAVAILABLE',
   'macroview':copy.deepcopy(c['preview']) if is_cpi else None,
   'live_feed':False,'trading_signal':False,'snapshot_as_of':c['as_of'],
   'event_occurred_at':None,'importance_assessment':None,'market_expectations':{'status':'UNAVAILABLE','value':None},
   'market_reaction':{'status':'NOT_MEASURED','value':None},'detection_latency':'UNKNOWN',
   'causality':'NOT_ESTABLISHED','frozen_macroview_status':'UNAVAILABLE_NO_APPROVED_LEDGER',
   'evidence_links':copy.deepcopy(c['official_evidence']) if is_cpi else [],
   'propositions':copy.deepcopy(c['propositions']) if is_cpi else [],
   'metrics':copy.deepcopy(saved['metrics']) if is_cpi else [],
   'time_conflict':copy.deepcopy(c['time_conflict']) if is_cpi else None,
   'official_document':copy.deepcopy(c['official_document']) if is_cpi else None}
  if not row['rights']:raise ValueError('MISSING_RIGHTS')
  row['timeline']=copy.deepcopy(c['timeline']) if is_cpi else [
   {'role':'SOURCE_REPORTED_PUBLICATION','value':a['source_reported_at'],'meaning_zh':'來源自報發布；不是本系統取得時間。'},
   {'role':'SAVED_LOCAL_OBSERVATION','value':a['observed_at'],'meaning_zh':'保存的本機實際取得；不是全球首次觀測。'},
   {'role':'SAVED_METADATA_RECORDING','value':a['recorded_at'],'meaning_zh':'保存 metadata 記錄；不等於正式 PIT ledger。'}]
  rows.append(row)
 # Transparent chronological ordering only; no materiality or causal inference.
 rows.sort(key=lambda r:(g.utc(r['observed_at']),g.utc(r['source_published_at']),r['candidate_id']),reverse=True)
 categories=[{'id':k,'label_zh':v[0],'label_en':v[1],'candidate_count':sum(r['category']==k for r in rows)} for k,v in CATEGORIES.items()]
 return {'schema':SCHEMA,'scope':'SAVED_PUBLIC_METADATA_AND_SEPARATELY_REVIEWED_CPI_PROPOSITIONS',
  'live_feed':False,'trading_signal':False,'snapshot_as_of':c['as_of'],
  'snapshot_as_of_meaning':'Existing M2 research cutoff; not current clock, source release time, or global PIT completeness.',
  'latest_saved_observation_at':max(a['observed_at'] for a in s['articles']),
  'ordering':'SAVED_OBSERVATION_DESC_THEN_SOURCE_PUBLICATION_DESC_THEN_CANDIDATE_ID',
  'article_identity':'EXACT_SOURCE_URL_NO_NEW_ARTICLE_IDS',
  'counts':{'articles':7,'article_set_candidates':7,'candidates_with_official_propositions':1,
   'candidates_without_official_propositions':6,'unverified_article_set_candidates':7,'empty_product_categories':sum(c['candidate_count']==0 for c in categories)},
  'taxonomy_mapping':FAMILY,'categories':categories,'events':rows,
  'source_inputs':saved['source_inputs'],'boundaries':['FIRST_SEEN_NOT_PROVEN','NO_APPROVED_PIT_LEDGER','NO_FROZEN_RECEIPT','NO_VALIDATED_MATERIALITY_RANKING','NO_COMPREHENSIVE_GLOBAL_COVERAGE'],
  'source_rights_url':'/source-rights.json'}
def time_html(value):
 return 'UNKNOWN' if value is None else '<time datetime="'+h(value)+'">'+h(value)+'</time>'
def bullets(xs):return '<ul>'+''.join('<li>'+h(x)+'</li>' for x in xs)+'</ul>'
def rights_html(e):
 return ''.join('<p>'+h(r['source'])+' · 作者：'+h(r['author'] or None)+' · <a href="'+h(r['policy_url'])+'">使用政策</a>'+(' · <a href="'+h(r['license_url'])+'">CC BY 4.0</a>' if r['license_url'] else '')+'<br>'+h(r['translation_responsibility'])+'</p>' for r in e['rights'])
def card(e):
 # JSON search key is attribute data only, escaped; identity never derives from translation.
 search=' '.join([e['original_title'],e['translated_title'] or '',*e['source_names']])
 support='有命題研究' if e['propositions'] else '待命題核實'
 return f'''<article class="event" data-event data-category="{h(e['category'])}" data-source="{h(e['articles'][0]['source_id'])}" data-official="{'linked' if e['propositions'] else 'pending'}" data-status="UNVERIFIED_NEWS" data-search="{h(search)}" data-observed="{h(e['observed_at'])}" data-published="{h(e['source_published_at'])}" data-identity="{h(e['candidate_id'])}">
<div class="event-top"><span class="topic">{h(CATEGORIES[e['category']][0])}</span><span class="state">{support} · 文章待核實</span></div>
<h2><a class="detail-link" href="/radar/{path(e)}">{h(e['translated_title'] or e['original_title'])}</a></h2>
<p class="original" lang="en">{h(e['original_title'])}</p>
<p class="source">{h(e['source_names'][0])} · <a href="{h(e['source_urls'][0])}">原文 ↗</a></p>
<dl class="clocks"><div><dt>來源自報發布 UTC</dt><dd>{time_html(e['source_published_at'])}</dd></div><div><dt>保存觀測 UTC</dt><dd>{time_html(e['observed_at'])}</dd></div></dl>
<p class="card-note">{'4 個統計命題另有官方支持；不升級整篇文章。' if e['propositions'] else '單篇保守候選；尚未連結官方命題核實證據。'}</p>
<a class="read" href="/radar/{path(e)}">檢查事件線索與證據 →</a></article>'''
def shell(title,body,route):
 base=json.loads((ROOT/'release.json').read_bytes())['canonical_base_url']
 return f'''<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{h(title)}｜Macro Radar</title><meta name="description" content="全球宏觀事件研究入口：保存新聞、來源證據、觀測時間與未知。非即時、非交易訊號。">
<meta http-equiv="Content-Security-Policy" content="default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'none'; img-src 'self' data:; object-src 'none'; base-uri 'none'">
<link rel="canonical" href="{h(base+'/radar/'+route)}"><link rel="icon" href="data:,"><link rel="stylesheet" href="/radar/v1/radar.css"><script src="/radar/v1/radar.js" defer></script></head>
<body><a class="skip" href="#main">跳至研究內容</a><header class="masthead"><a class="brand" href="/radar/">Macro Radar<span>GLOBAL MACRO EVENT INTELLIGENCE</span></a><nav aria-label="主導覽"><a href="/radar/">事件 Radar</a><a href="/workbench/">研究工作台</a><a href="/radar/events.txt">LLM 純文字</a></nav></header>
<div class="scope"><span>保存公開快照 · 非即時</span><span>研究預覽 · 非交易訊號</span></div>
<main id="main" tabindex="-1">{body}</main>
<footer><p>News 發現線索 · Official 核實個別命題 · Polymarket 只代表市場預期 · MacroView 條件假設</p><p>繁中為非官方展示譯文；原始英文與來源保留。無正式 PIT ledger／Frozen 收據，不能進入 Paper／Live。</p><a href="/radar/events.json">事件 JSON</a> · <a href="/radar/v1/manifest.json">版本與 SHA256</a> · <a href="/source-rights.json">來源權利</a> · <a href="/">M1 原始檔案</a></footer></body></html>'''.encode()
def homepage(d):
 categories=''.join('<a class="category" data-category-link="'+h(c['id'])+'" href="?category='+h(c['id'])+'#discovery"><span>'+h(c['label_zh'])+'</span><small lang="en">'+h(c['label_en'])+'</small><strong>'+str(c['candidate_count'])+'</strong></a>' for c in d['categories'])
 options=''.join('<option value="'+h(c['id'])+'">'+h(c['label_zh'])+'（'+str(c['candidate_count'])+'）</option>' for c in d['categories'])
 sourceopts=''.join('<option value="'+h(k)+'">'+h(label)+'</option>' for k,label in (('eia','EIA'),('360info','360info'),('bls_cpi_official','BLS CPI')))
 empty=''.join('<li>'+h(c['label_zh'])+'：目前公開快照無此類資料。</li>' for c in d['categories'] if not c['candidate_count'])
 body=f'''<section class="hero"><div><p class="eyebrow">GLOBAL EVENT RADAR / V1</p><h1>先看事件，再查證據。</h1><p class="intro">追蹤全球宏觀事件，區分新聞線索、官方事實、市場預期與研究假設。</p><p class="muted">目前僅含 7 篇保存文章與 7 個保守文章集合候選，不代表完整全球覆蓋，也不是剛偵測的新事件。</p></div><aside><p class="eyebrow">SNAPSHOT SCOPE</p><p>最後保存觀測 UTC<br>{time_html(d['latest_saved_observation_at'])}</p><p>研究整理截止 UTC<br>{time_html(d['snapshot_as_of'])}</p><a href="/radar/events.txt">不需 JavaScript 的研究文字 ↗</a></aside></section>
<section class="stats" aria-label="保存研究狀態"><div><strong>7</strong><span>保存公開文章</span></div><div><strong>7</strong><span>文章集合候選 · 未核實</span></div><div><strong>1</strong><span>候選有官方命題研究</span></div><div><strong>6</strong><span>候選待命題核實</span></div></section>
<details class="category-panel" open><summary>按宏觀主題調查 · 3 類主題目前無資料</summary><nav class="categories" aria-label="宏觀主題">{categories}</nav></details>
<section id="discovery" tabindex="-1"><div class="section-head"><div><p class="eyebrow">SAVED DISCOVERY</p><h2>值得進一步調查的線索</h2><p>按保存觀測時間新到舊排列；同時刻依來源發布排序。不是重要性或市場影響評分。</p></div><a href="/radar/events.json">取得同份資料 JSON ↗</a></div>
<details class="filter-panel" open><summary>搜尋與篩選 · 中文／英文、來源、命題研究</summary><form id="filters" class="filters" role="search" hidden><label>搜尋中文／英文／來源<input id="query" name="q" type="search" placeholder="輸入主題、標題或來源"></label><label>主題<select id="category" name="category"><option value="">全部主題</option>{options}</select></label><label>來源<select id="source" name="source"><option value="">全部來源</option>{sourceopts}</select></label><label>官方命題研究<select id="official" name="official"><option value="">全部</option><option value="linked">有命題連結</option><option value="pending">尚待命題核實</option></select></label><label>文章核實狀態<select id="verification" name="verification"><option value="">全部（7 篇皆待核實）</option><option value="UNVERIFIED_NEWS">待核實新聞</option></select></label><label>排序<select id="order" name="order"><option value="observed">保存觀測：新到舊</option><option value="published">來源發布：新到舊</option></select></label><button type="reset">清除篩選</button></form></details>
<noscript><p>以下完整列出 7 個候選。互動篩選需 JavaScript；主題分類、原文與事件詳情均可直接閱讀。</p></noscript>
<p id="result-count" role="status" aria-live="polite">顯示 7 / 7 個保存候選；不是 7 個已核實世界事件。</p><p id="empty" class="empty" hidden>目前公開快照無此類資料，或沒有符合篩選的候選。</p><div class="event-grid" id="events">{''.join(card(e) for e in d['events'])}</div></section>
<details class="limitations"><summary>資料範圍與目前缺口</summary><p>這是有限保存快照，不是24/7採集。七個單篇集合不自動等於七個不同真實世界事件；所有文章仍待核實。</p><ul>{empty}</ul><p>兩篇 MACRO_CONTEXT 保留為「宏觀脈絡」，未因標題相似而併入其他事件。市場預期與反應尚無授權資料；不生成方向、因果或交易評分。</p></details>'''
 return shell('全球宏觀事件 Radar',body,'')
def event_detail(e):
 cpi=bool(e['propositions']);title=e['translated_title'] or e['original_title']
 if cpi:
  metrics='<div class="metrics">'+''.join('<a href="#prop-'+h(m['proposition_id'])+'"><span>'+h(m['label'])+'</span><strong>+'+h(m['value_percent'])+'%</strong><small>'+h(m['basis'])+'</small></a>' for m in e['metrics'])+'</div>'
  facts=''.join('<article id="prop-'+h(p['id'])+'"><h3>'+h(p['statement_zh'])+'</h3><p class="state">DIRECTLY_SUPPORTED · 僅此命題</p><blockquote lang="en">'+h(p['supporting_excerpt_en'])+'</blockquote><a href="'+h(p['source_url'])+'">BLS 官方原文 ↗</a><p>命題核對可得時間 UTC：'+time_html(p['available_at'])+'</p></article>' for p in e['propositions'])
  official='<p>另行取得 BLS 文件，只支持四個統計命題；原始文章與候選仍為 UNVERIFIED_NEWS。</p>'+metrics+facts+'<p>官方精確發布時間 UNKNOWN；DATE_ONLY：'+h(e['official_document']['release_date'])+'</p>'
  v=e['macroview']
  macro='<p class="state">PREVIEW · 研究解讀，不是 Frozen</p><p>解讀可得時間 UTC：'+time_html(v['available_at'])+'</p><h3>條件傳導假設，非已觀測因果</h3>'+bullets(v['hypotheses_zh'])+'<h3>尚未解決</h3>'+bullets(v['unknowns_zh'])+'<h3>下一步證據</h3>'+bullets(v['next_evidence_zh'])+'<a href="/workbench/cpi-20261014/">原 CPI 專題工作台 ↗</a>'
 else:
  official='<p class="empty-state">尚未連結官方命題核實證據</p><p>即使發布者是官方機構，也不能據此升級整篇文章或候選。此處只有公開 metadata；沒有另行命題核對。</p>'
  macro='<p class="state">UNAVAILABLE</p><p>尚無通過證據門檻的 MacroView 研究解讀。</p><p>不從標題生成資產方向或跨事件因果。下一步需另行核對對應原始文件、具體命題與取得時間。</p>'
 conflict='<p class="conflict">'+h(e['time_conflict']['explanation_zh'])+'</p>' if e['time_conflict'] else ''
 timeline=''.join('<li><details><summary><span>'+h(r['meaning_zh'])+'</span><strong>'+time_html(r['value'])+'</strong></summary><p>時間角色：<code>'+h(r['role'])+'</code></p><p>原始值：'+h(r['value'])+'；缺少精度時不推定分鐘。</p></details></li>' for r in e['timeline'])
 cid=e['candidate_id']
 body=f'''<a class="back" data-back href="/radar/">← 回到事件 Radar</a><header class="event-hero"><p class="eyebrow">{h(CATEGORIES[e['category']][0])} / SAVED EVENT CANDIDATE</p><h1>{h(title)}</h1><p class="original" lang="en">{h(e['original_title'])}</p><p class="state">UNVERIFIED_NEWS · 單篇保守文章集合</p><p>這是保存的調查線索，不是新偵測事件。{'可查四項官方命題，政策與市場結果仍未知。' if cpi else '可檢查原始來源與時間；尚無官方命題核實及研究解讀。'}</p><details><summary>候選身分與研究範圍</summary><p><code>{h(cid)}</code></p><p>文章身分 = 原始 URL；候選身分 = 既有 article-set ID；兩者不等於已證明的不同世界事件。</p><p>研究整理截止 UTC：{time_html(e['snapshot_as_of'])}。事件發生時間 UNKNOWN；重要性未評估。</p></details></header>
<nav class="section-nav" aria-label="事件研究章節"><a href="#discovery">發現</a><a href="#official">官方證據</a><a href="#timeline">時間線</a><a href="#expectations">市場預期</a><a href="#macroview">MacroView</a><a href="#export">來源與匯出</a></nav>
<section class="panel" id="discovery"><p class="eyebrow">01 / DISCOVERY</p><h2>報導了什麼？</h2><p lang="en">{h(e['original_title'])}</p><a href="{h(e['source_urls'][0])}">{h(e['source_names'][0])} · 原文 ↗</a><dl class="detail-clocks"><dt>來源自報發布 UTC</dt><dd>{time_html(e['source_published_at'])}</dd><dt>時間精度／可靠性</dt><dd>來源自報 timestamp，未獨立證明實際上線時刻。</dd><dt>本機保存觀測 UTC</dt><dd>{time_html(e['observed_at'])}</dd><dt>Metadata 記錄 UTC</dt><dd>{time_html(e['recorded_at'])}</dd><dt>首次觀測範圍</dt><dd>SAVED_LOCAL_OBSERVATION · FIRST_SEEN_NOT_PROVEN</dd></dl><p>中文僅展示譯文，不參與原始文章身分、去重或 PIT 判定。</p></section>
<section class="panel" id="official"><p class="eyebrow">02 / OFFICIAL EVIDENCE</p><h2>哪些命題已核對？</h2>{official}</section>
<section class="panel" id="timeline"><p class="eyebrow">03 / EVIDENCE TIMELINE</p><h2>何時發生、何時才取得？</h2><p>以下原始 UTC／日期依時間角色呈現；不是正式歷史回放。</p>{conflict}<ol class="timeline">{timeline}</ol><p>偵測延遲 UNKNOWN；不把歷史發現間隔當成突發新聞偵測效能。</p></section>
<section class="panel" id="expectations"><p class="eyebrow">04 / MARKET EXPECTATIONS</p><h2>市場預期</h2><p class="state">UNAVAILABLE</p><p>此候選沒有授權的 Polymarket 機率或共識資料。預期感測器不能取代事實權威；市場反應 NOT_MEASURED。</p></section>
<section class="panel" id="macroview"><p class="eyebrow">05 / MACROVIEW</p><h2>能形成什麼研究判斷？</h2>{macro}<details><summary>為何仍不能交易？</summary><p>沒有正式 PIT ledger／Frozen 收據、完整策略、執行與風險驗證。CAUSALITY_NOT_ESTABLISHED；Paper／Live 未授權。</p></details></section>
<section class="panel" id="export"><p class="eyebrow">06 / SOURCE &amp; EXPORT</p><h2>查回來源，帶走研究</h2>{rights_html(e)}<div class="exports"><a href="event.md" download>下載 Markdown</a><a href="event.json" download>下載 JSON</a><a href="citation.txt" download>下載引用</a><button type="button" id="copy-citation">複製引用</button></div><p id="copy-status" role="status" aria-live="polite"></p><label id="citation-label" for="citation">引用內容（原生可選取複製）</label><textarea id="citation" readonly rows="6">{h(citation(e))}</textarea><p>匯出保留 UNKNOWN／null、原始身分與時間。全文及資料庫收據未發布；JSON 為展示投影，不是正式 PIT。</p></section>'''
 return shell(title,body,path(e))
def citation(e):
 return '\n'.join([e['source_names'][0]+': '+e['original_title'],e['source_urls'][0],
  'Source-reported publication UTC: '+date(e['source_published_at']),
  'Saved local observation UTC: '+date(e['observed_at']),'Recorded UTC: '+date(e['recorded_at']),
  'Research snapshot as-of UTC: '+date(e['snapshot_as_of']),
  'Candidate: '+e['candidate_id'],
  'UNVERIFIED_NEWS; '+e['official_proposition_status']+' (proposition-scoped only)',
  'FIRST_SEEN_NOT_PROVEN; no approved PIT/Frozen; live_feed=false; trading_signal=false',
  *[r['source']+'; Author: '+date(r['author'] or None)+'; '+r['policy_url']+'; '+date(r['license_url']) for r in e['rights']]])+'\n'
def narrative(e):
 lines=['# '+(e['translated_title'] or e['original_title']),e['original_title'],'',citation(e),
  'Candidate identity: '+e['candidate_identity_type'],'Original event family: '+e['original_event_family'],
  'Research status: '+e['research_status'],'MacroView: '+e['macroview_status'],
  'Event occurred at: UNKNOWN','Importance: UNKNOWN','Detection latency: UNKNOWN',
  'Market expectations: UNAVAILABLE','Market reaction: NOT_MEASURED','Causality: NOT_ESTABLISHED',
  '## Official propositions (not whole-article verification)']
 for p in e['propositions']:
  lines.extend([p['statement_zh'],p['supporting_excerpt_en'],p['source_url'],'Available at UTC: '+p['available_at']])
 if not e['propositions']:lines.append('尚未連結官方命題核實證據')
 lines.append('## Timeline')
 lines.extend(r['role']+': '+date(r['value'])+' — '+r['meaning_zh'] for r in e['timeline'])
 if e['time_conflict']:lines.append(e['time_conflict']['explanation_zh'])
 lines.append('## MacroView')
 if e['macroview']:
  lines.extend(['PREVIEW as-of '+e['macroview']['available_at'],'Conditional hypotheses, not observed causality',*e['macroview']['hypotheses_zh'],*e['macroview']['unknowns_zh'],*e['macroview']['next_evidence_zh']])
 else:lines.append('UNAVAILABLE — 尚無通過證據門檻的 MacroView 研究解讀。')
 lines.extend(['Unofficial Traditional Chinese presentation adaptation; original English preserved.','No trade authorization. No global first-seen or historical completeness claim.'])
 return '\n\n'.join(lines)+'\n'
def render(d,root=ROOT):
 assets={'index.html':homepage(d),'events.json':enc(d),
  'events.txt':('Macro Radar — Global Event Radar\n'+d['schema']+'\nSaved scope; NOT live, NOT comprehensive global coverage; 7 articles / 7 conservative single-article-set candidates.\nResearch snapshot as-of UTC: '+d['snapshot_as_of']+'\n'+'\n'.join(narrative(e) for e in d['events'])).encode()}
 for e in d['events']:
  prefix=path(e)
  assets[prefix+'index.html']=event_detail(e)
  assets[prefix+'event.json']=enc({'schema':SCHEMA,'source_inputs':d['source_inputs'],'event':e})
  assets[prefix+'event.md']=narrative(e).encode()
  assets[prefix+'citation.txt']=citation(e).encode()
 for n in ('radar.css','radar.js'):assets['v1/'+n]=(Path(root)/'radar_src'/n).read_bytes()
 assets['v1/manifest.json']=enc({'schema':'M36_RADAR_ASSET_MANIFEST_V1','self_excluded':True,
  'source_inputs':d['source_inputs'],'archive_pin_sha256':g.digest((Path(root)/'m36_archive_preservation.json').read_bytes()),
  'files':{n:{'sha256':g.digest(b),'bytes':len(b)} for n,b in sorted(assets.items())}})
 if set(assets)!=files_for([e['candidate_id'] for e in d['events']]):raise ValueError('RADAR_INVENTORY')
 return assets
def build(root=ROOT,output=None):
 root=Path(root);output=Path(output) if output else root/'public'
 archive(output,root);inventory(output/'radar',root)
 d=derive(root);assets=render(d,root)
 for name,raw in assets.items():
  p=output/'radar'/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
 inventory(output/'radar',root);archive(output,root)
 return assets
if __name__=='__main__':print('M36_GLOBAL_RADAR_BUILD=PASS; files='+str(len(build())))

