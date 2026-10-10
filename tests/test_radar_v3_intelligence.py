"""V3 presentation executes actual served JS; synthetic inputs, no external calls."""
import copy, json, re, subprocess, unittest
from pathlib import Path
import test_bilingual_visual_ui as bilingual
NODE=bilingual.NODE
ROOT=Path(__file__).resolve().parents[1]

def project(records, language='zh-TW'):
    code="const fs=require('fs'),vm=require('vm');const p=JSON.parse(fs.readFileSync(0,'utf8'));let c={window:{}};vm.createContext(c);vm.runInContext(fs.readFileSync(p.asset,'utf8'),c);console.log(JSON.stringify(p.records.map(r=>({projection:c.window.RadarMarketTranslation.project(r,p.lang),outcomes:(r.outcomes||[]).map(o=>c.window.RadarMarketTranslation.outcomeLabel(o,p.lang))}))));"
    packet={'asset':str(ROOT/'ui/radar_market_translations.js'),'records':records,'lang':language}
    return json.loads(subprocess.run([NODE,'-e',code],input=json.dumps(packet),text=True,encoding='utf-8',capture_output=True,check=True,timeout=10).stdout)

def reviewed():
    text=(ROOT/'ui/radar_market_translations.js').read_text(encoding='utf-8')
    return json.loads(text.split('const REVIEWED = ',1)[1].split(';\nconst CATEGORIES=',1)[0])

class MarketTranslationTests(unittest.TestCase):
    def test_exact_twenty_reviewed_questions(self):
        r=reviewed();self.assertEqual(len(r),20)
        records=[dict(market_id=k,question=v['question'],outcomes=['Yes','No']) for k,v in r.items()]
        before=copy.deepcopy(records);result=project(records)
        self.assertEqual(records,before)
        self.assertTrue(all(x['projection']['mode']=='REVIEWED_QUESTION_SUMMARY' for x in result))
        self.assertTrue(all(x['outcomes']==['是（Yes）','否（No）'] for x in result))
    def test_numeric_thresholds_preserved_all_questions(self):
        for k,v in reviewed().items():
            with self.subTest(market=k):
                for number in re.findall(r'\d+',v['question']):self.assertIn(number,v['zh'])
    def test_date_and_deadline_relations(self):
        r=reviewed()
        for k in ('2589810','2589811','2589812','2589813','2589814'):
            self.assertIn('2026 年 10 月會議之後',r[k]['zh'])
        for k,date in [('3029903','2026 年 12 月 31 日'),('3029904','2027 年 12 月 31 日'),('3840852','12 月 31 日'),('3900266','10 月 31 日'),('5180567','11 月 30 日')]:
            self.assertIn('截至 '+date,r[k]['zh'])
        for k,date in [('4641065','10 月 31 日'),('4713483','11 月 30 日'),('4713484','12 月 31 日'),('5130977','10 月 7 日'),('5130978','10 月 15 日')]:
            self.assertIn('持續到並涵蓋 '+date,r[k]['zh'])
    def test_threshold_negation_high_and_legal_section(self):
        r=reviewed()
        for k in ('2589810','2589814'):self.assertIn('至少 50 個基點（50+ bps）',r[k]['zh'])
        self.assertIn('維持不變',r['2589812']['zh'])
        self.assertIn('降息 25 個基點',r['2589811']['zh']);self.assertIn('升息 25 個基點',r['2589813']['zh'])
        self.assertIn('新的歷史最高價',r['2126461']['zh'])
        self.assertIn('第 232 條',r['3029903']['zh'])
        for k in ('4936098','4936099','4936100','4936101'):self.assertIn('HIGH',r[k]['zh'])
    def test_no_inferred_year_for_undated_questions(self):
        for v in reviewed().values():
            if not re.search(r'202[67]',v['question']):self.assertNotRegex(v['zh'],r'202[67]')
    def test_wrong_identity_or_changed_question_invalidates_summary(self):
        q=reviewed()['2589810']['question']
        records=[{'market_id':'other','question':q},{'market_id':'2589810','question':q.replace('50+','50')},{'market_id':'2589810','question':q+' extra condition'}]
        result=project(records)
        self.assertEqual(result[0]['projection']['mode'],'VALIDATED_QUESTION_TEMPLATE')
        for x in result[1:]:self.assertIsNone(x['projection']['summary'])
        self.assertTrue(all(x['projection']['mode']!='REVIEWED_QUESTION_SUMMARY' for x in result))
    def test_unknown_multioutcome_preserves_original_outcome_identity(self):
        r={'market_id':'unknown','question':'Candidate A wins before 17:00?','outcomes':['A','NO','Yes, before Friday',None]}
        x=project([r])[0];self.assertEqual(x['projection']['mode'],'ORIGINAL_FALLBACK');self.assertEqual(x['projection']['original'],r['question']);self.assertEqual(x['outcomes'],r['outcomes'])
    def test_partial_terminology_never_full_proposition(self):
        x=project([{'market_id':'unknown','question':'Will the Fed increase by more than 75 bps before June?','category':'MONETARY_POLICY'}])[0]['projection']
        self.assertEqual(x['mode'],'TERMINOLOGY_ONLY');self.assertIsNone(x['summary']);self.assertIn('聯準會（Fed）',x['terminology'])
    def test_english_remains_original(self):
        r=[dict(market_id=k,question=v['question']) for k,v in reviewed().items()]
        for original,x in zip(r,project(r,'en')):self.assertEqual(x['projection']['original'],original['question']);self.assertIsNone(x['projection']['summary'])

class EventIntelligenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        bilingual.BilingualVisualTests.setUpClass();cls.ui=bilingual.BilingualVisualTests();cls.ui.html=bilingual.BilingualVisualTests.html;cls.ui.translations=bilingual.BilingualVisualTests.translations;cls.ui.view=bilingual.BilingualVisualTests.view
    @classmethod
    def tearDownClass(cls):bilingual.BilingualVisualTests.tearDownClass()
    def test_actual_adapter_data_in_collapsed_detail(self):
        result=self.ui.render()
        for lang in ('en','zh'):
            html=result[lang];self.assertEqual(html.count('class="event-intelligence-detail"'),5)
            self.assertNotIn('<details class="event-intelligence-detail" open>',html)
            self.assertEqual(html.count('class="intelligence-section source-intelligence"'),5)
            self.assertIn('NO_RECORDED_HISTORY',html);self.assertIn('PREVIEW',html)
            self.assertIn('OFFICIAL_CONFIRMED',html);self.assertIn('UNVERIFIED_NEWS',html)
        self.assertTrue(result['unchanged'])
    def test_source_check_not_inferred_from_article_or_global_freshness(self):
        view=copy.deepcopy(self.ui.view);view['health_status']='FRESH';view['discovery_sources']={}
        result=self.ui.render(view=view)
        self.assertIn('Source health (no current connectivity probe)</dt><dd>Unknown',result['en'])
        self.assertIn('Last successful source check</dt><dd>Unknown',result['en'])
        self.assertIn('Saved input availability',result['en'])
        self.assertTrue(result['unchanged'])
    def test_source_rows_require_exact_canonical_article_membership(self):
        view=copy.deepcopy(self.ui.view)
        orphan=copy.deepcopy(view['items'][0]);orphan['article_reference']='unrelated-reference';orphan['news_source']['name']='Unrelated source sentinel'
        view['items'].append(orphan)
        result=self.ui.render(view=view)
        sections=re.findall(r'<section class="intelligence-section source-intelligence">([\s\S]*?)</dl></section></section>',result['en'])
        self.assertNotIn('Unrelated source sentinel',''.join(sections))
    def test_authoritative_source_state_and_distinct_timestamps(self):
        view=copy.deepcopy(self.ui.view);name=view['items'][0]['news_source']['name']
        view['discovery_sources']={name:{'status':'UNAVAILABLE','last_success_at':'2026-10-07T10:00:00Z'}}
        result=self.ui.render(view=view)
        self.assertIn('2026-10-07T10:00:00Z',result['en']);self.assertIn('Source health (no current connectivity probe)</dt><dd>Unknown',result['en'])
    def test_watch_translation_through_real_render_path_and_original_access(self):
        q=reviewed()['2589810']['question'];view=copy.deepcopy(self.ui.view)
        view['prediction_market_watch']={'markets':[dict(market_id='2589810',question=q,category='MONETARY_POLICY',market_status='ACTIVE',source_status='SAVED_SNAPSHOT',outcomes=['Yes','No'],probabilities=[0.3,0.7],outcome_type='BINARY_YES_NO',link_status='NO_MATCH')],'categories':['MONETARY_POLICY'],'market_count':1,'source_status':'SAVED_SNAPSHOT'}
        r=self.ui.render(view=view);self.assertIn('至少 50 個基點',r['zh']);self.assertIn(q,r['zh']);self.assertIn('class="watch-original-question"',r['zh']);self.assertIn('是（Yes）',r['zh']);self.assertNotIn('至少 50 個基點',r['en'])
        self.assertTrue(r['unchanged'])
    def test_new_asset_served_read_only(self):
        status,content,data=self.ui.http.request('/ui/radar_market_translations.js');self.assertEqual(status,200);self.assertEqual(content,'text/javascript; charset=utf-8');self.assertIn(b'REVIEWED',data)
