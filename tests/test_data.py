"""Series -> chart props. Network is mocked: the shapes and the scaling are what matter."""

from __future__ import annotations

import json
import unittest
from unittest import mock

from vidforge.data import (DataError, Series, bar_props, big_number_props, compare_props,
                           from_csv, human_scale, line_props)
from vidforge.data import worldbank


def gdp() -> Series:
    return Series(name="GDP", unit="", source="数据来源：世界银行（NY.GDP.MKTP.CD）", points={
        "中国": [(2000, 1.2e12), (2010, 6.1e12), (2023, 1.83e13)],
        "美国": [(2000, 1.03e13), (2010, 1.5e13), (2023, 2.78e13)],
    })


class Scaling(unittest.TestCase):
    def test_trillions_become_万亿_not_a_wall_of_digits(self):
        self.assertEqual(human_scale([1.83e13]), (1e12, "万亿"))
        self.assertEqual(human_scale([1.4e9]), (1e8, "亿"))
        self.assertEqual(human_scale([12.5]), (1.0, ""))

    def test_english_scale_is_available_for_english_projects(self):
        self.assertEqual(human_scale([1.83e13], zh=False), (1e12, "T"))


class Charts(unittest.TestCase):
    def test_line_keeps_the_order_asked_for_and_scales_every_line_the_same(self):
        p = line_props(gdp(), "中美 GDP")
        self.assertEqual([l["label"] for l in p["lines"]], ["中国", "美国"])
        self.assertEqual(p["unit"], "万亿")
        self.assertAlmostEqual(p["lines"][0]["points"][-1]["y"], 18.3, places=1)
        self.assertAlmostEqual(p["lines"][1]["points"][-1]["y"], 27.8, places=1)

    def test_every_chart_carries_the_source(self):
        s = gdp()
        for props in (line_props(s), bar_props(s), big_number_props(s, "中国"),
                      compare_props(s, "中国", "美国")):
            self.assertIn("世界银行", props["source"])

    def test_bar_ranks_the_latest_year_descending(self):
        p = bar_props(gdp())
        self.assertEqual([i["label"] for i in p["items"]], ["美国", "中国"])
        self.assertIn("2023", p["title"])

    def test_bar_can_be_asked_for_an_older_year(self):
        self.assertEqual([i["label"] for i in bar_props(gdp(), year=2000)["items"]], ["美国", "中国"])

    def test_big_number_reports_growth_since_the_first_year_it_has(self):
        p = big_number_props(gdp(), "中国")
        self.assertEqual((p["value"], p["unit"]), ("18.3", "万亿"))
        self.assertEqual(p["changeSince"], "2000")
        self.assertGreater(p["change"], 1000)          # 1.2 -> 18.3 trillion

    def test_compare_states_the_ratio_both_ways_round(self):
        p = compare_props(gdp(), "中国", "美国")
        self.assertEqual(p["left"]["label"], "中国")
        self.assertAlmostEqual(p["ratio"], 0.66, places=2)

    def test_a_missing_country_is_an_error_not_a_blank_chart(self):
        with self.assertRaises(DataError):
            compare_props(gdp(), "中国", "日本")


class Csv(unittest.TestCase):
    TABLE = "年份,一线城市,二线城市\n2021,100,80\n2022,92,74\n2023,85,70\n"

    def test_pasted_table_becomes_a_series(self):
        s = from_csv(self.TABLE, name="二手房价格指数", source="数据来源：国家统计局")
        self.assertEqual(s.labels, ["一线城市", "二线城市"])
        self.assertEqual(s.points["一线城市"][-1], (2023.0, 85.0))
        self.assertEqual(line_props(s)["source"], "数据来源：国家统计局")

    def test_tabs_commas_and_thousands_separators_all_work(self):
        s = from_csv("年份\t北京\n2022\t1,234\n2023\t2,345")
        self.assertEqual(s.points["北京"], [(2022.0, 1234.0), (2023.0, 2345.0)])

    def test_gaps_are_skipped_rather_than_read_as_zero(self):
        s = from_csv("年份,甲,乙\n2021,10,—\n2022,12,8")
        self.assertEqual(s.points["乙"], [(2022.0, 8.0)])

    def test_a_table_with_no_numbers_is_rejected(self):
        with self.assertRaises(DataError):
            from_csv("年份,甲\n2021,N/A")


class WorldBank(unittest.TestCase):
    REPLY = [
        {"page": 1, "total": 4},
        [
            {"countryiso3code": "CHN", "country": {"value": "China"}, "date": "2023", "value": 18270356654533.2,
             "indicator": {"value": "GDP (current US$)"}},
            {"countryiso3code": "CHN", "country": {"value": "China"}, "date": "2022", "value": None,
             "indicator": {"value": "GDP (current US$)"}},
            {"countryiso3code": "USA", "country": {"value": "United States"}, "date": "2023", "value": 27811517000000.0,
             "indicator": {"value": "GDP (current US$)"}},
        ],
    ]

    def fetch(self, **kw):
        with mock.patch("vidforge.data.worldbank._get", return_value=self.REPLY):
            return worldbank.fetch("NY.GDP.MKTP.CD", ["CHN", "USA"], **kw)

    def test_countries_come_back_in_the_order_requested_with_chinese_names(self):
        s = self.fetch()
        self.assertEqual(s.labels, ["中国", "美国"])

    def test_null_years_are_dropped_rather_than_plotted_as_zero(self):
        self.assertEqual(len(self.fetch().points["中国"]), 1)

    def test_the_indicator_code_is_recorded_in_the_source_line(self):
        self.assertIn("NY.GDP.MKTP.CD", self.fetch().source)

    def test_an_empty_answer_says_so_instead_of_returning_an_empty_chart(self):
        with mock.patch("vidforge.data.worldbank._get", return_value=[{"total": 0}, []]):
            with self.assertRaises(DataError):
                worldbank.fetch("NOPE", ["CHN"])

    def test_the_api_error_envelope_is_surfaced(self):
        envelope = [{"message": [{"value": "The provided parameter value is not valid"}]}]
        with mock.patch("vidforge.data.worldbank.urllib.request.urlopen") as op:
            op.return_value.__enter__.return_value.read.return_value = json.dumps(envelope).encode()
            with mock.patch("vidforge.data.worldbank.CACHE", worldbank.CACHE / "test-miss"):
                with self.assertRaises(DataError) as cm:
                    worldbank._get("country/XX/indicator/YY", {})
        self.assertIn("not valid", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
