/* Pure presentation selectors. No network, persistence, recording or authority. */
(function (root, factory) {
  'use strict';
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) root.RadarProductWorkbench = api;
})(typeof window === 'object' ? window : null, function () {
  'use strict';
  const object = value => value && typeof value === 'object' && !Array.isArray(value) ? value : {};
  const rows = value => Array.isArray(value) ? value.filter(x => x && typeof x === 'object' && !Array.isArray(x)) : [];
  const text = value => typeof value === 'string' ? value : '';
  const normalized = value => text(value).normalize('NFKC').toLowerCase();
  const count = value => Number.isSafeInteger(value) && value >= 0 ? value : null;
  function option(value, fallback) {
    if (value == null) return fallback;
    if (typeof value !== 'string') throw new TypeError('FILTER_TEXT_REQUIRED');
    return value;
  }
  function choice(value, allowed) {
    const result = option(value, 'ALL');
    if (!allowed.includes(result)) throw new TypeError('UNKNOWN_FILTER');
    return result;
  }
  function officialFor(event, view) {
    const e = object(event), ids = new Set(Array.isArray(e.official_evidence_ids) ? e.official_evidence_ids : []);
    if (!text(e.event_id)) return [];
    const seen = new Set();
    return rows(object(view).official_evidence).filter(record => {
      const id = text(record.official_evidence_id);
      if (!id || !ids.has(id) || seen.has(id) || record.canonical_event_id !== e.event_id ||
          record.evidence_status !== 'OFFICIAL_CONFIRMED' || record.authority_role !== 'FACT_AUTHORITY' || !text(record.fact_proposition).trim()) return false;
      seen.add(id); return true;
    });
  }
  function sourceNames(view) {
    const v = object(view), names = new Set();
    for (const event of rows(v.events)) for (const name of Array.isArray(event.source_names) ? event.source_names : []) if (text(name)) names.add(name);
    for (const article of rows(v.items)) if (text(object(article.news_source).name)) names.add(article.news_source.name);
    return Array.from(names).sort((a, b) => a.localeCompare(b));
  }
  function summarize(view, options) {
    const v = object(view), o = object(options), capture = object(v.news_capture_status), freshness = object(v.news_freshness);
    const events = rows(v.events), items = rows(v.items), validView = view && typeof view === 'object' && !Array.isArray(view);
    const recorded = items.filter(article => {
      const evidence = object(article.prospective_evidence);
      return ['RECORDED_LOCAL_PILOT', 'RECORDED_EVIDENCE_LEDGER', 'RECORDED_DURABLE_CAPTURE', 'CAPTURED_EARLIER_VERSION'].includes(evidence.status) &&
        !!text(evidence.receipt_id) && !!text(evidence.recorded_at);
    }).length;
    const sources = Object.values(object(v.discovery_sources)).map(object), ingestion = object(v.live_ingestion);
    const requestUpdated = [ingestion, ...sources].some(s => s.enabled === true && s.status === 'LIVE' && !!text(s.last_success_at));
    const snapshot = o.demoMode === true || [ingestion, ...sources].some(s => ['SAVED_SNAPSHOT', 'SNAPSHOT_FALLBACK', 'LAST_VALID_FALLBACK'].includes(s.status));
    let dataMode = 'NOT_RECORDED';
    if (!validView || v.status === 'UNAVAILABLE' || v.status === 'ERROR') dataMode = 'UNAVAILABLE';
    else if (requestUpdated) dataMode = 'REQUEST_UPDATED';
    else if (snapshot) dataMode = 'SNAPSHOT';
    else if (recorded > 0) dataMode = 'SNAPSHOT';
    if (v.data_scope === 'SYNTHETIC_TEST_FIXTURE') dataMode = 'SYNTHETIC_FIXTURE';
    // A recorded local receipt is not proof of continuous capture or live data.
    const linked = new Set(events.flatMap(event => officialFor(event, v).map(record => record.official_evidence_id)));
    const cases = rows(object(v.market_research_library).cases).filter(c => c.status === 'AVAILABLE' && c.receipt && typeof c.receipt === 'object');
    return {
      dataMode, captureStatus: text(capture.status) || 'UNKNOWN',
      captureEnabled: typeof capture.enabled === 'boolean' ? capture.enabled : null,
      latestObserved: text(v.latest_observed_data_at) || null,
      recent24: count(freshness.last_24h_article_count), recent48: count(freshness.last_48h_article_count),
      storedEvents: events.length, eventCount: events.length, countScope: 'LOADED_RESPONSE_ONLY_NOT_STORAGE_TOTAL',
      linkedOfficialCount: linked.size, historicalCaseCount: cases.length,
      recordedEvidenceCount: recorded, firstSeenStatus: 'FIRST_SEEN_NOT_PROVEN',
      productionAuthority: 'UNKNOWN_NOT_QUERIED'
    };
  }
  function filterEvents(view, options) {
    const v = object(view), o = object(options), query = normalized(option(o.query, '').trim()), source = option(o.source, 'ALL');
    const evidence = choice(o.evidence, ['ALL', 'OFFICIAL', 'NEWS_ONLY']), titles = object(o.translatedTitles);
    return rows(v.events).filter(event => {
      const names = Array.isArray(event.source_names) ? event.source_names.filter(name => typeof name === 'string') : [];
      if (source !== 'ALL' && !names.includes(source)) return false;
      const official = officialFor(event, v).length > 0;
      if ((evidence === 'OFFICIAL' && !official) || (evidence === 'NEWS_ONLY' && official)) return false;
      const refs = new Set(event.article_references || []);
      const articles = rows(v.items).filter(a => refs.has(a.article_reference));
      return !query || normalized([text(event.event_id), text(event.event_title), text(titles[event.event_id]), ...names,
        ...articles.map(a => text(a.title)), ...officialFor(event,v).map(f => text(f.fact_proposition))].join(' ')).includes(query);
    });
  }
  function filterNews(view, options) {
    const v = object(view), o = object(options), query = normalized(option(o.query, '').trim()), source = option(o.source, 'ALL');
    const window = choice(o.window, ['ALL', '24H', '48H', 'OLDER']), freshness = object(v.news_freshness);
    const buckets = object(freshness.article_recency), published = object(freshness.published_at), titles = object(o.translatedTitles);
    return rows(v.items).filter(article => {
      const name = text(object(article.news_source).name), bucket = buckets[article.article_reference];
      if (source !== 'ALL' && name !== source) return false;
      if ((window === '24H' && bucket !== 'LAST_24H') || (window === '48H' && !['LAST_24H', 'LAST_48H'].includes(bucket)) || (window === 'OLDER' && bucket !== 'OLDER')) return false;
      return !query || normalized([text(article.title), text(titles[article.article_reference]), name].join(' ')).includes(query);
    }).sort((a, b) => text(published[b.article_reference]).localeCompare(text(published[a.article_reference])));
  }
  function readiness(event, view) {
    const e = object(event), v = object(view);
    const preview = rows(v.macroview_previews).some(p => p.canonical_event_id === e.event_id && !!text(e.event_id) && p.preview_only === true && p.persisted === false);
    return {
      status: 'RESEARCH_ONLY', officialCount: officialFor(e, v).length, previewAvailable: preview,
      marketRealityStatus: text(object(e.market_reality).snapshot_status) || 'UNAVAILABLE',
      missing: ['STRATEGY_NOT_VALIDATED', 'EXECUTION_NOT_AUTHORIZED', 'RISK_APPROVAL_NOT_RECORDED'],
      tradingAuthority: 'NONE_IN_THIS_INTERFACE', productionAuthority: 'UNKNOWN_NOT_QUERIED',
      causality: 'NOT_ESTABLISHED'
    };
  }
  // System observation clocks must be instants. DATE_ONLY remains source data,
  // never midnight system knowledge. Preserve microseconds for as-of checks.
  function instant(value) {
    if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})$/.test(value)) return null;
    const [year,month,day,hour,minute,second]=value.slice(0,19).split(/[-T:]/).map(Number);
    if(month<1||month>12||day<1||day>new Date(Date.UTC(year,month,0)).getUTCDate()||hour>23||minute>59||second>59)return null;
    const n=Date.parse(value);if(!Number.isFinite(n))return null;
    const fraction=(value.match(/\.(\d+)/)?.[1]||'').padEnd(6,'0');
    const micros=n*1000+Number(fraction.slice(3));return Number.isSafeInteger(micros)?micros:null;
  }
  function firstSeen(article, asOf) {
    const a=object(article),d=object(a.detection_evidence),receipt=d.source_receipt_identity||object(a.prospective_evidence).receipt_id;
    if(d.first_observed_proven!==true||!text(receipt)||!d.first_observed_at)return {status:'FIRST_SEEN_NOT_PROVEN',at:null};
    const first=instant(d.first_observed_at),retrieved=d.retrieved_at?instant(d.retrieved_at):first;
    const recordedValue=d.knowledge_recorded_at||d.recorded_at||d.first_recorded_at;
    const recorded=recordedValue?instant(recordedValue):retrieved,limit=asOf?instant(asOf):null;
    if(first===null||retrieved===null||recorded===null||first>retrieved||retrieved>recorded||(asOf&&(limit===null||recorded>limit)))return {status:'CLOCK_ORDER_INVALID',at:null};
    return {status:'PROVEN',at:d.first_observed_at};
  }
  function stable(value){return JSON.stringify(value,(_,v)=>v&&typeof v==='object'&&!Array.isArray(v)?Object.fromEntries(Object.keys(v).sort().map(k=>[k,v[k]])):v);}
  function unique(input,key) {
    if(!Array.isArray(input))throw Error('INVALID_DATA_RELATIONSHIP');const found=new Map();
    for(const row of input){if(!row||typeof row!=='object'||!text(row[key]))throw Error('INVALID_DATA_RELATIONSHIP');const old=found.get(row[key]);if(old&&stable(old)!==stable(row))throw Error('CONFLICTING_RECORD_ID');found.set(row[key],row);}
    return Array.from(found.values());
  }
  function validateRadar(input) {
    const v=object(input);if(v.canonical_event_contract!=='CANONICAL_EVENT_V0')throw Error('INVALID_RESPONSE');
    const items=unique(v.items,'article_reference'),events=unique(v.events,'event_id'),official=unique(v.official_evidence||[],'official_evidence_id'),previews=unique(v.macroview_previews||[],'macroview_id');
    const byArticle=new Map(items.map(a=>[a.article_reference,a])),byEvent=new Map(events.map(e=>[e.event_id,e])),byFact=new Map(official.map(f=>[f.official_evidence_id,f]));
    for(const event of events){for(const ref of event.article_references||[])if(!byArticle.has(ref))throw Error('INVALID_DATA_RELATIONSHIP');for(const id of event.official_evidence_ids||[]){const fact=byFact.get(id);if(!fact||fact.canonical_event_id!==event.event_id||fact.authority_role!=='FACT_AUTHORITY'||fact.evidence_status!=='OFFICIAL_CONFIRMED')throw Error('INVALID_DATA_RELATIONSHIP');}}
    for(const preview of previews){const event=byEvent.get(preview.canonical_event_id);if(!event||preview.contract_version!=='MACROVIEW_PREVIEW_V0'||preview.preview_only!==true||preview.persisted!==false)throw Error('INVALID_MACROVIEW_RELATIONSHIP');for(const ref of preview.news_article_references||[])if(!(event.article_references||[]).includes(ref))throw Error('INVALID_MACROVIEW_RELATIONSHIP');for(const id of preview.official_evidence_ids||[])if(!(event.official_evidence_ids||[]).includes(id))throw Error('INVALID_MACROVIEW_RELATIONSHIP');for(const fact of rows(object(preview.snapshot).official_evidence)){const current=byFact.get(fact.official_evidence_id);if(!current||fact.canonical_event_id!==event.event_id||fact.authority_role!=='FACT_AUTHORITY'||fact.fact_proposition!==current.fact_proposition||!(preview.official_evidence_ids||[]).includes(fact.official_evidence_id))throw Error('INVALID_MACROVIEW_RELATIONSHIP');}for(const news of rows(object(preview.snapshot).news)){const current=byArticle.get(news.article_reference);if(!current||current.title!==news.title||!(event.article_references||[]).includes(news.article_reference))throw Error('INVALID_MACROVIEW_RELATIONSHIP');}}
    return {...v,items,events,official_evidence:official,macroview_previews:previews,integration_duplicate_count:v.items.length+v.events.length+(v.official_evidence||[]).length+(v.macroview_previews||[]).length-items.length-events.length-official.length-previews.length};
  }
  function validateAsOf(input,eventId,asOf,mode='replay') {
    const v=object(input),limit=instant(asOf);
    if(limit===null||instant(v.as_of)!==limit||v.canonical_event_id!==eventId)throw Error('INVALID_ASOF_IDENTITY');
    const result={...v};const before=time=>{const n=instant(time);if(n===null||n>limit)throw Error('INVALID_EVIDENCE_CLOCK');};
    if(mode==='research'){
      if(v.contract!=='NEWS_PROSPECTIVE_V47'||!['AVAILABLE','NO_OBSERVATIONS','PARTIAL_OBSERVATIONS'].includes(v.status))throw Error('INVALID_RESEARCH_RESPONSE');
      result.news=unique(v.news||[],'article_reference');
      for(const article of result.news)if(firstSeen(article,asOf).status==='CLOCK_ORDER_INVALID')throw Error('INVALID_EVIDENCE_CLOCK');
      result.evidence_versions=unique(v.evidence_versions||[],'observation_id');for(const row of result.evidence_versions)before(row.recorded_at);
      result.official_proposition_observations=unique(v.official_proposition_observations||[],'observation_id');
      result.source_states=unique(v.source_states||[],'observation_id');for(const row of result.source_states)before(row.observed_at);
      const facts=unique(v.official_propositions||[],'official_evidence_id');
      for(const row of result.official_proposition_observations){before(row.recorded_at);const p=object(row.payload);if(p.canonical_event_id!==eventId||p.authority_role!=='FACT_AUTHORITY'||p.evidence_status!=='OFFICIAL_CONFIRMED'||!facts.some(f=>f.official_evidence_id===p.official_evidence_id&&stable(f)===stable(p)))throw Error('INVALID_DATA_RELATIONSHIP');}
      if(facts.length!==result.official_proposition_observations.length)throw Error('INVALID_DATA_RELATIONSHIP');
      const p=v.macroview_preview;if(p&&(p.canonical_event_id!==eventId||p.preview_only!==true||p.persisted!==false||p.contract_version!=='MACROVIEW_PREVIEW_V0'||(p.official_evidence_ids||[]).some(id=>!facts.some(f=>f.official_evidence_id===id))||(p.news_article_references||[]).some(ref=>!result.news.some(n=>n.article_reference===ref))))throw Error('INVALID_MACROVIEW_RELATIONSHIP');
      result.market_expectation_observations=unique(v.market_expectation_observations||[],'observation_id');for(const row of result.market_expectation_observations){before(row.recorded_at);const m=object(row.payload);if(m.canonical_event_id!==eventId||m.authority_role!=='EXPECTATION_SENSOR'||m.link_status!=='LINKED'||!(p?.market_expectation_ids||[]).includes(m.expectation_id))throw Error('INVALID_DATA_RELATIONSHIP');if(m.observed_at)before(m.observed_at);}
      if(p)validateRadar({canonical_event_contract:'CANONICAL_EVENT_V0',items:result.news,events:[{event_id:eventId,article_references:p.news_article_references,official_evidence_ids:p.official_evidence_ids}],official_evidence:facts,macroview_previews:[p]});
      if(v.local_frozen_candidates!=null){if(!Array.isArray(v.local_frozen_candidates)||v.local_frozen_candidates.length>20)throw Error('INVALID_LOCAL_FREEZE_CANDIDATE');for(const candidate of v.local_frozen_candidates){const r=object(candidate.receipt),snapshot=object(candidate.snapshot);if(v.research_scope!=='SYNTHETIC_LOCAL_RESEARCH_LAB_ONLY'||candidate.state!=='SYNTHETIC_FROZEN_CANDIDATE'||r.scope!==v.research_scope||r.contract!=='LOCAL_FREEZE_RECEIPT_CANDIDATE_S3'||r.contract_status!=='UNAPPROVED_CANDIDATE'||r.synthetic!==true||r.production_authorized!==false||r.ledger_id!==v.research_ledger_id||r.canonical_event_id!==eventId||snapshot.canonical_event_id!==eventId||r.macroview_id!==snapshot.macroview_id||r.verification_status!=='LOCAL_PERSISTENCE_HASHES_VERIFIED'||!/^local-freeze-receipt-s3-[a-f0-9]{64}$/.test(r.receipt_id||'')||!/^[a-f0-9]{64}$/.test(r.snapshot_sha256||'')||r.snapshot_sha256!==object(snapshot.provenance).snapshot_sha256)throw Error('INVALID_LOCAL_FREEZE_CANDIDATE');before(r.created_at);before(r.evidence_as_of);if(instant(r.created_at)<instant(r.evidence_as_of)||instant(snapshot.frozen_at)!==instant(r.evidence_as_of))throw Error('INVALID_EVIDENCE_CLOCK');}}
      if(v.status==='NO_OBSERVATIONS'&&(result.news.length||facts.length||p))throw Error('INVALID_RESEARCH_RESPONSE');
    }else{
      if(v.contract_version!=='POINT_IN_TIME_REPLAY_V0')throw Error('INVALID_REPLAY_RESPONSE');
      for(const key of ['news_observations','official_evidence_observations','market_expectation_observations','context_observations','market_reality_observations']){result[key]=unique(v[key]||[],'observation_id');for(const row of result[key]){before(row.observed_at);if(row.canonical_event_id!==eventId)throw Error('INVALID_DATA_RELATIONSHIP');}}
      const p=v.reconstructed_macroview;if(p&&(p.canonical_event_id!==eventId||p.reconstructed!==true||p.persisted!==false||instant(p.frozen_at)!==limit))throw Error('INVALID_MACROVIEW_RELATIONSHIP');
    }
    return result;
  }
  function researchGate(result){
    const v=object(result),p=object(v.macroview_preview),eid=text(v.canonical_event_id);
    const facts=rows(v.official_propositions).filter(f=>f.canonical_event_id===eid&&f.authority_role==='FACT_AUTHORITY'&&f.evidence_status==='OFFICIAL_CONFIRMED');
    const markets=rows(v.market_expectation_observations).filter(r=>r.payload?.canonical_event_id===eid&&r.payload?.authority_role==='EXPECTATION_SENSOR'&&r.payload?.link_status==='LINKED'&&(p.market_expectation_ids||[]).includes(r.payload.expectation_id));
    const missing=['STRATEGY_VALIDATION_UNAVAILABLE','EXECUTION_EVIDENCE_UNAVAILABLE','RISK_APPROVAL_UNAVAILABLE'];
    if(!facts.length)missing.unshift('OFFICIAL_PROPOSITION_MISSING');
    if(facts.some(f=>!f.published_at))missing.push('OFFICIAL_PUBLICATION_TIME_UNKNOWN');
    if(rows(v.news).some(a=>firstSeen(a,v.as_of).status!=='PROVEN'))missing.push('FIRST_SEEN_NOT_PROVEN');
    return {state:'RESEARCH_ONLY',knowledge_as_of:v.as_of||null,scope:v.research_scope||v.scope||'UNKNOWN',news_count:rows(v.news).length,facts,expectations:markets,preview_status:v.macroview_preview?'PREVIEW':'UNAVAILABLE',missing,trade_authorization:false,paper_authorization:false,production_frozen_available:false};
  }
  function compareResearch(a,b){
    if(!a||!b||a.canonical_event_id!==b.canonical_event_id||!a.research_ledger_id||a.research_ledger_id!==b.research_ledger_id)return {status:'COMPARISON_UNAVAILABLE_LEDGER_IDENTITY'};
    if(instant(a.as_of)===instant(b.as_of))return {status:'SAME_ASOF'};
    const [earlier,later]=instant(a.as_of)<instant(b.as_of)?[a,b]:[b,a],old=new Map(rows(earlier.news).map(n=>[n.article_reference,n])),facts=new Set(rows(earlier.official_propositions).map(f=>f.official_evidence_id));
    return {status:'AVAILABLE',earlier_as_of:earlier.as_of,later_as_of:later.as_of,ledger_id:a.research_ledger_id,
      added_news:rows(later.news).filter(n=>!old.has(n.article_reference)),
      revisions:rows(later.news).filter(n=>old.has(n.article_reference)&&stable({title:n.title,reported_at:n.reported_at})!==stable({title:old.get(n.article_reference).title,reported_at:old.get(n.article_reference).reported_at})).map(n=>({article_reference:n.article_reference,before_title:old.get(n.article_reference).title,after_title:n.title})),
      official_added:rows(later.official_propositions).filter(f=>!facts.has(f.official_evidence_id))};
  }
  return Object.freeze({summarize, filterEvents, filterNews, readiness, sourceNames, firstSeen, validateRadar, validateAsOf, instant, researchGate, compareResearch});
});
