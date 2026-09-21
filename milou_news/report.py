"""Structured report model shared by every renderer.

Routines already compute structured records and then flatten them into prose.
This module is the intermediate the flattening used to skip: generators build a
:class:`Report`, and each renderer decides how much of that structure to keep.
Markdown keeps the text; HTML keeps the ordering, tiers, and signals too.

The model is deliberately plain data so a report can be stored as JSON and
re-rendered later without re-running the routine.
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import List, Mapping, Optional

#: Tier/tone vocabulary. ``""`` is neutral; the rest map to reserved colours.
TONES = ("", "critical", "notable", "coverage", "positive", "quiet")

def _clean(value) -> str:
    return "" if value is None else str(value)


def humanize_age(then: datetime, now: datetime) -> str:
    """A short relative age. Readers scan "14h ago" faster than an ISO stamp."""
    if then is None or now is None:
        return ""
    seconds = max(0, int((now - then).total_seconds()))
    if seconds < 3600:
        return "%dm ago" % max(1, seconds // 60)
    if seconds < 86400:
        return "%dh ago" % (seconds // 3600)
    return "%dd ago" % (seconds // 86400)


@dataclass
class Kpi:
    """One headline number."""

    label: str
    value: str
    sub: str = ""
    tone: str = ""


@dataclass
class Signal:
    """A short chip: a label, optionally carrying a reserved tone."""

    label: str
    tone: str = ""


@dataclass
class Segment:
    """One slice of a bar. ``slot`` indexes the palette; ``texture`` opts out of hue."""

    label: str
    value: float
    display: str = ""
    slot: int = 0
    texture: bool = False


@dataclass
class Bar:
    """A distribution or composition bar.

    ``kind`` is ``"sequential"`` for magnitude breakdowns (one hue, light to
    dark, ordered) or ``"categorical"`` for identity (distinct validated hues).
    """

    label: str
    segments: List[Segment] = field(default_factory=list)
    caption: str = ""
    kind: str = "sequential"

    @property
    def total(self) -> float:
        return sum(segment.value for segment in self.segments)


@dataclass
class Row:
    """One finding. Every field has a home in the rendered row."""

    title: str
    ago: str = ""
    when: str = ""
    owner: str = ""
    source: str = ""
    category: str = ""
    byline: str = ""
    summary: str = ""
    url: str = ""
    tone: str = ""
    rank: str = ""
    score: str = ""
    marker: str = ""
    signals: List[Signal] = field(default_factory=list)
    flags: List[Signal] = field(default_factory=list)
    meter: Optional[Bar] = None


@dataclass
class Tier:
    """A group of rows sharing a consequence level."""

    label: str
    rows: List[Row] = field(default_factory=list)
    note: str = ""
    tone: str = ""
    footnote: str = ""

    @property
    def count(self) -> int:
        return len(self.rows)


@dataclass
class Report:
    """A whole rendered report, independent of output format."""

    title: str
    routine: str
    generated: str = ""
    window: str = ""
    scopes: List[str] = field(default_factory=list)
    kpis: List[Kpi] = field(default_factory=list)
    bars: List[Bar] = field(default_factory=list)
    tiers: List[Tier] = field(default_factory=list)
    alert: str = ""
    alert_detail: str = ""
    boundary: str = ""
    empty_note: str = ""

    @property
    def total_rows(self) -> int:
        return sum(tier.count for tier in self.tiers)

    @property
    def is_empty(self) -> bool:
        return self.total_rows == 0

    def populated_tiers(self) -> List[Tier]:
        """Tiers that actually carry rows — empty sections never render."""
        return [tier for tier in self.tiers if tier.rows]

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: Mapping) -> "Report":
        """Rebuild a report from stored JSON, tolerating unknown/missing keys."""
        if not isinstance(payload, Mapping):
            raise ValueError("report payload must be a mapping")

        def signals(items) -> List[Signal]:
            return [Signal(_clean(x.get("label")), _clean(x.get("tone")))
                    for x in (items or []) if isinstance(x, Mapping)]

        def bar(value) -> Optional[Bar]:
            if not isinstance(value, Mapping):
                return None
            segments = [
                Segment(_clean(s.get("label")), float(s.get("value") or 0.0),
                        _clean(s.get("display")), int(s.get("slot") or 0),
                        bool(s.get("texture")))
                for s in (value.get("segments") or []) if isinstance(s, Mapping)
            ]
            return Bar(_clean(value.get("label")), segments,
                       _clean(value.get("caption")),
                       _clean(value.get("kind")) or "sequential")

        def row(value) -> Row:
            return Row(
                title=_clean(value.get("title")), ago=_clean(value.get("ago")),
                when=_clean(value.get("when")), owner=_clean(value.get("owner")),
                source=_clean(value.get("source")), category=_clean(value.get("category")),
                byline=_clean(value.get("byline")), summary=_clean(value.get("summary")),
                url=_clean(value.get("url")), tone=_clean(value.get("tone")),
                rank=_clean(value.get("rank")), score=_clean(value.get("score")),
                marker=_clean(value.get("marker")),
                signals=signals(value.get("signals")), flags=signals(value.get("flags")),
                meter=bar(value.get("meter")),
            )

        tiers = []
        for item in payload.get("tiers") or []:
            if not isinstance(item, Mapping):
                continue
            tiers.append(Tier(
                label=_clean(item.get("label")),
                rows=[row(r) for r in (item.get("rows") or []) if isinstance(r, Mapping)],
                note=_clean(item.get("note")), tone=_clean(item.get("tone")),
                footnote=_clean(item.get("footnote")),
            ))
        return cls(
            title=_clean(payload.get("title")) or "Report",
            routine=_clean(payload.get("routine")),
            generated=_clean(payload.get("generated")), window=_clean(payload.get("window")),
            scopes=[_clean(x) for x in (payload.get("scopes") or [])],
            kpis=[Kpi(_clean(k.get("label")), _clean(k.get("value")), _clean(k.get("sub")),
                      _clean(k.get("tone")))
                  for k in (payload.get("kpis") or []) if isinstance(k, Mapping)],
            bars=[b for b in (bar(x) for x in (payload.get("bars") or [])) if b],
            tiers=tiers,
            alert=_clean(payload.get("alert")), alert_detail=_clean(payload.get("alert_detail")),
            boundary=_clean(payload.get("boundary")), empty_note=_clean(payload.get("empty_note")),
        )
