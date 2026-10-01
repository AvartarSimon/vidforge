"""World Bank Open Data — GDP, population, energy, trade, urbanisation, for 200+ countries.

No key and no signup (checked 2026-10), ~16,000 indicators, JSON over HTTPS. That combination is
why this is the default source: a topic like 房地产 / 人口 / 能源 can be answered with a real
series in one call instead of a figure copied off a slide.

    search("population")                     -> candidate indicator codes
    fetch("SP.POP.TOTL", ["CHN", "IND"])     -> Series ready for line_props()

Answers are cached under ~/.vidforge/data-cache/ so re-rendering a project does not re-fetch, and
so a finished video can be rebuilt offline with exactly the numbers it was made with.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from . import DataError, Series

API = "https://api.worldbank.org/v2"
CACHE = Path.home() / ".vidforge" / "data-cache"
CACHE_DAYS = 30

# The handful that cover most of this channel's beat; `search()` reaches the other ~16,000.
COMMON = {
    "NY.GDP.MKTP.CD": "GDP（现价美元）",
    "NY.GDP.PCAP.CD": "人均 GDP（现价美元）",
    "NY.GDP.MKTP.KD.ZG": "GDP 年增长率 %",
    "FP.CPI.TOTL.ZG": "通胀率（CPI）%",
    "SP.POP.TOTL": "总人口",
    "SP.POP.GROW": "人口增长率 %",
    "SP.DYN.TFRT.IN": "总和生育率",
    "SP.POP.65UP.TO.ZS": "65 岁以上人口占比 %",
    "SP.URB.TOTL.IN.ZS": "城镇化率 %",
    "SL.UEM.TOTL.ZS": "失业率 %",
    "NE.EXP.GNFS.ZS": "出口占 GDP %",
    "BX.KLT.DINV.CD.WD": "外商直接投资（美元）",
    "GC.DOD.TOTL.GD.ZS": "政府债务占 GDP %",
    "EG.USE.PCAP.KG.OE": "人均能源消费",
    "EG.FEC.RNEW.ZS": "可再生能源占比 %",
    "EN.GHG.CO2.MT.CE.AR5": "二氧化碳排放（百万吨）",
    "IT.NET.USER.ZS": "互联网普及率 %",
    "MS.MIL.XPND.GD.ZS": "军费占 GDP %",
}

# Chinese names for the countries this channel talks about most; anything else falls back to the
# World Bank's own English name.
ZH_NAMES = {
    "CHN": "中国", "USA": "美国", "JPN": "日本", "DEU": "德国", "IND": "印度", "GBR": "英国",
    "FRA": "法国", "RUS": "俄罗斯", "KOR": "韩国", "AUS": "澳大利亚", "CAN": "加拿大",
    "BRA": "巴西", "IDN": "印尼", "VNM": "越南", "SGP": "新加坡", "ITA": "意大利",
    "ESP": "西班牙", "MEX": "墨西哥", "SAU": "沙特", "ZAF": "南非", "TUR": "土耳其",
    "NLD": "荷兰", "CHE": "瑞士", "SWE": "瑞典", "POL": "波兰", "THA": "泰国",
    "MYS": "马来西亚", "PHL": "菲律宾", "NZL": "新西兰", "ARE": "阿联酋", "IRN": "伊朗",
    "EUU": "欧盟", "WLD": "世界", "OED": "经合组织", "HKG": "中国香港", "TWN": "中国台湾",
}


def _get(path: str, params: dict, timeout: int = 60) -> list:
    url = f"{API}/{path}?" + urllib.parse.urlencode({**params, "format": "json"})
    key = CACHE / (urllib.parse.quote(url, safe="")[:150] + ".json")
    if key.is_file() and time.time() - key.stat().st_mtime < CACHE_DAYS * 86400:
        try:
            return json.loads(key.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise DataError(f"世界银行接口 HTTP {e.code}：{url}") from None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
        raise DataError(f"世界银行接口不可用：{e}") from None
    if isinstance(data, list) and data and isinstance(data[0], dict) and data[0].get("message"):
        msg = data[0]["message"][0].get("value", "")
        raise DataError(f"世界银行接口报错：{msg}")
    CACHE.mkdir(parents=True, exist_ok=True)
    key.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data


def search(text: str, limit: int = 15) -> list[dict]:
    """Indicators whose name matches `text` — how you find the code for a topic.

    Matching happens locally over the full indicator list (one cached download) because the API's
    own search is exact-match only and misses the obvious words."""
    text = text.strip().lower()
    if not text:
        return [{"id": k, "name": v, "source": "World Bank"} for k, v in COMMON.items()][:limit]
    hits = [{"id": k, "name": v, "source": "World Bank"} for k, v in COMMON.items()
            if text in k.lower() or text in v.lower()]
    data = _get("indicator", {"per_page": 25000})
    rows = data[1] if len(data) > 1 and isinstance(data[1], list) else []
    for row in rows:
        name = (row.get("name") or "")
        if text in name.lower() or text == (row.get("id") or "").lower():
            if not any(h["id"] == row["id"] for h in hits):
                hits.append({"id": row["id"], "name": name,
                             "source": (row.get("sourceOrganization") or "World Bank")[:120]})
        if len(hits) >= limit:
            break
    return hits[:limit]


def fetch(indicator: str, countries: list[str], start: int | None = None, end: int | None = None,
          zh: bool = True) -> Series:
    """One indicator for several countries -> Series, with the source filled in."""
    codes = [c.strip().upper() for c in countries if c.strip()]
    if not codes:
        raise DataError("至少要一个国家代码，例如 CHN")
    params = {"per_page": 20000}
    if start or end:
        params["date"] = f"{start or 1960}:{end or time.gmtime().tm_year}"
    data = _get(f"country/{';'.join(codes)}/indicator/{indicator}", params)
    rows = data[1] if len(data) > 1 and isinstance(data[1], list) else []
    if not rows:
        raise DataError(f"{indicator} 在 {', '.join(codes)} 上没有数据（指标代码写对了吗？）")
    name = rows[0].get("indicator", {}).get("value", indicator)
    series = Series(name=COMMON.get(indicator, name), unit="",
                    source=f"数据来源：世界银行（{indicator}）")
    for row in rows:
        if row.get("value") is None:
            continue
        iso = (row.get("countryiso3code") or "").upper()
        label = (ZH_NAMES.get(iso) if zh else None) or row.get("country", {}).get("value", iso)
        series.points.setdefault(label, []).append((float(row["date"]), float(row["value"])))
    if not series.points:
        raise DataError(f"{indicator}：这些国家/年份全是空值")
    for label in series.points:
        series.points[label].sort()
    # keep the order the caller asked for, so "中国 vs 美国" is not drawn the other way round
    wanted = [(ZH_NAMES.get(c) if zh else None) or c for c in codes]
    series.points = {k: series.points[k] for k in sorted(
        series.points, key=lambda k: wanted.index(k) if k in wanted else 99)}
    return series
