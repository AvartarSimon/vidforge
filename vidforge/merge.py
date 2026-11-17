"""Saving project.json without losing what someone else wrote in the meantime.

The page keeps the whole project in memory and saved it back whole. Meanwhile the server writes
to the same file itself — a studio take lands as the segment's narration and picture, 小窗⇄全屏,
a template, the jump cut. The page's next autosave then put back its older copy, and the take was
gone from the project a second after it was saved (the files stayed on disk; nothing pointed at
them any more). Measured on a real project: five takes, all five dropped this way.

So a save says what it started from (`base`, the copy the page loaded) and only its own changes
are applied: a three-way merge of base / the page's copy / what is on disk now. Segments are
matched by id. When both sides changed the same field, the page wins — that is the user typing.
"""

from __future__ import annotations

_MISSING = object()


def merge3(base, mine, theirs):
    """`mine` applied onto `theirs`, given that both started from `base`."""
    if mine == base:
        return theirs
    if theirs == base or theirs == mine:
        return mine
    if isinstance(base, dict) and isinstance(mine, dict) and isinstance(theirs, dict):
        out = {}
        for k in list(theirs) + [k for k in mine if k not in theirs]:
            b, m, t = base.get(k, _MISSING), mine.get(k, _MISSING), theirs.get(k, _MISSING)
            v = _merge_value(b, m, t)
            if v is not _MISSING:
                out[k] = v
        return out
    if _by_id(base) and _by_id(mine) and _by_id(theirs):
        return _merge_list(base, mine, theirs)
    return mine                        # both changed one value: the page is the user, and wins


def _merge_value(b, m, t):
    if m is _MISSING and t is _MISSING:
        return _MISSING
    if m is _MISSING:                  # the page has no such key
        return _MISSING if b is not _MISSING and t == b else t      # deleted by the page, untouched since
    if t is _MISSING:                  # not on disk
        return _MISSING if b is not _MISSING and m == b else m      # deleted on disk, untouched by the page
    return merge3(b if b is not _MISSING else None, m, t) if b is not _MISSING else (m if m == t else _new_both(m, t))


def _new_both(m, t):
    """Added on both sides at once: merge dicts, else the page's."""
    if isinstance(m, dict) and isinstance(t, dict):
        return merge3({}, m, t)
    return m


def _by_id(v) -> bool:
    return isinstance(v, list) and all(isinstance(x, dict) and "id" in x for x in v)


def _merge_list(base: list, mine: list, theirs: list) -> list:
    b = {x["id"]: x for x in base}
    m = {x["id"]: x for x in mine}
    t = {x["id"]: x for x in theirs}
    # the page's order when it reordered or added, else the disk's
    order = [x["id"] for x in mine] if [x["id"] for x in mine] != [x["id"] for x in base] else [x["id"] for x in theirs]
    for x in theirs:                   # added on disk meanwhile
        if x["id"] not in b and x["id"] not in order:
            order.append(x["id"])
    out = []
    for i in order:
        if i in m and i in t:
            out.append(merge3(b.get(i, {}), m[i], t[i]) if i in b else _new_both(m[i], t[i]))
        elif i in m:
            if i in b and i not in t and m[i] == b[i]:
                continue               # deleted on disk, untouched by the page
            out.append(m[i])
        elif i in t:
            if i in b and t[i] == b[i]:
                continue               # deleted by the page, untouched on disk
            out.append(t[i])
    return out
