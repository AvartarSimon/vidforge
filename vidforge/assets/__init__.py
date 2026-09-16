"""Asset providers resolve a segment's `source` spec ("pexels:query") into a local file.

Files are downloaded into `<project>/assets/<provider>/` and recorded in an index there,
so a rebuild is deterministic and offline, and the credits list can be pasted into the
video description.
"""

from __future__ import annotations

from ..project import Project, Segment


def resolve_all(project: Project, needed_seconds: dict[str, float] | None = None, log=print) -> None:
    """Fill `image`/`video` for every segment that only has a `source`.

    `needed_seconds` (segment id -> narration length) lets a video provider prefer clips
    long enough to cover the narration without looping.
    """
    pending = [s for s in project.segments if s.needs_asset]
    if not pending:
        return
    from . import pexels
    client = pexels.Pexels(project.root / "assets" / "pexels")
    for seg in pending:
        assert seg.source is not None
        provider, _, query = seg.source.partition(":")
        if provider != "pexels":
            raise ValueError(f"segment {seg.id}: unknown asset provider '{provider}'")
        need = (needed_seconds or {}).get(seg.id, 0.0)
        if seg.source_kind == "video":
            seg.video = client.video(query, min_duration=need, width=project.width)
        else:
            seg.image = client.photo(query, width=project.width)
        log(f"  asset {seg.id:<12} {seg.source_kind} <- {seg.source!r} -> {(seg.video or seg.image).name}")
    client.save()
