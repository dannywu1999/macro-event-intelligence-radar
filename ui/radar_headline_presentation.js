/* Translation is presentation only. This module does not change evidence, ranking or identity. */
(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;if(root)root.RadarHeadlinePresentation=api})(typeof window==='object'?window:null,function(){
 'use strict';
 function article(a){const r=a?.headline_translation;return ((r?.status==='CURATED_CANDIDATE'&&r.adapter_version==='CURATED_ZH_TW_V1')||(r?.status==='REVIEWED_LOCAL_CANDIDATE'&&r.adapter_version==='LOCAL_TRANSLATION_PIPELINE_V1'&&r.local_only===true&&typeof r.reviewer==='string'&&r.reviewer.trim()&&typeof r.reviewed_at==='string'&&typeof r.result_sha256==='string'&&/^[a-f0-9]{64}$/.test(r.result_sha256)))&&r.presentation_only===true&&r.target_locale==='zh-TW'&&r.source_url===a.article_reference&&r.source_title===a.title&&typeof r.translated_title==='string'&&r.translated_title.trim()?r:null}
 function event(e,v){for(const a of v?.items||[]){if((e.article_references||[]).includes(a.article_reference)&&a.title===e.event_title){const r=article(a);if(r)return r}}return null}
 function searchMap(v){return Object.fromEntries((v?.events||[]).map(e=>[e.event_id,event(e,v)?.translated_title||'']).filter(([,title])=>title))}
 return Object.freeze({article,event,searchMap});
});
