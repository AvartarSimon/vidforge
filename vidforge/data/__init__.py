"""Real numbers for the charts: fetch a public dataset, turn it into a Remotion chart.

A channel whose promise is "用数据看热点" lives or dies on two things — the numbers being right
and the viewer being told where they came from. So every series carries its source through to
the caption burned into the chart, and nothing here invents a figure.

    series = worldbank.fetch("NY.GDP.MKTP.CD", ["CHN", "USA"], 2000, 2023)
    props  = line_props(series, title="中国 vs 美国 GDP")

Sources
    worldbank  — World Bank Open Data: ~16,000 indicators, 200+ countries, no key, no signup.
    csv        — anything you paste or export yourself (国家统计局, Wind, your own spreadsheet).

Both produce the same `Series` object, so the chart builders do not care which one it came from.
"""

from __future__ import annotations

import csv as _csv
import io
import re
from dataclasses import dataclass, field


class DataError(RuntimeError):
    pass


@dataclass
class Series:
    """One or more named lines over a shared x axis (usually years)."""
    name: str                                   # what is being measured, e.g. "GDP (current US$)"
    unit: str = ""                              # "US$", "%", "人"
    source: str = ""                            # shown under the chart — never left empty
    points: dict[str, list[tuple[float, float]]] = field(default_factory=dict)   # label -> [(x, y)]

    @property
    def labels(self) -> list[str]:
        return list(self.points)

    def latest(self, label: str) -> tuple[float, float] | None:
        pts = self.points.get(label) or []
        return max(pts, key=lambda p: p[0]) if pts else None

    def span(self) -> tuple[float, float]:
        xs = [x for pts in self.points.values() for x, _ in pts]
        return (min(xs), max(xs)) if xs else (0.0, 0.0)


# -- scaling -------------------------------------------------------------------------------
# Raw figures from these datasets are unreadable on screen ("18270356654533.2"), so a series is
# rescaled once and the unit says what the numbers now mean.
_SCALES_ZH = ((1e12, "万亿"), (1e8, "亿"), (1e4, "万"))
_SCALES_EN = ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K"))


def human_scale(values: list[float], zh: bool = True) -> tuple[float, str]:
    """(divisor, suffix) that makes the biggest value read naturally."""
    top = max((abs(v) for v in values), default=0.0)
    for cut, suffix in (_SCALES_ZH if zh else _SCALES_EN):
        if top >= cut:
            return cut, suffix
    return 1.0, ""


def _fmt(v: float) -> str:
    return f"{v:,.0f}" if abs(v) >= 100 else f"{v:,.1f}"


# -- chart props ---------------------------------------------------------------------------
def line_props(s: Series, title: str = "", zh: bool = True, highlight_last: bool = True) -> dict:
    """LineChart props: a time series per label, drawn left to right."""
    if not s.points:
        raise DataError("没有数据点")
    div, suffix = human_scale([y for pts in s.points.values() for _, y in pts], zh)
    return {
        "title": title or s.name,
        "unit": f"{suffix}{s.unit}".strip(),
        "source": s.source,
        "highlightLast": highlight_last,
        "lines": [{"label": k, "points": [{"x": x, "y": y / div} for x, y in sorted(pts)]}
                  for k, pts in s.points.items()],
    }


def bar_props(s: Series, title: str = "", year: float | None = None, zh: bool = True) -> dict:
    """BarChart props from one year of a series — a ranking rather than a trend."""
    picks: list[tuple[str, float]] = []
    for label, pts in s.points.items():
        if not pts:
            continue
        pt = max(pts, key=lambda p: p[0]) if year is None else next((p for p in pts if p[0] == year), None)
        # falls through to the None check below
        if pt:
            picks.append((label, pt[1]))
    if not picks:
        raise DataError("这一年没有数据")
    div, suffix = human_scale([v for _, v in picks], zh)
    picks.sort(key=lambda p: -p[1])
    shown_year = year if year is not None else max(p[0] for pts in s.points.values() for p in pts)
    return {
        "title": title or f"{s.name}（{shown_year:.0f}）",
        "unit": f"{suffix}{s.unit}".strip(),
        "source": s.source,
        "items": [{"label": k, "value": v / div} for k, v in picks],
    }


def big_number_props(s: Series, label: str | None = None, title: str = "", zh: bool = True,
                     compare_to: float | None = None) -> dict:
    """BigNumber props: one figure, full screen — the hook a data video opens on."""
    label = label or (s.labels[0] if s.labels else "")
    pt = s.latest(label)
    if pt is None:
        raise DataError(f"没有 {label} 的数据")
    year, value = pt
    div, suffix = human_scale([value], zh)
    first = sorted(s.points[label])[0] if s.points.get(label) else None
    base = compare_to if compare_to is not None else (first[1] if first and first[1] else None)
    change = ((value - base) / base * 100) if base else None
    return {
        "title": title or s.name,
        "value": _fmt(value / div),
        "unit": f"{suffix}{s.unit}".strip(),
        "caption": f"{label} · {year:.0f}",
        "change": None if change is None else round(change, 1),
        "changeSince": None if first is None else f"{first[0]:.0f}",
        "source": s.source,
    }


def compare_props(s: Series, a: str, b: str, year: float | None = None, title: str = "",
                  zh: bool = True) -> dict:
    """Compare props: two figures side by side with the ratio between them."""
    out = []
    for label in (a, b):
        pts = s.points.get(label) or []
        if not pts:
            raise DataError(f"没有 {label} 的数据（有：{'、'.join(s.labels)}）")
        pt = max(pts, key=lambda p: p[0]) if year is None else next((p for p in pts if p[0] == year), None)
        if pt is None:
            raise DataError(f"{label} 没有 {year:.0f} 年的数据")
        out.append((label, pt))
    div, suffix = human_scale([p[1][1] for p in out], zh)
    (la, (ya, va)), (lb, (yb, vb)) = out
    return {
        "title": title or s.name,
        "unit": f"{suffix}{s.unit}".strip(),
        "source": s.source,
        "left": {"label": la, "value": _fmt(va / div), "raw": va, "caption": f"{ya:.0f}"},
        "right": {"label": lb, "value": _fmt(vb / div), "raw": vb, "caption": f"{yb:.0f}"},
        "ratio": round(va / vb, 2) if vb else None,
    }


# -- your own numbers ----------------------------------------------------------------------
def from_csv(text: str, name: str = "", unit: str = "", source: str = "") -> Series:
    """A pasted table -> Series. First column is the x axis, every other column is a line.

        年份,中国,美国
        2020,14.7,21.0
        2021,17.8,23.3

    This is how 国家统计局 / Wind / a spreadsheet gets in: those have no open API, and copying a
    table is less work than scripting a scraper."""
    body = text.strip()
    delim = "\t" if "\t" in body.splitlines()[0] else ("," if "," in body else ";")
    rows = [r for r in _csv.reader(io.StringIO(body), delimiter=delim) if any(c.strip() for c in r)]
    if len(rows) < 2:
        raise DataError("至少要有表头和一行数据")
    header = [c.strip() for c in rows[0]]
    series = Series(name=name or header[0], unit=unit, source=source or "自有数据")
    for col in header[1:]:
        series.points[col] = []
    for row in rows[1:]:
        try:
            x = float(re.sub(r"[^\d.\-]", "", row[0]))
        except ValueError:
            continue
        for i, col in enumerate(header[1:], start=1):
            if i >= len(row):
                continue
            raw = re.sub(r"[,\s%]", "", row[i])
            if not raw or raw in ("-", "—", "N/A", "NA"):
                continue
            try:
                series.points[col].append((x, float(raw)))
            except ValueError:
                continue
    series.points = {k: v for k, v in series.points.items() if v}
    if not series.points:
        raise DataError("没解析出任何数字")
    return series
