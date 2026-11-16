"""The local model's answers are cleaned before anything is searched for (offline: chat() is mocked)."""
from __future__ import annotations

import json
import unittest
from unittest import mock

from vidforge import llm


class Keywords(unittest.TestCase):
    ROME = {"s1": "公元前二十七年，屋大维成为罗马的第一位皇帝。", "s2": "罗马军团沿着莱茵河修筑了长长的边墙。"}

    def test_the_prompts_own_example_is_not_an_answer(self):
        # a 3B model answered a script about Rome with the example from the prompt
        answer = json.dumps({"s1": ["秦国 青铜器 / 兵马俑 陶俑", "屋大维 雕像"], "s2": ["战国 地图", "罗马军团 浮雕"]}, ensure_ascii=False)
        got = llm.parse_ranked_answer(answer, self.ROME)
        self.assertEqual(got, {"s1": ["屋大维 雕像"], "s2": ["罗马军团 浮雕"]})

    def test_the_example_is_kept_when_the_script_really_is_about_it(self):
        items = {"q": "秦国的青铜器在战国时期已经很成熟。"}
        got = llm.parse_ranked_answer(json.dumps({"q": ["秦国 青铜器"]}, ensure_ascii=False), items)
        self.assertEqual(got, {"q": ["秦国 青铜器"]})
        self.assertIn(llm._EXAMPLE_ZH[0], llm.ranked_prompt(items), "the parser knows the example the prompt shows")

    def test_slash_joined_phrases_are_separate_subjects_and_capped(self):
        answer = json.dumps({"s1": ["屋大维 雕像 / 罗马 元老院", "罗马 广场", "奥古斯都 钱币", "罗马 地图", "凯撒 胸像"]}, ensure_ascii=False)
        got = llm.parse_ranked_answer(answer, self.ROME, n=4)
        self.assertEqual(got["s1"], ["屋大维 雕像", "罗马 元老院", "罗马 广场", "奥古斯都 钱币"])


class Translate(unittest.TestCase):
    def test_asks_again_for_what_the_first_answer_left_out(self):
        # the model translated entry 0 and stopped; every other phrase then went unsearched in English
        answers = iter(['{"0": "Octavian marble statue"}', '{"0": "Roman legion relief", "1": "Rhine frontier wall"}'])
        with mock.patch.object(llm, "chat", side_effect=lambda *a, **k: next(answers)) as chat:
            got = llm.translate_batch(["屋大维 雕像", "罗马军团 浮雕", "莱茵河 边墙"])
        self.assertEqual(chat.call_count, 2)
        self.assertEqual(got, {"屋大维 雕像": "Octavian marble statue", "罗马军团 浮雕": "Roman legion relief",
                               "莱茵河 边墙": "Rhine frontier wall"})

    def test_a_complete_answer_costs_one_call_and_no_model_costs_nothing_more(self):
        with mock.patch.object(llm, "chat", return_value='{"0": "Octavian marble statue"}') as chat:
            self.assertEqual(llm.translate_batch(["屋大维 雕像"]), {"屋大维 雕像": "Octavian marble statue"})
            self.assertEqual(chat.call_count, 1)
        with mock.patch.object(llm, "chat", side_effect=llm.LlmError("down")) as chat:
            self.assertEqual(llm.translate_batch(["屋大维 雕像", "罗马 广场"]), {})
            self.assertEqual(chat.call_count, 1)


if __name__ == "__main__":
    unittest.main()
