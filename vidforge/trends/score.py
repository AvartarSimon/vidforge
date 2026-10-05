"""给热榜打分：榜上的东西，哪些适合「用数据看热点，用历史看今天」。

A hot list is mostly not for you. On any given day 头条/百度 are led by entertainment, sport and
local crime; B 站 by games and anime. Handing that list over unsorted would be worse than useless,
because the work of filtering is exactly the work being automated.

So every topic gets a score out of the signals that can be computed locally, with no model and no
network call:

    平台权重 × 榜位      which list it is on, and how high      ← the owner's stated priority
    领域匹配             经济/房地产/人口/金融/历史/科技/能源/国际/政策
    有数字               a number in the title means a chart can carry it
    有年份/历史线索       「用历史看今天」的后半句能不能成立
    禁用词               categories[].banned_keywords -> excluded outright

The weights are deliberately plain multipliers rather than a trained model: when a topic ranks
high you can read *why* in one line, and when the ranking is wrong you can see which term did it.
`explain()` returns exactly that line.

平台权重按主人给的优先级：YouTube 和今日头条最高，B 站次之（中文长视频，形态最接近），
百度热搜和 Google News 做广度补充，HN 只在科技选题上加一点。抖音 / TikTok / 快手
抓不到（见 `trends.UNREACHABLE`），它们的权重留在表里，等哪天有正规途径可以直接插进来。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from . import SOURCES, Topic

# 频道定位的九个方向。命中任意一个就算领域内；命中多个不额外加分（一个选题讲清一件事就够了）。
DOMAINS: dict[str, tuple[str, ...]] = {
    "经济": ("经济", "GDP", "增长", "衰退", "通胀", "通缩", "物价", "CPI", "PPI", "失业", "就业",
             "消费", "出口", "进口", "贸易", "关税", "供应链", "制造业", "产能",
             "economy", "inflation", "recession", "GDP", "tariff", "trade", "unemployment"),
    "房地产": ("房地产", "楼市", "房价", "房贷", "土地", "开发商", "保交楼", "租金", "住房",
               "烂尾", "新房", "二手房", "公积金",
             "housing", "mortgage", "property", "real estate", "rent"),
    "人口": ("人口", "出生", "生育", "老龄", "结婚", "离婚", "移民", "人口流动", "城镇化", "户籍",
             "population", "birth rate", "fertility", "ageing", "aging", "migration"),
    "金融": ("金融", "央行", "利率", "降息", "加息", "汇率", "人民币", "美元", "股市", "A股",
             "债券", "国债", "基金", "银行", "信贷", "债务", "违约", "黄金", "比特币",
             "interest rate", "rate cut", "central bank", "bond", "yuan", "dollar", "stocks"),
    "历史": ("历史", "王朝", "战争", "条约", "革命", "起源", "古代", "世纪", "百年", "往事",
             "history", "historical", "century", "empire", "treaty"),
    "科技": ("科技", "AI", "人工智能", "芯片", "半导体", "算力", "模型", "大模型", "机器人",
             "新能源车", "自动驾驶", "量子", "航天", "卫星", "专利",
             "AI", "OpenAI", "Anthropic", "chip", "chips", "semiconductor", "GPU", "LLM", "model", "models", "robot", "robotics", "quantum", "satellite"),
    "能源": ("能源", "石油", "原油", "天然气", "煤炭", "电力", "电价", "光伏", "风电", "核电",
             "储能", "锂", "碳排", "减排",
             "energy", "oil", "gas", "coal", "nuclear", "solar", "grid", "battery"),
    # 注意：这里没有光秃的国名。"日本" "美国" 在娱乐、体育标题里每天都出现（实测：
    # 「日本代表团团长承认金牌数被中国碾压」「蔡康永账号 IP 在日本」都被当成了国际题材），
    # 所以国名移到下面的 REGIONS：只加一点分，不单独成立领域。
    "国际": ("国际关系", "欧盟", "北约", "台海", "南海", "地缘", "制裁", "外交", "峰会",
             "军演", "停战", "和谈", "关税战", "贸易战", "领土", "主权",
             "sanctions", "geopolitics", "NATO", "diplomacy", "summit"),
    "政策": ("政策", "国务院", "发改委", "财政部", "监管", "新规", "法案", "规划", "补贴",
             "税收", "改革", "试点", "会议",
             "policy", "regulation", "regulator", "bill", "subsidy", "ban"),
}

# 「用历史看今天」能不能成立的线索：一个年份，或一句明确的时间比较。
_YEAR = re.compile(r"(1[6-9]\d\d|20[0-4]\d)\s*年?")
_HISTORY = re.compile(r"历史|首次|以来|最[高低多少大]|纪录|创下|重演|当年|上一次|\d+\s*年[前来]")
# 复用 structure 的数字判据，不另造一套：那边已经分清了「六百八十万」和「聊一聊」
try:
    from ..structure import _NUMBER
except ImportError:                                   # pragma: no cover
    _NUMBER = re.compile(r"\d")

WEIGHTS = {
    "platform": 3.0,      # 平台权重 × 榜位衰减
    "domain": 4.0,        # 在不在这个频道讲的范围里 —— 最重要的一条
    "number": 2.0,        # 有数字 = 能配图表
    "history": 1.5,       # 有历史可照
    "region": 0.8,        # 涉外，**仅在已经有领域词时**加分
}


@dataclass
class Scored:
    topic: Topic
    score: float
    domain: str           # "" when the topic is outside the channel's nine directions
    reasons: list[str]

    @property
    def fit(self) -> bool:
        """Worth a look at all. Off-domain topics are ranked but not recommended."""
        return bool(self.domain)


# 国家/地区名：是个信号，但不是一个题材。它们只在已经有领域词时加分。
REGIONS = ("美国", "中国", "日本", "俄罗斯", "印度", "韩国", "德国", "法国", "英国",
           "欧洲", "中东", "中亚", "东南亚", "非洲", "拉美", "澳大利亚", "台湾", "香港")


def _hit(word: str, title: str) -> bool:
    """Does this keyword really occur?

    An ASCII keyword has to sit on a word boundary: matching "AI" as a substring turned
    "Bahrain" into a technology story (measured on a live hot list). CJK has no word boundaries,
    so a plain substring test is the right one there."""
    if word.isascii():
        # a phrase like "real estate" keeps its space through re.escape; the lookarounds only
        # guard the two ends
        return re.search(rf"(?<![A-Za-z0-9]){re.escape(word)}(?![A-Za-z0-9])", title, re.I) is not None
    return word in title


def domain_of(title: str) -> tuple[str, str]:
    """Which of the nine directions this title belongs to, and the word that decided it."""
    for name, words in DOMAINS.items():
        for w in words:
            if _hit(w, title):
                return name, w
    return "", ""


def region_of(title: str) -> str:
    return next((r for r in REGIONS if r in title), "")


def _platform(topic: Topic, weights: dict[str, float] | None = None) -> float:
    """Source weight, decayed by how far down the list the item sits.

    Rank 1 keeps the full weight, rank 25 keeps about a third: being #1 on 头条 is a different
    fact from being #40, and a flat per-source weight would throw that away."""
    w = (weights or {}).get(topic.source)
    if w is None:
        w = SOURCES.get(topic.source, ("", "", 0.5, "hot"))[2]
    return w * (1.0 / (1.0 + max(0, topic.rank - 1) / 12.0))


def score_one(topic: Topic, *, banned: tuple[str, ...] = (),
              weights: dict[str, float] | None = None) -> Scored | None:
    """None when the topic is excluded by a banned keyword."""
    title = topic.title
    for b in banned:
        if b and b in title:
            return None

    reasons: list[str] = []
    domain, hit = domain_of(title)
    total = WEIGHTS["platform"] * _platform(topic, weights)
    label = SOURCES.get(topic.source, (None, topic.source))[1] or topic.source
    reasons.append(f"{label} 第 {topic.rank} 位")

    if domain:
        total += WEIGHTS["domain"]
        reasons.append(f"{domain}（「{hit}」）")
        region = region_of(title)
        if region:
            total += WEIGHTS["region"]
            reasons.append(region)
    if _NUMBER.search(title):
        total += WEIGHTS["number"]
        reasons.append("标题里有数字，能配图表")
    if _YEAR.search(title) or _HISTORY.search(title):
        total += WEIGHTS["history"]
        reasons.append("有时间/历史线索，能照到今天")
    return Scored(topic=topic, score=round(total, 2), domain=domain, reasons=reasons)


def rank(topics: list[Topic], *, banned: tuple[str, ...] = (), on_domain_only: bool = False,
         weights: dict[str, float] | None = None, limit: int = 40) -> list[Scored]:
    """Score, merge the same story across lists, sort.

    A story on three hot lists is a bigger story than one on a single list, so duplicates are
    merged by adding a bonus rather than being dropped — but the bonus is sub-linear, because
    three lists carrying the same headline is one story, not three."""
    merged: dict[str, Scored] = {}
    for t in topics:
        s = score_one(t, banned=banned, weights=weights)
        if s is None or (on_domain_only and not s.domain):
            continue
        prev = merged.get(t.key)
        if prev is None:
            merged[t.key] = s
            continue
        keep, drop = (prev, s) if prev.score >= s.score else (s, prev)
        keep.score = round(keep.score + drop.score * 0.35, 2)
        label = SOURCES.get(drop.topic.source, (None, drop.topic.source))[1] or drop.topic.source
        keep.reasons.append(f"{label} 也在榜（第 {drop.topic.rank} 位）")
        merged[t.key] = keep
    out = sorted(merged.values(), key=lambda s: -s.score)
    return out[:limit]


def explain(s: Scored) -> str:
    return f"{s.score:5.1f}  {s.topic.title}   [{' · '.join(s.reasons)}]"
