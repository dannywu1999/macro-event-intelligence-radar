"""M3.5 versioned presentation, derived only from pinned M1/M2 public data."""
from pathlib import Path
import hashlib,json,re
import build_gateway as g
import build_event_case as case

ROOT=Path(__file__).resolve().parent
FILES=frozenset(('index.html','cpi-20261014/index.html','v2/workbench.css','v2/workbench.js','v2/data.json','v2/manifest.json'))
def sha(raw):return hashlib.sha256(raw).hexdigest()
def enc(obj):return g.encoded(obj)
def inventory(path):
    path=Path(path)
    if not path.exists():return
    if path.is_symlink():raise ValueError('WORKBENCH_SYMLINK')
    for p in path.rglob('*'):
        if p.is_symlink():raise ValueError('WORKBENCH_SYMLINK')
        rel=p.relative_to(path).as_posix()
        if p.is_dir() and rel not in ('v2','cpi-20261014'):raise ValueError('UNKNOWN_WORKBENCH_DIRECTORY')
        if p.is_file() and rel not in FILES:raise ValueError('UNKNOWN_WORKBENCH_ASSET')
def archive(output):
    manifest=json.loads((ROOT/'m35_archive_preservation.json').read_bytes())
    if len(manifest['files'])!=17:raise ValueError('ARCHIVE_INVENTORY')
    for n,h in manifest['files'].items():
        if sha((Path(output)/n).read_bytes())!=h:raise ValueError('ARCHIVE_CHANGED:'+n)
    return manifest
def derive(root=ROOT):
    root=Path(root)
    pin=json.loads((root/'event_release.json').read_bytes())
    for n,h in pin['inputs'].items():
        if sha((root/n).read_bytes())!=h:raise ValueError('M2_PIN')
    source=json.loads((root/'source_snapshot.json').read_bytes());release=json.loads((root/'release.json').read_bytes())
    if sha((root/'source_snapshot.json').read_bytes())!=release['source_sha256']:raise ValueError('M1_PIN')
    g.validate(source,release);c=case.validate(json.loads((root/'event_case.json').read_bytes()))
    published=json.loads(case.render(c)['case.json'])
    labels={'headline_month':('整體 CPI-U','月比 · 季節調整'),'headline_year':('整體 CPI-U','年比 · 未季節調整'),'core_month':('核心 CPI','月比 · 季節調整'),'gasoline':('汽油指數','月比 · 季節調整')}
    metrics=[]
    for p in c['propositions']:
        match=re.search(r'(\d+(?:\.\d+)?) percent',p['supporting_excerpt_en'])
        if not match or not re.search(r'\b(?:increased|rose)\b',p['supporting_excerpt_en']):raise ValueError('UNSUPPORTED_METRIC_EXTRACTION')
        label,basis=labels[p['id']]
        metrics.append({'proposition_id':p['id'],'label':label,'basis':basis,'value_percent':match[1],'direction':'INCREASE','source_url':p['source_url']})
    examples=json.loads(case.render(c)['asof-examples.json'])
    return {'schema':'MACRO_RADAR_WORKBENCH_V2','scope':'VERSIONED_PRESENTATION_OF_PINNED_SAVED_PUBLIC_DATA','source_inputs':{'source_snapshot.json':sha((root/'source_snapshot.json').read_bytes()),'event_case.json':sha((root/'event_case.json').read_bytes())},'case':published,'metrics':metrics,'articles':source['snapshot']['articles'],'rights':source['rights'],'event_candidates':source['snapshot']['event_candidates'],'checkpoints':examples,'live_feed':False,'trading_signal':False,'original_article_status_unchanged':True}
def page(kind):
    title='美國 CPI｜證據研究工作台' if kind=='case' else 'Macro Radar｜研究工作台'
    return f'''<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title>
<meta name="description" content="從保存新聞到官方命題：CPI數值、來源證據、觀測時間與研究限制，一頁查清楚。非即時、非交易訊號。">
<meta http-equiv="Content-Security-Policy" content="default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'">
<link rel="icon" href="data:,"><link rel="stylesheet" href="/workbench/v2/workbench.css"><script src="/workbench/v2/workbench.js" defer></script></head>
<body data-page="{kind}"><a class="skip" href="#main">跳至研究內容</a>
<header class="masthead"><a class="brand" href="/workbench/">Macro Radar<span>RESEARCH WORKBENCH / V2</span></a><nav aria-label="主導覽"><a href="/workbench/">研究總覽</a><a href="/workbench/cpi-20261014/">CPI 證據案例</a><a href="/">M1 原始快照 ↗</a></nav></header>
<div class="scopebar"><span>保存研究 · 非即時</span><span>研究預覽，非交易訊號</span><button id="reload" type="button">重新讀取保存資料</button></div>
<div id="load-status" role="alert" hidden></div><p id="feedback" role="status" aria-live="polite"></p>
<main id="main" tabindex="-1"><p class="loading">正在讀取保存研究資料…</p></main>
<noscript><section class="noscript"><h1>{title}</h1><p>互動篩選與匯出需要 JavaScript。仍可直接閱讀完整的原始公開研究，沒有即時資料或交易服務。</p><a href="/research/m2-cpi-20261014/case.txt">CPI 完整文字與四項官方命題</a> · <a href="/events.txt">七篇保存文章</a></section></noscript>
<dialog id="copy-fallback"><form method="dialog"><h2>手動複製研究內容</h2><p>瀏覽器未允許直接寫入剪貼簿。內容未傳送到任何外部服務。</p><label for="copy-text">選取以下內容後複製</label><textarea id="copy-text" readonly rows="14"></textarea><button>完成／關閉</button></form></dialog>
<footer><p>News 發現線索 · Official 核實個別命題 · MacroView 條件假設</p><p>沒有正式 PIT ledger／Frozen 收據；因果與交易準備度未建立。繁中為非官方展示譯文，英文證據保留。</p><a href="/workbench/v2/manifest.json">V2 SHA256</a> · <a href="/research/m2-cpi-20261014/">原 M2 案例</a> · <a href="/source-rights.json">來源使用依據</a></footer></body></html>'''.encode()
def build(root=ROOT,output=None):
    root=Path(root);output=Path(output) if output else root/'public'
    archive(output);inventory(output/'workbench')
    data=derive(root)
    assets={'index.html':page('overview'),'cpi-20261014/index.html':page('case'),'v2/data.json':enc(data)}
    for n in ('workbench.css','workbench.js'):assets['v2/'+n]=(root/'workbench_src'/n).read_bytes()
    assets['v2/manifest.json']=enc({'schema':'M35_PRESENTATION_MANIFEST_V2','self_excluded':True,'scope':data['scope'],'source_inputs':data['source_inputs'],'archives_sha256':sha((root/'m35_archive_preservation.json').read_bytes()),'files':{n:{'sha256':sha(raw),'bytes':len(raw)} for n,raw in sorted(assets.items())}})
    assert set(assets)==FILES
    for n,raw in assets.items():
        path=output/'workbench'/n;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
    inventory(output/'workbench');archive(output)
    return assets
if __name__=='__main__':print('M35_WORKBENCH_BUILD=PASS; files='+str(len(build())))
