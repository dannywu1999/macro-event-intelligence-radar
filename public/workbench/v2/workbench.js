'use strict';
(() => {
  const $ = s => document.querySelector(s);
  const esc = value => String(value ?? 'UNKNOWN').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const link = (url, text) => `<a href="${esc(url)}"${url.startsWith('https://') ? ' target="_blank" rel="noopener noreferrer"' : ''}>${esc(text)}</a>`;
  const badge = (text, type='') => `<span class="badge ${type}">${esc(text)}</span>`;
  let data = null, zone = 'UTC';
  const filters = {query:'',source:'',topic:'',evidence:'',conflict:false};
  function date(raw) {
    if (!raw) return 'UNKNOWN';
    if (!raw.includes('T')) return esc(raw)+' · 日期／期間';
    const d = new Date(raw);
    if (!Number.isFinite(d.getTime())) return 'UNKNOWN';
    if (zone==='UTC') return d.toISOString().slice(0,19).replace('T',' ')+' UTC';
    return new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Taipei',dateStyle:'short',timeStyle:'medium'}).format(d)+' 台灣 UTC+8';
  }
  const stamp = raw => `<time datetime="${esc(raw)}">${date(raw)}</time>`;
  const labels = {ENERGY:'能源',MACRO_CONTEXT:'宏觀脈絡',MACRO_DATA:'經濟數據',TRADE_POLICY:'貿易政策'};
  const cpiArticle = a => a.source_url===data.case.discovery.item.article_reference;
  const supportedCount = () => data.case.propositions.filter(p=>p.support==='DIRECTLY_SUPPORTED').length;
  const publisher = a => a.source.split(' · ')[0]; // Presentation only; raw source/author untouched.
  function metrics() {
    return `<div class="metrics" aria-label="官方統計命題">${data.metrics.map(m => `<div class="metric"><a class="metric-main" href="/workbench/cpi-20261014/#proposition-${esc(m.proposition_id)}"><span>${esc(m.label)}</span><strong>+${esc(m.value_percent)}<span>%</span></strong><small>${esc(m.basis)} · 檢查證據 ↗</small></a><a class="metric-source" href="${esc(m.source_url)}" target="_blank" rel="noopener noreferrer">BLS 原文 ↗</a></div>`).join('')}</div>`;
  }
  function boundaries() {
    return `<aside aria-label="目前研究邊界"><h2>確認數據，保留未知</h2><dl><div><dt>偵測延遲</dt><dd>UNKNOWN</dd></div><div><dt>市場反應</dt><dd>尚未量測</dd></div><div><dt>正式 Frozen</dt><dd>UNAVAILABLE</dd></div></dl></aside>`;
  }
  function supportSummary() {
    const count=data.case.propositions.filter(p=>p.support==='DIRECTLY_SUPPORTED').length;
    return `<div class="pills">${badge(`${count} 項官方統計命題獲直接支持`,'support')}${badge('文章／事件身份：仍待核實')}</div>`;
  }
  function overview() {
    const c=data.case;
    $('#main').innerHTML=`<section aria-labelledby="overview-title"><div class="hero"><div><p class="eyebrow">EVIDENCE BEFORE INTERPRETATION</p><h1 id="overview-title">看清宏觀事件，查回每項證據。</h1><p class="lede muted">從保存的新聞線索，走到官方支持的命題。先區分已知與未知，再形成研究問題。</p>${supportSummary()}<p class="small">精選研究 · ${esc(c.reference_period)} 美國 CPI · 發布日期 ${esc(c.release_date)}（DATE_ONLY）</p></div>${boundaries()}</div>${metrics()}<div class="inline-meta"><span>統計來源：BLS · 數據不是今日更新</span><span>研究整理 as-of：${stamp(c.as_of)}</span></div><div class="action-row"><a class="primary-link" href="/workbench/cpi-20261014/">打開 CPI 證據研究 →</a><a href="/research/m2-cpi-20261014/case.txt">原始案例文字 ↗</a></div><p class="scope-note">官方支持只及四個統計命題，不背書整則文章、政策預測或資產方向。保存文章仍為 UNVERIFIED_NEWS。</p></section>
    <section aria-labelledby="feed-title"><div class="section-head"><h2 id="feed-title">保存的新聞與研究線索</h2><p>${data.articles.length} 篇文章 · ${data.event_candidates.length} 個保守候選，非已核實世界事件</p></div>
    <form id="filters" class="filters" role="search"><label>中英文標題或來源<input id="query" type="search" autocomplete="off" placeholder="例如：通膨、CPI、solar"></label><label>來源<select id="source"><option value="">全部來源</option>${[...new Set(data.articles.map(publisher))].map(s=>`<option>${esc(s)}</option>`).join('')}</select></label><label>宏觀分類<select id="topic"><option value="">全部分類</option>${[...new Set(data.articles.map(a=>a.event_family))].map(t=>`<option value="${esc(t)}">${esc(labels[t]||t)}</option>`).join('')}</select></label><label>命題證據研究<select id="evidence"><option value="">全部研究狀態</option><option value="supported">有官方命題研究連結</option><option value="unlinked">尚無命題研究連結</option></select></label></form>
    <div class="filter-extra"><label><input id="conflict" type="checkbox">僅顯示已記錄時間衝突</label><button id="reset" type="button">清除篩選</button><span>文章身份均為「新聞發現／尚待核實」</span></div><p id="results" role="status" class="small muted"></p><div id="feed" class="feed"></div></section>`;
    for(const key of ['query','source','topic','evidence']) {
      const element=$('#'+key);element.value=filters[key];
      element.addEventListener(key==='query'?'input':'change',()=>{filters[key]=element.value;renderFeed();});
    }
    $('#conflict').checked=filters.conflict;
    $('#conflict').addEventListener('change',()=>{filters.conflict=$('#conflict').checked;renderFeed();});
    $('#filters').addEventListener('submit',e=>e.preventDefault());
    $('#reset').addEventListener('click',()=>{Object.assign(filters,{query:'',source:'',topic:'',evidence:'',conflict:false});for(const id of ['query','source','topic','evidence'])$('#'+id).value='';$('#conflict').checked=false;renderFeed();$('#query').focus();});
    renderFeed();
  }
  function renderFeed() {
    const q=filters.query.trim().toLocaleLowerCase();
    const rows=data.articles.filter(a=>(!q||[a.headline_original,a.headline_zh,a.source].join(' ').toLocaleLowerCase().includes(q))&&(!filters.source||publisher(a)===filters.source)&&(!filters.topic||a.event_family===filters.topic)&&(!filters.evidence||(filters.evidence==='supported')===cpiArticle(a))&&(!filters.conflict||cpiArticle(a)));
    $('#results').textContent=`顯示 ${rows.length} / ${data.articles.length} 篇文章；篩選只影響展示，不變更證據或事件身份。`;
    $('#feed').innerHTML=rows.length?rows.map(a=>{
      const r=data.rights.find(r=>r.rights_id===a.rights_id);
      return `<article class="article-row"><div class="topic small muted">${esc(labels[a.event_family]||a.event_family)}</div><div><h3>${cpiArticle(a)?`<a href="/workbench/cpi-20261014/">${esc(a.headline_zh||a.headline_original)}</a>`:link(a.source_url,a.headline_zh||a.headline_original)}</h3><p class="original" lang="en">${esc(a.headline_original)}</p><p class="source-info">${esc(publisher(a))}${a.author?' · '+esc(a.author):''} · ${link(a.source_url,'原文 ↗')}</p>${badge('新聞發現／尚待核實')}${cpiArticle(a)?' '+badge(`${supportedCount()} 項官方命題研究連結`,'support')+' '+badge('來源時間衝突','warning'):''}
      <details><summary>來源授權與保存狀態</summary><p>原文章狀態：${esc(a.verification_status)}；原 M1 官方證據欄位：${esc(a.official_evidence_status)}。${cpiArticle(a)?'M2 另有命題研究，沒有升級原文章身份。':''}</p><p>${link(r.policy_url,'來源使用政策')}${r.license_url?' · '+link(r.license_url,'CC BY 4.0'):''} · 中文為非官方展示譯文；原始英文與身份保留。</p><p>${esc(r.attribution_requirements)}</p><p>保存記錄：${stamp(a.recorded_at)}</p></details></div><div class="meta">來源自報發布<br>${stamp(a.source_reported_at)}<br><br>本機實際取得<br>${stamp(a.observed_at)}</div></article>`;
    }).join(''):`<div class="empty"><h3>沒有符合這組條件的保存文章</h3><p>這不代表世界沒有事件，也不會啟動新聞抓取。請調整條件或清除篩選。</p></div>`;
  }
  function timeline() {
    const c=data.case;
    const names={SOURCE_REPORTED_PUBLICATION_CONFLICTING:['Feed 自報發布','來源自報，可靠性待釐清',c.discovery.receipt_sha256,c.discovery.item.article_reference],SCHEDULED_EMBARGO_NOT_ACTUAL_PUBLICATION:['文件預定禁發時間','來源文件公告，並非實測上線',c.official_document.response_sha256,c.official_document.source_url],SAVED_NEWS_OBSERVED:['保存的新聞觀測','本機實際取得；非全球 first-seen',c.discovery.receipt_sha256,c.discovery.item.article_reference],SAVED_NEWS_RECORDED:['新聞記錄完成','保存快照記錄時間',c.discovery.receipt_sha256,c.discovery.item.article_reference],OFFICIAL_DOCUMENT_RETRIEVED_IN_M2:['官方原文取得','本輪實際 HTTP 取得',c.official_document.receipt_sha256,c.official_document.source_url],OFFICIAL_DOCUMENT_RECORDED_IN_M2:['官方原文記錄','保存原文收據記錄時間',c.official_document.receipt_sha256,c.official_document.source_url],PROPOSITION_REVIEW_AND_PREVIEW_AS_OF:['命題核對與研究預覽','研究整理建立；不可回填至原文取得時間',data.source_inputs['event_case.json'],'/research/m2-cpi-20261014/case.json']};
    const rows=c.timeline.filter(r=>r.role!=='REFERENCE_PERIOD_DATE_ONLY');
    return `<ol class="timeline">${rows.map((r,i)=>{const n=names[r.role];return `<li class="${i<2?'conflict':''}"><details><summary>${esc(n[0])}${stamp(r.value)}</summary><p>${esc(r.meaning_zh)}</p><p>時間性質：${esc(n[1])}。原始精度／UTC：<code>${esc(r.value)}</code></p><p>${link(n[3],'原始來源／保存案例 ↗')}</p><p>來源／收據 SHA256：<code>${esc(n[2])}</code></p><p class="small">原角色：${esc(r.role)}</p></details></li>`;}).join('')}</ol>
    <details><summary>完整原始時間表與精度</summary><div class="table-wrap"><table><caption>原 M2 時間原值；參考期間不是觀測時間</caption><thead><tr><th scope="col">角色</th><th scope="col">原始值</th><th scope="col">意義</th></tr></thead><tbody>${c.timeline.map(r=>`<tr><th scope="row">${esc(r.role)}</th><td><code>${esc(r.value)}</code></td><td>${esc(r.meaning_zh)}</td></tr>`).join('')}</tbody></table></div></details>`;
  }
  function casePage() {
    const c=data.case,d=c.discovery,doc=c.official_document;
    $('#main').innerHTML=`<section id="overview"><p class="eyebrow">CPI / SAVED EVIDENCE CASE</p><div class="hero"><div><h1>${esc(c.title_zh)}</h1><p class="original" lang="en">${esc(c.title_en)}</p>${supportSummary()}<p class="muted">${esc(c.why_it_matters_zh)}</p></div>${boundaries()}</div>${metrics()}<div class="inline-meta"><span>統計期間：${esc(c.reference_period)}（非觀測時間）</span><span>官方發布日期：${esc(c.release_date)} · DATE_ONLY</span><span>研究 as-of：${stamp(c.as_of)}</span></div><div class="notice"><strong>來源時間衝突：Feed 自報時間早於文件禁發時間</strong><p>${esc(c.time_conflict.explanation_zh)} 不代表已證明提前洩漏、假新聞或系統故障。精確發布分鐘與偵測延遲仍為 UNKNOWN。</p></div>
    <div class="action-row"><button data-copy="markdown" class="primary">複製 Markdown</button><button data-copy="json">複製 JSON</button><button data-copy="citation">複製引用</button><a href="/research/m2-cpi-20261014/case.json">原始案例 JSON ↗</a></div></section>
    <nav class="case-nav" aria-label="研究段落"><a href="#overview">摘要</a><a href="#evidence">命題與證據</a><a href="#timeline">時間軸</a><a href="#unknowns">未知</a><a href="#interpretation">研究解讀</a><a href="#sources">來源檔案</a></nav>
    <section id="evidence" aria-labelledby="evidence-title"><div class="section-head"><h2 id="evidence-title">新聞說了什麼，官方支持什麼？</h2><p>支持範圍逐項判定，不替整則新聞蓋章</p></div><div class="split"><article class="claim"><p class="eyebrow">DISCOVERY / 原始線索</p><h3 lang="en">${esc(d.item.title)}</h3>${badge('新聞發現／尚待核實')}<dl><dt>來源</dt><dd>${esc(d.item.news_source.name)} · ${link(d.item.article_reference,'原文 ↗')}</dd><dt>來源自報發布（有衝突）</dt><dd>${stamp(d.item.reported_at)}</dd><dt>實際新聞取得</dt><dd>${stamp(d.retrieved_at)}</dd><dt>保存記錄</dt><dd>${stamp(d.recorded_at)}</dd></dl><p class="small muted">發現 Feed 與官方原文都來自 BLS，並非兩家獨立來源。文章與事件仍為 UNVERIFIED_NEWS。</p></article><div aria-label="官方命題支持">${c.propositions.map(p=>`<details class="proposition" id="proposition-${esc(p.id)}"><summary>${esc(p.statement_zh)}${badge('官方命題已核實 · DIRECTLY_SUPPORTED','support')}</summary><blockquote lang="en">${esc(p.supporting_excerpt_en)}</blockquote><p>${link(p.source_url,'BLS 官方原文 ↗')} · ${esc(p.document_reference)}</p><p>只支持此統計命題；政策、預期與市場方向未獲背書。</p><p>整理可得時間：${stamp(p.available_at)}</p><p>原文回應 SHA256：<code>${esc(p.response_sha256)}</code></p></details>`).join('')}</div></div></section>
    <section id="timeline" aria-labelledby="timeline-title"><div class="section-head"><h2 id="timeline-title">我們何時才知道？</h2><p>來源時間、觀測、記錄及研究建立分開看</p></div><div class="time-controls"><label for="timezone">顯示時區</label><select id="timezone"><option value="UTC">UTC</option><option value="Asia/Taipei">台灣 · Asia/Taipei（UTC+8）</option></select><span>原始 UTC 原值永遠保留在展開內容</span></div><div id="timeline-body">${timeline()}</div></section>
    <section id="unknowns" class="unknowns"><h2>哪些還不知道？</h2><ul>${c.preview.unknowns_zh.map(x=>`<li>${esc(x)}</li>`).join('')}</ul><details><summary>未被支持的推論：研究邊界示例</summary><p class="small">以下來自原案例的限制清單，並非宣稱觀測到有人發布這些新聞主張，也不是反駁一則虛構報導。</p><ul>${c.unsupported_claims.map(x=>`<li>${esc(x.claim_zh)} — ${esc(x.status)}；值為 ${x.value===null?'null（未知）':esc(x.value)}</li>`).join('')}</ul></details></section>
    <section id="interpretation"><p class="eyebrow">MACROVIEW / RESEARCH PREVIEW</p><h2>把已知事實轉成下一個研究問題</h2><p class="muted">條件傳導假設，非已建立因果，也非交易建議。</p><div class="research-columns"><div><h3>可能的傳導渠道</h3><ul>${c.preview.hypotheses_zh.map(x=>`<li>${esc(x)}</li>`).join('')}</ul></div><div><h3>接下來應查什麼？</h3><ul>${c.preview.next_evidence_zh.map(x=>`<li>${esc(x)}</li>`).join('')}</ul></div></div><p>${badge('研究假設／非正式結論','preview')} ${badge('Paper / Live 未授權')}</p><p class="small muted">沒有核准的持久歷史、Frozen 收據、執行與風險驗證。可研究，不代表可交易。</p></section>
    <section id="sources"><h2>來源與完整保存檔案</h2><div class="source-files">${link(doc.source_url,'BLS 原始統計文件 ↗')}${link(c.rights.policy_url,'BLS 公開使用政策 ↗')}${link('/research/m2-cpi-20261014/case.json','完整原 M2 JSON')}${link('/research/m2-cpi-20261014/case.md','原 M2 Markdown')}${link('/research/m2-cpi-20261014/asof-examples.json','保存收據可得性範例')}${link('/workbench/v2/manifest.json','新版展示 SHA256')}</div><p class="scope-note">原始發布者：${esc(doc.authority_name)}。官方原文於 ${stamp(doc.retrieved_at)} 才由本研究取得；研究解讀於 ${stamp(c.created_at)} 建立。不是歷史發布當下就已知。繁中為非官方展示譯文，英文原文保留。</p><details class="technical"><summary>技術識別、PIT 與進階功能界線</summary><p>Event ID：<code>${esc(c.canonical_event.event_id)}</code></p><p>官方文件收據 SHA256：<code>${esc(doc.receipt_sha256)}</code></p><p>CASE input SHA256：<code>${esc(data.source_inputs['event_case.json'])}</code></p><ul>${c.pit_limitations_zh.map(x=>`<li>${esc(x)}</li>`).join('')}</ul><p>Revision diff：尚無足夠的已保存修訂版本。As-of：僅提供原收據範例，不提供任意歷史日期回放。Causality：NOT_ESTABLISHED。LLM consensus：未實作、無同意分數。</p></details></section>`;
    $('#timezone').value=zone;
    $('#timezone').addEventListener('change',()=>{zone=$('#timezone').value;$('#timeline-body').innerHTML=timeline();});
    for (const button of document.querySelectorAll('[data-copy]'))button.addEventListener('click',()=>copy(button.dataset.copy));
    openHash();
  }
  function exportJSON() {
    const c=data.case;
    return {schema:'MACRO_RADAR_RESEARCH_EXPORT_V2',presentation_schema:data.schema,case_release:c.release,title_zh:c.title_zh,title_en:c.title_en,original_publisher:c.official_document.authority_name,source_url:c.official_document.source_url,source_release_date:c.release_date,publication_precision:c.official_document.publication_precision,exact_publication_at:c.official_document.published_at,reference_period:c.reference_period,research_as_of:c.as_of,research_created_at:c.created_at,discovery:c.discovery,article_verification_status:c.discovery.item.verification_status,event_verification_status:c.canonical_event.verification_status,propositions:c.propositions,timeline:c.timeline,time_conflict:c.time_conflict,detection_latency:c.detection_latency,market_reaction:c.market_reaction,polymarket:c.polymarket,causality:c.causality,preview:c.preview,frozen_macroview_status:c.frozen_macroview_status,durable_first_seen_status:c.durable_first_seen_status,rights:c.rights,source_input_sha256:data.source_inputs['event_case.json'],scope:'SAVED_RESEARCH_PREVIEW_NOT_LIVE_NOT_FULL_PIT_NOT_TRADING'};
  }
  function citation() {
    const c=data.case;
    return `${c.official_document.authority_name}. ${c.title_en}. Release date: ${c.release_date} (DATE_ONLY; exact publication UNKNOWN). ${c.official_document.source_url}\nMacro Radar research interpretation: ${c.created_at}; official document retrieved: ${c.official_document.retrieved_at}. ${supportedCount()} directly supported propositions only; article/event remain UNVERIFIED_NEWS. Historical saved research; not live, Frozen PIT or a trading signal.`;
  }
  function markdown() {
    const c=data.case;
    return `# ${c.title_zh}\n\n${c.title_en}\n\n${citation()}\n\n## 官方直接支持的命題\n${c.propositions.map(p=>`- ${p.statement_zh}\n  Source: ${p.source_url}\n  Support: ${p.support}; available_at: ${p.available_at}`).join('\n')}\n\n## 時間角色\n${c.timeline.map(r=>`- ${r.role}: ${r.value} — ${r.meaning_zh}`).join('\n')}\n\n## Material unknowns\n${c.preview.unknowns_zh.map(x=>'- '+x).join('\n')}\n\nDETECTION_LATENCY=UNKNOWN\nMarket reaction=NOT_MEASURED\nPolymarket=UNAVAILABLE\nCausality=NOT_ESTABLISHED\nFrozen=UNAVAILABLE_NO_APPROVED_LEDGER\nArticle/Event=UNVERIFIED_NEWS\nScope=SAVED_RESEARCH_PREVIEW_NOT_LIVE_NOT_TRADING\n\n繁中為非官方展示譯文；原文與命題身份不變。\n`;
  }
  async function copy(kind) {
    const value=kind==='json'?JSON.stringify(exportJSON(),null,2):kind==='citation'?citation():markdown();
    try {await navigator.clipboard.writeText(value);$('#feedback').textContent='已複製；包含來源、時間與研究限制。';}
    catch (_) {$('#copy-text').value=value;$('#copy-fallback').showModal();$('#copy-text').focus();$('#copy-text').select();}
  }
  function openHash() {
    const id=decodeURIComponent(location.hash.slice(1));
    if(!id)return;
    const node=document.getElementById(id);
    if(node?.classList.contains('proposition')) {node.open=true;node.scrollIntoView();}
  }
  addEventListener('hashchange',openHash);
  async function load() {
    const button=$('#reload');button.disabled=true;
    try {
      const response=await fetch('/workbench/v2/data.json',{cache:'no-store',credentials:'omit'});
      if(!response.ok)throw new Error('DATA_UNAVAILABLE');
      const next=await response.json();
      if(next.schema!=='MACRO_RADAR_WORKBENCH_V2'||next.live_feed!==false||next.trading_signal!==false||next.case.canonical_event.verification_status!=='UNVERIFIED_NEWS'||next.case.detection_latency!=='UNKNOWN')throw new Error('INVALID_SNAPSHOT');
      data=next;$('#load-status').hidden=true;
      if(document.body.dataset.page==='case')casePage();else overview();
    } catch (_) {
      const status=$('#load-status');status.hidden=false;status.textContent=data?'保存資料重新讀取失敗；保留上一份已載入資料，內容可能過期。這不代表沒有事件。':'無法讀取保存研究資料。請重試，或閱讀下方原始文字檔；不會啟動採集。';
      if(!data)$('#main').innerHTML='<section class="empty"><h1>研究資料暫不可用</h1><p>這是讀取失敗，不是沒有事件。</p><a href="/research/m2-cpi-20261014/case.txt">直接閱讀保存的 CPI 文字</a> · <a href="/events.txt">七篇原始快照</a></section>';
    } finally {button.disabled=false;}
  }
  $('#reload').addEventListener('click',load);
  load();
})();
