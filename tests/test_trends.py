"""热点发现：取源、打分、以及 /api/trends。

Every fetcher is tested against a captured sample of the real response rather than the network,
so the suite stays offline. The samples are trimmed copies of what the live endpoints returned on
2026-10-05 — if a site changes shape, the parser test is what notices.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from vidforge import trends, ui
from vidforge.trends import baidu, bilibili, googlenews, hn, score as sc, toutiao
from vidforge.trends import youtube as yt

TOUTIAO = json.dumps({"data": [
    {"Title": "央行宣布降息25个基点", "Url": "https://x/1", "HotValue": "9123456"},
    {"Title": "日本总人口减至1.2297亿", "Url": "https://x/2", "HotValue": "812345"},
    {"Title": "", "Url": "https://x/3"},
    {"Title": "某明星恋情曝光", "Url": "https://x/4", "HotValue": "not-a-number"},
]})

BAIDU = ('junk{"query":"全国房地产市场基本情况","hotScore":"4812345"}more'
         '{"query":"某综艺收视破纪录","hotScore":"3912345"}'
         '{"query":"全国房地产市场基本情况","hotScore":"1"}'      # duplicate, must collapse
         '{"query":"&amp;特殊字符","hotScore":"7"}')

BILIBILI_OK = json.dumps({"code": 0, "data": {"list": [
    {"title": "中国人口为什么开始减少", "bvid": "BV1", "stat": {"view": 1234567},
     "owner": {"name": "某频道"}, "duration": 780},
    {"title": "", "bvid": "BV2"},
]}})
BILIBILI_BLOCKED = json.dumps({"code": -352, "message": "风控校验失败", "data": {}})

GNEWS = """<rss><channel>
<item><title>越南三季度经济增长9.95% - 财新</title><link>https://a</link><pubDate>Sun, 05 Oct 2026</pubDate></item>
<item><title><![CDATA[2026年1—8月份全国房地产市场基本情况]]></title><link><![CDATA[https://b?x=1]]></link></item>
<item><title></title><link>https://c</link></item>
</channel></rss>"""

YT_API = json.dumps({"items": [
    {"id": "abc", "snippet": {"title": "How China's Housing Bubble Ended",
                              "channelTitle": "Ch", "publishedAt": "2026-10-01T00:00:00Z"},
     "statistics": {"viewCount": "480000"}},
]})


class FetcherTest(unittest.TestCase):
    def test_toutiao_keeps_titles_and_skips_blanks(self):
        with mock.patch.object(toutiao, "get_json", return_value=json.loads(TOUTIAO)):
            got = toutiao.fetch()
        self.assertEqual([t.title for t in got],
                         ["央行宣布降息25个基点", "日本总人口减至1.2297亿", "某明星恋情曝光"])
        self.assertEqual([t.rank for t in got], [1, 2, 3])
        self.assertEqual(got[0].heat, 9123456)
        self.assertIsNone(got[2].heat, "a non-numeric heat must not crash or lie")

    def test_baidu_collapses_duplicates_and_unescapes(self):
        with mock.patch.object(baidu, "get", return_value=BAIDU):
            got = baidu.fetch()
        self.assertEqual([t.title for t in got],
                         ["全国房地产市场基本情况", "某综艺收视破纪录", "&特殊字符"])
        self.assertEqual([t.rank for t in got], [1, 2, 3])
        self.assertIn("wd=", got[0].url)

    def test_baidu_url_is_percent_encoded(self):
        with mock.patch.object(baidu, "get", return_value=BAIDU):
            got = baidu.fetch()
        self.assertNotIn("全国", got[0].url, "a URL with raw CJK cannot be requested")

    def test_bilibili_parses_and_carries_the_view_count(self):
        with mock.patch.object(bilibili, "get_json", return_value=json.loads(BILIBILI_OK)):
            got = bilibili.fetch()
        self.assertEqual([t.title for t in got], ["中国人口为什么开始减少"])
        self.assertEqual(got[0].heat, 1234567)
        self.assertIn("BV1", got[0].url)

    def test_bilibili_says_so_when_it_is_throttled(self):
        # a silent zero rows would be read as "nothing today" instead of "you were blocked"
        with mock.patch.object(bilibili, "get_json", return_value=json.loads(BILIBILI_BLOCKED)):
            with self.assertRaises(trends.TrendsError) as cm:
                bilibili.fetch()
        self.assertIn("-352", str(cm.exception))

    def test_googlenews_splits_the_outlet_off_the_title(self):
        with mock.patch.object(googlenews, "get", return_value=GNEWS):
            got = googlenews.fetch(queries=["经济"])
        self.assertEqual(got[0].title, "越南三季度经济增长9.95%")
        self.assertEqual(got[0].extra["outlet"], "财新")
        self.assertEqual(got[0].extra["query"], "经济")

    def test_googlenews_handles_cdata(self):
        with mock.patch.object(googlenews, "get", return_value=GNEWS):
            got = googlenews.fetch(queries=["房地产"])
        self.assertEqual(got[1].title, "2026年1—8月份全国房地产市场基本情况")
        self.assertEqual(got[1].url, "https://b?x=1")

    def test_googlenews_encodes_the_query_into_the_url(self):
        seen = []
        with mock.patch.object(googlenews, "get", side_effect=lambda u: seen.append(u) or GNEWS):
            googlenews.fetch(queries=["房地产"])
        self.assertTrue(seen)
        self.assertNotIn("房地产", seen[0], "a URL with raw CJK raises UnicodeEncodeError")
        self.assertIn("%", seen[0])

    def test_youtube_is_empty_without_a_key_rather_than_guessing(self):
        # the keyless trending page measured 0 videos; parsing it would yield UI chrome, not news
        with mock.patch.dict("os.environ", {"YOUTUBE_API_KEY": ""}, clear=False):
            self.assertEqual(yt.fetch(), [])

    def test_youtube_with_a_key(self):
        with mock.patch.dict("os.environ", {"YOUTUBE_API_KEY": "k"}, clear=False), \
             mock.patch.object(yt, "get_json", return_value=json.loads(YT_API)):
            got = yt.fetch()
        self.assertEqual(got[0].title, "How China's Housing Bubble Ended")
        self.assertEqual(got[0].heat, 480000)

    def test_hn_walks_the_front_page(self):
        def fake(url):
            if url.endswith("topstories.json"):
                return [11, 22]
            return {"title": f"Story {url[-7]}", "url": "https://s", "score": 120}
        with mock.patch.object(hn, "get_json", side_effect=fake):
            got = hn.fetch()
        self.assertEqual(len(got), 2)
        self.assertEqual(got[0].heat, 120)


class RegistryTest(unittest.TestCase):
    def test_every_source_has_a_module_that_imports(self):
        for sid in trends.SOURCES:
            mod = __import__(f"vidforge.trends.{trends.SOURCES[sid][0]}", fromlist=["x"])
            self.assertTrue(callable(mod.fetch), sid)

    def test_available_lists_the_blocked_ones_with_a_reason(self):
        rows = {r["id"]: r for r in trends.available()}
        self.assertTrue(rows["toutiao"]["ok"])
        for blocked in ("douyin", "tiktok", "kuaishou", "weibo"):
            self.assertFalse(rows[blocked]["ok"], blocked)
            self.assertTrue(rows[blocked]["why"], blocked)

    def test_kinds_split_attention_from_relevance(self):
        self.assertEqual(trends.kind_of("toutiao"), "hot")
        self.assertEqual(trends.kind_of("googlenews"), "news")
        self.assertEqual(set(r["kind"] for r in trends.available()) - set(trends.KINDS), set())

    def test_unknown_source_is_an_error(self):
        with self.assertRaises(trends.TrendsError):
            trends.fetch_one(Path(tempfile.gettempdir()), "nope")

    def test_a_broken_source_returns_empty_instead_of_taking_the_page_down(self):
        td = Path(tempfile.mkdtemp())
        try:
            with mock.patch.object(toutiao, "get_json", side_effect=OSError("boom")):
                logged: list[str] = []
                got = trends.fetch_one(td, "toutiao", log=logged.append)
            self.assertEqual(got, [])
            self.assertTrue(any("toutiao" in m for m in logged))
        finally:
            shutil.rmtree(td, ignore_errors=True)

    def test_topics_are_cached_so_a_reload_is_free(self):
        td = Path(tempfile.mkdtemp())
        try:
            calls = []
            with mock.patch.object(toutiao, "get_json",
                                   side_effect=lambda *a, **k: calls.append(1) or json.loads(TOUTIAO)):
                trends.fetch_one(td, "toutiao")
                trends.fetch_one(td, "toutiao")
            self.assertEqual(len(calls), 1, "the 15-minute bucket should serve the second call")
        finally:
            shutil.rmtree(td, ignore_errors=True)


class DomainTest(unittest.TestCase):
    def test_the_nine_directions_are_recognised(self):
        for title, want in [
            ("央行宣布降息25个基点", "金融"),
            ("去年全国680万平米新房未售出", "房地产"),
            ("日本总人口减至1.2297亿", "人口"),
            ("余承东：华为已量产芯片", "科技"),
            ("新型储能迎来政策利好", "能源"),
            ("平陆运河：跨越百年的向海之梦", "历史"),
        ]:
            self.assertEqual(sc.domain_of(title)[0], want, title)

    def test_an_ascii_keyword_needs_a_word_boundary(self):
        # measured on a live hot list: "AI" matched inside "Bahrain" and made F1 a tech story
        self.assertEqual(sc.domain_of("Bahrain F1 software glitch")[0], "")
        self.assertEqual(sc.domain_of("AI 芯片禁令升级")[0], "科技")
        self.assertEqual(sc.domain_of("OpenAI releases a model")[0], "科技")

    def test_a_bare_country_name_is_not_a_topic(self):
        # entertainment and sport headlines are full of country names
        for off in ("日本代表团团长承认金牌数被中国碾压", "蔡康永账号IP在日本", "美国歌手宣布巡演"):
            self.assertEqual(sc.domain_of(off)[0], "", off)

    def test_a_country_name_adds_to_a_real_topic(self):
        on = sc.score_one(trends.Topic("美国9月非农就业人口增加2.9万人", "toutiao", 1))
        off = sc.score_one(trends.Topic("9月非农就业人口增加2.9万人", "toutiao", 1))
        self.assertGreater(on.score, off.score)
        self.assertIn("美国", on.reasons)

    def test_region_alone_scores_nothing(self):
        s = sc.score_one(trends.Topic("蔡康永账号IP在日本", "toutiao", 1))
        self.assertEqual(s.domain, "")
        self.assertFalse(any("日本" in r for r in s.reasons))


class ScoreTest(unittest.TestCase):
    def topic(self, title, source="toutiao", rank=1):
        return trends.Topic(title, source, rank)

    def test_rank_one_outscores_rank_forty_on_the_same_list(self):
        a = sc.score_one(self.topic("央行降息", rank=1))
        b = sc.score_one(self.topic("央行降息", rank=40))
        self.assertGreater(a.score, b.score)

    def test_a_heavier_platform_outscores_a_lighter_one(self):
        a = sc.score_one(self.topic("央行降息", source="toutiao"))
        b = sc.score_one(self.topic("央行降息", source="hn"))
        self.assertGreater(a.score, b.score)

    def test_a_number_and_a_history_clue_both_add(self):
        plain = sc.score_one(self.topic("央行决定降息"))
        number = sc.score_one(self.topic("央行降息25个基点"))
        both = sc.score_one(self.topic("央行降息25个基点，为2015年以来首次"))
        self.assertGreater(number.score, plain.score)
        self.assertGreater(both.score, number.score)

    def test_banned_keywords_exclude_outright(self):
        self.assertIsNone(sc.score_one(self.topic("某敏感词事件"), banned=("敏感词",)))

    def test_custom_weights_override_the_defaults(self):
        t = self.topic("央行降息", source="hn")
        low = sc.score_one(t)
        high = sc.score_one(t, weights={"hn": 5.0})
        self.assertGreater(high.score, low.score)

    def test_the_same_story_on_two_lists_merges_and_gains(self):
        topics = [self.topic("央行降息25个基点", "toutiao", 1),
                  self.topic("央行降息 25 个基点！", "baidu", 3)]
        out = sc.rank(topics)
        self.assertEqual(len(out), 1, "one story, not two")
        single = sc.rank([topics[0]])[0]
        self.assertGreater(out[0].score, single.score)
        self.assertTrue(any("也在榜" in r for r in out[0].reasons))

    def test_merging_is_sublinear(self):
        # three lists carrying one headline is one story, not three
        one = sc.rank([self.topic("央行降息25个基点", "toutiao", 1)])[0].score
        two = sc.rank([self.topic("央行降息25个基点", "toutiao", 1),
                       self.topic("央行降息25个基点", "baidu", 1)])[0].score
        self.assertLess(two, one * 2)

    def test_on_domain_only_drops_the_rest(self):
        topics = [self.topic("央行降息"), self.topic("某明星恋情曝光")]
        self.assertEqual(len(sc.rank(topics, on_domain_only=True)), 1)
        self.assertEqual(len(sc.rank(topics, on_domain_only=False)), 2)

    def test_results_are_sorted_and_limited(self):
        topics = [self.topic(f"央行降息{i}个基点", rank=i + 1) for i in range(30)]
        out = sc.rank(topics, limit=5)
        self.assertEqual(len(out), 5)
        self.assertEqual([s.score for s in out], sorted((s.score for s in out), reverse=True))

    def test_explain_names_every_reason(self):
        s = sc.score_one(self.topic("央行降息25个基点，2015年以来首次"))
        line = sc.explain(s)
        for r in s.reasons:
            self.assertIn(r, line)

    def test_key_ignores_punctuation_and_case(self):
        self.assertEqual(trends.Topic("A, B! c", "x", 1).key, trends.Topic("ab C", "x", 1).key)


class TrendsApi(unittest.TestCase):
    def setUp(self):
        self.td = Path(tempfile.mkdtemp())
        (self.td / "project.json").write_text(json.dumps({
            "title": "T", "language": "zh", "voice": "zh-CN-YunxiNeural",
            "segments": [{"id": "s1", "text": "你好。"}],
        }, ensure_ascii=False), encoding="utf-8")
        self.state = ui.State(self.td / "project.json")
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), ui.make_handler(self.state))
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        shutil.rmtree(self.td, ignore_errors=True)

    def call(self, path):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}")
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.status, json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    def test_sources_route(self):
        status, j = self.call("/api/trends/sources")
        self.assertEqual(status, 200)
        self.assertEqual({r["id"] for r in j["sources"]} & {"toutiao", "douyin"}, {"toutiao", "douyin"})
        self.assertIn("hot", j["kinds"])

    def test_trends_route_groups_by_kind(self):
        with mock.patch.object(trends, "fetch", return_value=[
            trends.Topic("央行降息25个基点", "toutiao", 1),
            trends.Topic("某明星恋情曝光", "baidu", 2),
            trends.Topic("全国房地产市场基本情况", "googlenews", 1),
        ]):
            status, j = self.call("/api/trends?limit=5")
        self.assertEqual(status, 200)
        kinds = {g["kind"]: g for g in j["groups"]}
        self.assertEqual(set(kinds), set(trends.KINDS))
        self.assertEqual([i["title"] for i in kinds["hot"]["items"]], ["央行降息25个基点"])
        self.assertEqual([i["title"] for i in kinds["news"]["items"]], ["全国房地产市场基本情况"])
        self.assertTrue(j["on_domain_only"])
        self.assertTrue(kinds["hot"]["items"][0]["reasons"])

    def test_all_flag_keeps_off_domain_topics(self):
        with mock.patch.object(trends, "fetch",
                               return_value=[trends.Topic("某明星恋情曝光", "baidu", 2)]):
            _, j = self.call("/api/trends?all=1")
        hot = next(g for g in j["groups"] if g["kind"] == "hot")
        self.assertEqual(len(hot["items"]), 1)
        self.assertFalse(j["on_domain_only"])

    def test_a_fetch_failure_becomes_an_error_not_a_crash(self):
        with mock.patch.object(trends, "fetch", side_effect=trends.TrendsError("都挂了")):
            status, j = self.call("/api/trends")
        self.assertEqual(status, 400)
        self.assertIn("挂", j["error"])


if __name__ == "__main__":
    unittest.main()
