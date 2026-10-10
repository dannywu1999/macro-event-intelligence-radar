// Reviewed presentation only. Exact market ID + original question binding.
// Question summaries do not translate or replace the provider resolution rules.
(function(root){'use strict';
const REVIEWED = {
  "2589810": {
    "question": "Will the Fed decrease interest rates by 50+ bps after the October 2026 meeting?",
    "zh": "聯準會（Fed）是否會在 2026 年 10 月會議之後降息至少 50 個基點（50+ bps）？"
  },
  "3029903": {
    "question": "Copper cable hit with Sec. 232 tariffs by December 31, 2026?",
    "zh": "截至 2026 年 12 月 31 日，銅纜是否已被課徵第 232 條（Section 232）關稅？"
  },
  "2126461": {
    "question": "Will Crude Oil reach a new all-time high by December 31?",
    "zh": "截至 12 月 31 日，原油是否會創下新的歷史最高價？"
  },
  "4641065": {
    "question": "US x Iran ceasefire continues through October 31?",
    "zh": "美國與伊朗的停火是否會持續到並涵蓋 10 月 31 日？"
  },
  "2589811": {
    "question": "Will the Fed decrease interest rates by 25 bps after the October 2026 meeting?",
    "zh": "聯準會（Fed）是否會在 2026 年 10 月會議之後降息 25 個基點（25 bps）？"
  },
  "3029904": {
    "question": "Copper cable hit with Sec. 232 tariffs by December 31, 2027?",
    "zh": "截至 2027 年 12 月 31 日，銅纜是否已被課徵第 232 條（Section 232）關稅？"
  },
  "4936098": {
    "question": "Will WTI Crude Oil (WTI) hit (HIGH) $150 in October?",
    "zh": "WTI 原油（WTI）是否會在 10 月觸及 150 美元（HIGH／價格高點）？"
  },
  "4713483": {
    "question": "US x Iran ceasefire continues through November 30?",
    "zh": "美國與伊朗的停火是否會持續到並涵蓋 11 月 30 日？"
  },
  "2589812": {
    "question": "Will there be no change in Fed interest rates after the October 2026 meeting?",
    "zh": "聯準會（Fed）利率是否會在 2026 年 10 月會議之後維持不變？"
  },
  "3840852": {
    "question": "US-Canada diplomatic agreement to lower tariffs by December 31?",
    "zh": "截至 12 月 31 日，美國與加拿大是否會達成降低關稅的外交協議？"
  },
  "4936099": {
    "question": "Will WTI Crude Oil (WTI) hit (HIGH) $140 in October?",
    "zh": "WTI 原油（WTI）是否會在 10 月觸及 140 美元（HIGH／價格高點）？"
  },
  "4713484": {
    "question": "US x Iran ceasefire continues through December 31?",
    "zh": "美國與伊朗的停火是否會持續到並涵蓋 12 月 31 日？"
  },
  "2589813": {
    "question": "Will the Fed increase interest rates by 25 bps after the October 2026 meeting?",
    "zh": "聯準會（Fed）是否會在 2026 年 10 月會議之後升息 25 個基點（25 bps）？"
  },
  "3900266": {
    "question": "US-Canada diplomatic agreement to lower tariffs by October 31?",
    "zh": "截至 10 月 31 日，美國與加拿大是否會達成降低關稅的外交協議？"
  },
  "4936100": {
    "question": "Will WTI Crude Oil (WTI) hit (HIGH) $130 in October?",
    "zh": "WTI 原油（WTI）是否會在 10 月觸及 130 美元（HIGH／價格高點）？"
  },
  "5130977": {
    "question": "US x Iran ceasefire continues through October 7?",
    "zh": "美國與伊朗的停火是否會持續到並涵蓋 10 月 7 日？"
  },
  "2589814": {
    "question": "Will the Fed increase interest rates by 50+ bps after the October 2026 meeting?",
    "zh": "聯準會（Fed）是否會在 2026 年 10 月會議之後升息至少 50 個基點（50+ bps）？"
  },
  "5180567": {
    "question": "US-Canada diplomatic agreement to lower tariffs by November 30?",
    "zh": "截至 11 月 30 日，美國與加拿大是否會達成降低關稅的外交協議？"
  },
  "4936101": {
    "question": "Will WTI Crude Oil (WTI) hit (HIGH) $120 in October?",
    "zh": "WTI 原油（WTI）是否會在 10 月觸及 120 美元（HIGH／價格高點）？"
  },
  "5130978": {
    "question": "US x Iran ceasefire continues through October 15?",
    "zh": "美國與伊朗的停火是否會持續到並涵蓋 10 月 15 日？"
  }
};
const CATEGORIES={MONETARY_POLICY:'貨幣政策',ECONOMY_TRADE:'經濟／貿易',ENERGY:'能源',GEOPOLITICS:'地緣政治'};
const TERMS=[[/\bFed\b/,'聯準會（Fed）'],[/\bWTI\b/,'WTI 原油'],[/\bSection 232\b|\bSec\. 232\b/,'第 232 條（Section 232）'],[/\bceasefire\b/i,'停火'],[/\btariffs\b/i,'關稅']];
// Whole-question templates. Unsupported conditions never match a substring.
const MONTHS={January:1,February:2,March:3,April:4,May:5,June:6,July:7,August:8,September:9,October:10,November:11,December:12};
function dateLabel(month,day,year){const n=MONTHS[month],d=Number(day),y=year?Number(year):2000;if(!n||y<2000||y>2100||d<1||d>new Date(Date.UTC(y,n,0)).getUTCDate())return null;return `${year?year+' 年 ':''}${n} 月 ${d} 日`;}
function template(q){if(typeof q!=='string')return null;let m;
 if(m=/^(US|Israel) x Iran ceasefire continues through ([A-Z][a-z]+) (\d{1,2})(?:, (20\d{2}))?\?$/.exec(q)){const date=dateLabel(m[2],m[3],m[4]);return date?`${m[1]==='US'?'美國':'以色列'}與伊朗的停火是否會持續到並涵蓋 ${date}？`:null;}
 if(m=/^Will the Fed (decrease|increase) interest rates by (25|50\+) bps after the ([A-Z][a-z]+) (20\d{2}) meeting\?$/.exec(q)){const month=MONTHS[m[3]];return month?`聯準會（Fed）是否會在 ${m[4]} 年 ${month} 月會議之後${m[1]==='decrease'?'降息':'升息'}${m[2]==='50+'?'至少 50':' 25'} 個基點（${m[2]} bps）？`:null;}
 if(m=/^Will there be no change in Fed interest rates after the ([A-Z][a-z]+) (20\d{2}) meeting\?$/.exec(q)){const month=MONTHS[m[1]];return month?`聯準會（Fed）利率是否會在 ${m[2]} 年 ${month} 月會議之後維持不變？`:null;}
 if(m=/^US-Canada diplomatic agreement to lower tariffs by ([A-Z][a-z]+) (\d{1,2})(?:, (20\d{2}))?\?$/.exec(q)){const date=dateLabel(m[1],m[2],m[3]);return date?`截至 ${date}，美國與加拿大是否會達成降低關稅的外交協議？`:null;}
 if(m=/^Copper cable hit with Sec\. 232 tariffs by ([A-Z][a-z]+) (\d{1,2}), (20\d{2})\?$/.exec(q)){const date=dateLabel(m[1],m[2],m[3]);return date?`截至 ${date}，銅纜是否已被課徵第 232 條（Section 232）關稅？`:null;}
 if(m=/^Will WTI Crude Oil \(WTI\) hit \(HIGH\) \$(\d{1,4}(?:\.\d{1,2})?) in ([A-Z][a-z]+)\?$/.exec(q)){const month=MONTHS[m[2]];return month&&Number(m[1])>0?`WTI 原油（WTI）是否會在 ${month} 月觸及 ${m[1]} 美元（HIGH／價格高點）？`:null;}
 return null;
}
function project(record,language){
 const original=typeof record.question==='string'?record.question:null;
 if(language!=='zh-TW')return {original,summary:null,mode:'ORIGINAL',terminology:[]};
 const entry=REVIEWED[String(record.market_id)];
 if(entry&&entry.question===original)return {original,summary:entry.zh,mode:'REVIEWED_QUESTION_SUMMARY',terminology:[]};
 const translated=template(original);if(translated)return {original,summary:translated,mode:'VALIDATED_QUESTION_TEMPLATE',terminology:[]};
 const terminology=TERMS.filter(([pattern])=>pattern.test(original||'')).map(([,label])=>label);
 const category=CATEGORIES[record.category];if(category)terminology.unshift(category);
 return {original,summary:null,mode:terminology.length?'TERMINOLOGY_ONLY':'ORIGINAL_FALLBACK',terminology};
}
function outcomeLabel(label,language){return language==='zh-TW'&&label==='Yes'?'是（Yes）':language==='zh-TW'&&label==='No'?'否（No）':label;}
root.RadarMarketTranslation=Object.freeze({project,outcomeLabel});
})(typeof window==='undefined'?globalThis:window);
