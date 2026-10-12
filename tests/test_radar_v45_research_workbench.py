import copy
import hashlib
import unittest
from pathlib import Path

from tools.stage1b_historical_campaign import radar_market_reaction as research
import test_bilingual_visual_ui as bilingual


class RealResearchCases(unittest.TestCase):
    def test_three_real_cases_and_only_two_additions(self):
        library = research.load_research_library()
        self.assertEqual(library["status"], "AVAILABLE")
        self.assertEqual(library["total_case_count"], 3)
        self.assertEqual(library["observed_price_case_count"], 3)
        self.assertEqual(library["not_measured_case_count"], 0)
        self.assertEqual(library["official_case_count"], 3)
        self.assertEqual(library["pit_replay_case_count"], 0)
        self.assertEqual(library["comparable_pair_count"], 3)

    def test_march_decision_and_decimal_observation(self):
        c = research.load_case(
            research.ROOT / "demo/radar_public/market_reaction/ecb_2025_03_06.json",
            research.ROOT / "demo/radar_public/market_reaction/ecb_eurusd_2025_03.csv",
            expected_event_source=research.RESEARCH_CASES[0]["event_source"],
            expected_market_data_source=research.RESEARCH_CASES[0]["data_source"],
            expected_event_date="2025-03-06", expected_effective_date="2025-03-12",
            case_id="ecb-2025-03-06")
        r = c["receipt"]
        self.assertEqual(r["pre_event_observation"]["observation_date"], "2025-03-05")
        self.assertEqual(r["pre_event_observation"]["value"], "1.0694")
        self.assertEqual(r["post_event_observation"]["observation_date"], "2025-03-07")
        self.assertEqual(r["post_event_observation"]["value"], "1.0857")
        self.assertEqual((r["absolute_change"], r["percentage_change"], r["elapsed_calendar_days"]),
                         ("0.0163", "1.524219", 2))
        self.assertIsNone(r["event_timestamp_utc"])
        self.assertIsNone(r["source_published_at"])

    def test_april_holiday_window_is_explicit_and_event_day_excluded(self):
        c = research.load_case(
            research.ROOT / "demo/radar_public/market_reaction/ecb_2025_04_17.json",
            research.ROOT / "demo/radar_public/market_reaction/ecb_eurusd_2025_04.csv",
            expected_event_source=research.RESEARCH_CASES[1]["event_source"],
            expected_market_data_source=research.RESEARCH_CASES[1]["data_source"],
            expected_event_date="2025-04-17", expected_effective_date="2025-04-23",
            case_id="ecb-2025-04-17")
        r = c["receipt"]
        self.assertEqual(r["pre_event_observation"]["observation_date"], "2025-04-16")
        self.assertEqual(r["post_event_observation"]["observation_date"], "2025-04-22")
        self.assertEqual((r["absolute_change"], r["percentage_change"], r["elapsed_calendar_days"]),
                         ("0.0121", "1.065610", 6))
        self.assertEqual(r["intervening_unobserved_dates"],
                         ["2025-04-18", "2025-04-19", "2025-04-20", "2025-04-21"])
        self.assertIn("2025-04-17", [o["observation_date"] for o in r["observations"]])
        self.assertNotEqual(r["pre_event_observation"]["observation_date"], "2025-04-17")
        self.assertNotEqual(r["post_event_observation"]["observation_date"], "2025-04-17")

    def test_truth_pit_and_causality_boundaries(self):
        for c in research.load_research_library()["cases"]:
            r = c["receipt"]
            self.assertEqual(c["event"]["verification_status"], "UNVERIFIED_NEWS")
            self.assertTrue(c["official_evidence"])
            self.assertTrue(all(x["evidence_status"] == "OFFICIAL_CONFIRMED" for x in c["official_evidence"]))
            self.assertTrue(all(x["published_at"] is None for x in c["official_evidence"]))
            self.assertEqual(r["time_basis"], "EX_POST_MARKET_OBSERVATION")
            self.assertFalse(r["point_in_time_available"])
            self.assertEqual(r["causal_attribution_status"], "NOT_ESTABLISHED")

    def test_only_fixed_comparable_ecb_instrument_is_counted(self):
        library = research.load_research_library()
        for a_id, b_id in library["comparable_pairs"]:
            a = next(c for c in library["cases"] if c["research_case_id"] == a_id)["receipt"]
            b = next(c for c in library["cases"] if c["research_case_id"] == b_id)["receipt"]
            self.assertEqual((a["instrument_id"], a["market_data_provider"], a["data_frequency"]),
                             (b["instrument_id"], b["market_data_provider"], b["data_frequency"]))

    def test_original_provider_csv_bytes_and_packet_hashes(self):
        for cfg in research.RESEARCH_CASES:
            packet = research.json.loads(cfg["case_path"].read_bytes())
            raw = cfg["data_path"].read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), packet["market_data_sha256"])
            self.assertEqual(packet["event_source"], cfg["event_source"])
            self.assertEqual(packet["market_data_source"], cfg["data_source"])
            self.assertFalse(packet["synthetic"])


class ResearchWorkbenchUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        bilingual.BilingualVisualTests.setUpClass()
        cls.ui = bilingual.BilingualVisualTests()
        cls.ui.html = bilingual.BilingualVisualTests.html
        cls.ui.translations = bilingual.BilingualVisualTests.translations
        cls.ui.view = bilingual.BilingualVisualTests.view

    @classmethod
    def tearDownClass(cls):
        bilingual.BilingualVisualTests.tearDownClass()

    def test_api_library_stays_out_of_current_event_and_news_counts(self):
        v = self.ui.view
        self.assertEqual(v["market_research_library"]["total_case_count"], 3)
        self.assertEqual(v["market_research_library"]["observed_price_case_count"], 3)
        self.assertEqual(v["news_item_count"], len(v["items"]))
        current_ids = {event["event_id"] for event in v["events"]}
        self.assertTrue(current_ids.isdisjoint({case["event"]["event_id"] for case in v["market_research_library"]["cases"]}))

    def test_bilingual_library_details_comparison_and_boundaries(self):
        result = self.ui.render()
        en, zh = result["en"], result["zh"]
        for text in ("Historical Research", "2025-03-06", "2025-04-17", "2025-06-05",
                     "1.524219", "1.065610", "0.237175", "data-research-compare", "Research Evidence",
                     "NOT_ESTABLISHED", "No aggregate score is calculated"):
            self.assertIn(text, en)
        for text in ("歷史事件研究", "研究證據摘要", "事實", "可能機制", "不確定性", "下一步驗證",
                     "因果效果", "2025-04-22", "PIT Replay", "依 ECB 原文整理",
                     "ECB 決定將三項主要利率下調 25 個基點"):
            self.assertIn(text, zh)
        self.assertIn('<option value="ecb-2025-03-06" selected>', en)
        self.assertIn('<option value="ecb-2025-04-17" selected>', en)
        self.assertEqual(en.count('class="research-case-card'), 3)

    def test_unavailable_library_has_no_fake_reaction_chart(self):
        view = copy.deepcopy(self.ui.view)
        view["market_research_library"] = {
            "status": "NOT_MEASURED", "cases": [], "total_case_count": 3,
            "observed_price_case_count": 0, "not_measured_case_count": 3,
            "official_case_count": 0, "pit_replay_case_count": 0,
            "comparable_pairs": [], "comparable_pair_count": 0,
        }
        result = self.ui.render(view=view)
        self.assertNotIn('class="research-case-card', result["en"])
        self.assertNotIn('class="reaction-chart"', result["en"])
        self.assertNotIn('class="comparison-chart"', result["en"])
        self.assertIn("NOT_MEASURED", result["en"])


if __name__ == "__main__":
    unittest.main()
