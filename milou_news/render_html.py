"""HTML rendering for structured reports.

The Markdown renderers flatten every record into one sentence and sort purely by
clock. This renderer keeps the structure instead: consequence decides order and
weight, each field gets a column, coverage failures are promoted above the
findings, and boilerplate recedes to a footer.

Colour is reserved. Reserved tones (critical / notable / coverage / positive)
mark state and never decorate; categorical hues are only used where a value
carries identity. Every categorical hue below was verified with the data-viz
validator across all pairs (worst case dE 8.7 under simulated colour-vision
deficiency, 21.2 for normal vision) and every one clears 3:1 on a light
surface. Status colours always pair an icon and a word so hue is never the only
carrier.

No third-party dependencies: the stylesheet is inlined and self-contained.
"""

import html
from typing import Iterable, List, Sequence

from .report import Bar, Report, Row, Tier

#: Validated categorical palette — identity, never magnitude.
CATEGORICAL = ("#1657D9", "#D2600A", "#00915F", "#A0479B")
#: Texture fill for a value that is added on top rather than weighted in.
TEXTURE_INK = "#7A5A05"
#: Sequential ramp — magnitude, ordered light to dark, lightness monotonic.
SEQUENTIAL = ("#0E2F73", "#1657D9", "#5C90EA", "#93B6F3", "#BFD4F9", "#E2EBFD")
#: Label ink per sequential step, so every label clears 4.5:1.
SEQUENTIAL_INK = ("#FFFFFF", "#FFFFFF", "#1D1D1F", "#1D1D1F", "#1D1D1F", "#1D1D1F")

_TONE_INK = {"critical": "#A5232B", "notable": "#7A5A05",
             "coverage": "#8A421D", "positive": "#0E6B33", "quiet": "#6E6E73"}
_TONE_RAIL = {"critical": "#A5232B", "notable": "#C9A227"}

_ICONS = {
    "critical": '<path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line>',
    "notable": '<path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z"></path><line x1="4" y1="22" x2="4" y2="15"></line>',
    "coverage": '<circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line>',
    "positive": '<line x1="12" y1="19" x2="12" y2="5"></line><polyline points="5 12 12 5 19 12"></polyline>',
    "quiet": '<circle cx="12" cy="12" r="9"></circle>',
    "lock": '<rect x="3" y="11" width="18" height="11" rx="2"></rect><path d="M7 11V7a5 5 0 0 1 10 0v4"></path>',
    "link": '<line x1="7" y1="17" x2="17" y2="7"></line><polyline points="7 7 17 7 17 17"></polyline>',
    "empty": '<circle cx="12" cy="12" r="9"></circle><line x1="8.5" y1="12" x2="15.5" y2="12"></line>',
}

STYLES = """
:root{color-scheme:light;
--ground:#F2F2F6;--glass:rgba(255,255,255,.60);--glass-raised:rgba(255,255,255,.78);
--glass-soft:rgba(255,255,255,.44);--hair:rgba(0,0,0,.06);--hair-2:rgba(0,0,0,.04);
--edge:rgba(255,255,255,.72);
--spec:inset 0 1px 0 rgba(255,255,255,.95),inset 0 0 0 1px rgba(255,255,255,.38),inset 0 -1px 0 rgba(255,255,255,.28);
--lift:0 1px 2px rgba(16,24,40,.05),0 14px 34px -12px rgba(16,24,40,.17),0 36px 68px -28px rgba(16,24,40,.15);
--lift-sm:0 1px 2px rgba(16,24,40,.04),0 6px 18px -10px rgba(16,24,40,.12);
--ink-1:#1D1D1F;--ink-2:#5C5C61;--ink-3:#6E6E73;
--crit:#A5232B;--crit-tint:rgba(208,59,59,.10);--crit-edge:rgba(165,35,43,.22);
--note:#7A5A05;--note-tint:rgba(250,178,25,.16);--note-edge:rgba(122,90,5,.20);
--cov:#8A421D;--cov-tint:rgba(236,131,90,.14);--cov-edge:rgba(138,66,29,.22);
--pos:#0E6B33;
--sans:-apple-system,BlinkMacSystemFont,"SF Pro Display","SF Pro Text","Helvetica Neue",system-ui,sans-serif;
--mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
--blur:blur(30px) saturate(205%)}
*{box-sizing:border-box}
body{margin:0;background-color:var(--ground);background-image:
radial-gradient(52% 40% at 8% 2%,rgba(22,87,217,.17),transparent 64%),
radial-gradient(48% 34% at 94% 0%,rgba(160,71,155,.15),transparent 62%),
radial-gradient(46% 38% at 86% 44%,rgba(0,145,95,.14),transparent 62%),
radial-gradient(44% 34% at 4% 60%,rgba(210,96,10,.13),transparent 60%),
radial-gradient(54% 34% at 52% 99%,rgba(22,87,217,.12),transparent 64%);
background-attachment:fixed;color:var(--ink-1);font-family:var(--sans);font-size:15px;
line-height:1.5;-webkit-font-smoothing:antialiased}
a{color:var(--ink-1);text-decoration:none}a:hover{color:var(--crit)}
code{font-family:var(--mono);font-size:.9em}
.wrap{max-width:1220px;margin:0 auto;padding:44px 24px 80px}
@media(max-width:640px){.wrap{padding:28px 16px 56px}}
.glass{background:var(--glass);backdrop-filter:var(--blur);-webkit-backdrop-filter:var(--blur);
border:1px solid var(--edge);border-radius:26px;box-shadow:var(--spec),var(--lift)}
.glass-soft{background:var(--glass-soft);backdrop-filter:blur(20px) saturate(165%);
-webkit-backdrop-filter:blur(20px) saturate(165%);border:1px solid rgba(255,255,255,.72);
box-shadow:var(--spec),var(--lift-sm)}
.report{padding:26px 28px;display:flex;flex-direction:column;gap:16px}
@media(max-width:640px){.report{padding:18px 16px;border-radius:20px}}
.rpt-head{display:flex;align-items:flex-start;gap:24px;flex-wrap:wrap}
.rpt-title{margin:0;font-size:28px;font-weight:600;letter-spacing:-.02em}
.pill{display:inline-flex;align-items:center;gap:6px;height:26px;padding:0 11px;border-radius:999px;
background:rgba(255,255,255,.86);border:1px solid var(--hair);font-size:12.5px;color:var(--ink-2);white-space:nowrap}
.pill-strong{font-weight:600;color:var(--ink-1);background:rgba(255,255,255,.95)}
.pill-ro{height:28px;font-size:11.5px;font-weight:600;letter-spacing:.04em;text-transform:uppercase}
.dv{width:1px;height:16px;background:rgba(0,0,0,.1)}
.small{font-size:12.5px}.xsmall{font-size:11.5px}.muted{color:var(--ink-2)}
.banner{display:flex;align-items:flex-start;gap:12px;padding:14px 18px;border-radius:16px;
background:rgba(255,255,255,.72);backdrop-filter:var(--blur);-webkit-backdrop-filter:var(--blur);
border:1px solid var(--cov-edge);box-shadow:var(--spec),var(--lift-sm)}
.banner-ico{flex:0 0 auto;display:inline-flex;align-items:center;justify-content:center;
width:28px;height:28px;border-radius:999px;background:var(--cov-tint);color:var(--cov)}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px}
.kpi{padding:16px 18px 15px;border-radius:20px;background:var(--glass-raised);
backdrop-filter:var(--blur);-webkit-backdrop-filter:var(--blur);border:1px solid var(--edge);
box-shadow:var(--spec),0 1px 1px rgba(0,0,0,.04),0 8px 22px -14px rgba(0,0,0,.14);
display:flex;flex-direction:column;gap:5px}
.kpi-label{display:inline-flex;align-items:center;gap:5px;font-size:10.5px;font-weight:600;
letter-spacing:.06em;text-transform:uppercase;color:var(--ink-3)}
.kpi-val{font-size:34px;font-weight:600;letter-spacing:-.03em;line-height:1;font-variant-numeric:tabular-nums}
.kpi-sub{font-size:11.5px;color:var(--ink-3)}
.dist{padding:18px 22px 20px;border-radius:20px;display:flex;flex-direction:column;gap:12px}
.dist-bar{display:flex;align-items:stretch;height:30px;gap:2px}
.dist-seg{min-width:0;display:flex;align-items:center;justify-content:center;border-radius:3px;
box-shadow:inset 0 1px 0 rgba(255,255,255,.25)}
.dist-seg:first-child{border-radius:8px 3px 3px 8px}.dist-seg:last-child{border-radius:3px 8px 8px 3px}
.dist-seg span{font-size:12px;font-weight:600;font-variant-numeric:tabular-nums}
.key{display:flex;align-items:center;gap:16px;flex-wrap:wrap}
.key span{display:inline-flex;align-items:center;gap:7px;font-size:12px;color:var(--ink-2)}
.sw{width:9px;height:9px;border-radius:3px;flex:0 0 auto}
.sw-tex{background-color:#7A5A05;background-image:repeating-linear-gradient(45deg,rgba(255,255,255,.55) 0 2px,transparent 2px 4px)}
.tier-head{display:flex;align-items:center;gap:9px;padding:0 4px;margin-bottom:9px;flex-wrap:wrap}
.tier-ico{display:inline-flex;align-items:center;justify-content:center;width:22px;height:22px;
border-radius:999px;flex:0 0 auto}
.tier-name{margin:0;font-size:15px;font-weight:600;letter-spacing:-.01em}
.tier-count{font-size:13px;color:var(--ink-3);font-variant-numeric:tabular-nums}
.tier-note{margin-left:auto;font-size:11.5px;color:var(--ink-3)}
@media(max-width:640px){.tier-note{margin-left:0;flex-basis:100%}}
.rows{border-radius:20px;overflow:hidden;display:flex;flex-direction:column}
.row{display:flex;align-items:stretch;border-bottom:1px solid var(--hair-2)}
.row:last-child{border-bottom:0}
.rail{width:3px;flex:0 0 auto}
.cells{flex:1 1 auto;min-width:0;padding:13px 18px;display:flex;align-items:center;gap:16px}
.c-time{flex:0 0 88px}.c-repo{flex:0 0 200px}.c-type{flex:0 0 118px}
.c-chg{flex:1 1 auto}.c-sig{flex:0 0 180px}
@media(max-width:1100px){.cells{gap:12px}.c-type{display:none}
.c-repo{flex:0 0 160px}.c-sig{flex:0 0 150px}}
@media(max-width:720px){.cells{flex-wrap:wrap;gap:6px 12px;padding:14px 16px}
.c-time,.c-repo,.c-chg,.c-sig{flex:1 1 100%}
.c-time{flex-direction:row;gap:8px;align-items:baseline}}
.c-time{display:flex;flex-direction:column;gap:2px}
.t-rel{font-size:13px;font-weight:600;font-variant-numeric:tabular-nums}
.t-abs{font-size:11px;color:var(--ink-3);font-variant-numeric:tabular-nums}
.c-repo{min-width:0;display:flex;flex-direction:column;gap:1px}
.r-own{font-family:var(--mono);font-size:10.5px;color:var(--ink-3);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.r-nm{font-family:var(--mono);font-size:12.5px;color:var(--ink-1);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.chip-type{display:inline-flex;align-items:center;height:22px;padding:0 9px;border-radius:7px;
background:rgba(0,0,0,.045);font-size:11.5px;font-weight:500;color:var(--ink-2);white-space:nowrap}
.c-chg{min-width:0;display:flex;flex-direction:column;gap:3px}
.c-link{flex:0 0 30px}
.chg-title{font-size:13.5px;font-weight:600;letter-spacing:-.005em}
.chg-by{font-size:11.5px;color:var(--ink-3)}
.c-sig{display:flex;align-items:center;gap:6px;flex-wrap:wrap}
.chip{display:inline-flex;align-items:center;height:21px;padding:0 8px;border-radius:999px;
font-size:11px;font-weight:500;white-space:nowrap;background:rgba(0,0,0,.045);
border:1px solid var(--hair);color:var(--ink-2)}
.chip-critical{background:var(--crit-tint);border-color:var(--crit-edge);color:var(--crit)}
.chip-notable{background:var(--note-tint);border-color:var(--note-edge);color:var(--note)}
.chip-coverage{background:var(--cov-tint);border-color:var(--cov-edge);color:var(--cov)}
.c-link{display:inline-flex;align-items:center;justify-content:center;width:30px;height:30px;
border-radius:9px;flex:0 0 auto;background:rgba(255,255,255,.8);border:1px solid var(--hair);color:var(--ink-2)}
.c-link:hover{background:#fff;color:var(--crit)}
.row-quiet .chg-title{font-weight:400;font-size:12.5px}
.row-quiet .t-rel{font-weight:400;font-size:12.5px;color:var(--ink-2)}
.art-list{display:flex;flex-direction:column;gap:10px}
.art{display:flex;gap:16px;padding:17px 20px;border-radius:20px;background:rgba(255,255,255,.80);
backdrop-filter:var(--blur);-webkit-backdrop-filter:var(--blur);border:1px solid var(--edge);
box-shadow:var(--spec),0 1px 1px rgba(0,0,0,.04),0 8px 22px -16px rgba(0,0,0,.14)}
.art-rank{flex:0 0 30px;display:flex;flex-direction:column;align-items:center;gap:3px}
.rk{display:inline-flex;align-items:center;justify-content:center;width:26px;height:26px;
border-radius:999px;background:rgba(0,0,0,.05);font-size:12.5px;font-weight:700;
font-variant-numeric:tabular-nums;color:var(--ink-2)}
.rk-why{font-size:9px;color:var(--ink-3);line-height:1}
.art-body{flex:1 1 auto;min-width:0;display:flex;flex-direction:column;gap:7px}
.art-top{display:flex;align-items:baseline;gap:14px}
.art-title{flex:1 1 auto;min-width:0;font-size:15.5px;font-weight:600;letter-spacing:-.01em;line-height:1.3}
.art-score{flex:0 0 auto;font-size:17px;font-weight:600;font-variant-numeric:tabular-nums;letter-spacing:-.02em}
.art-meta{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.art-outlet{font-size:12.5px;font-weight:600}
.art-when{font-size:11.5px;color:var(--ink-3);font-variant-numeric:tabular-nums}
.art-sum{margin:0;font-size:13px;line-height:1.55;color:var(--ink-2)}
@media(max-width:640px){.art{padding:14px 16px;gap:12px}.art-top{flex-direction:column;gap:4px}}
.meter{display:flex;height:13px;gap:2px;background:rgba(16,24,40,.05);border-radius:999px;overflow:hidden}
.meter i{display:block;box-shadow:inset 0 1px 0 rgba(255,255,255,.28)}
.meter i:first-child{border-radius:999px 2px 2px 999px}
.meter i.tex{background-color:#7A5A05;background-image:repeating-linear-gradient(45deg,rgba(255,255,255,.45) 0 3px,transparent 3px 6px)}
.flags{display:flex;flex-direction:column;gap:5px}
.quote{margin:0 0 6px;padding-left:10px;border-left:2px solid rgba(0,0,0,.12);
font-size:12.5px;line-height:1.5;color:var(--ink-2)}
.flag{display:inline-flex;align-items:flex-start;gap:6px;font-size:11.5px;line-height:1.45;color:var(--ink-3)}
.flag svg{flex:0 0 auto;margin-top:2px}
.empty{padding:22px;border-radius:16px;background:rgba(255,255,255,.7);border:1px solid var(--hair);
display:flex;flex-direction:column;align-items:center;gap:8px;text-align:center}
.empty-ico{display:inline-flex;align-items:center;justify-content:center;width:34px;height:34px;
border-radius:999px;background:rgba(0,0,0,.04);color:#86868B}
.foot{padding:16px 22px;border-radius:16px;display:flex;align-items:center;gap:24px;flex-wrap:wrap}
.idx{display:flex;flex-direction:column;gap:8px}
.idx-row{display:flex;align-items:center;gap:14px;padding:13px 18px;border-bottom:1px solid var(--hair-2)}
.idx-row:last-child{border-bottom:0}
.idx-when{flex:0 0 150px;font-size:12.5px;font-variant-numeric:tabular-nums;color:var(--ink-2)}
.idx-name{flex:1 1 auto;min-width:0;font-size:13.5px;font-weight:600}
.btn{display:inline-flex;align-items:center;gap:7px;height:32px;padding:0 14px;border-radius:999px;
background:rgba(255,255,255,.85);border:1px solid var(--hair);font:inherit;font-size:12.5px;
font-weight:500;color:var(--ink-1);cursor:pointer}
.btn:hover{background:#fff}
h1.page{margin:0;font-size:34px;font-weight:600;letter-spacing:-.025em}
.eyebrow{margin:0 0 8px;font-size:10.5px;font-weight:600;letter-spacing:.08em;
text-transform:uppercase;color:var(--ink-3)}
.raw{margin:0;font-family:var(--mono);font-size:11.5px;line-height:1.6;color:#4A4A4F;
white-space:pre-wrap;word-break:break-word}
"""


def _e(value) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def _icon(name: str, size: int = 13) -> str:
    body = _ICONS.get(name)
    if not body:
        return ""
    return ('<svg width="%d" height="%d" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            'stroke-width="2.3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
            '%s</svg>' % (size, size, body))


def _segment_fill(segment, kind: str) -> str:
    """Colour for one segment. Texture opts out of hue entirely."""
    if segment.texture:
        return ""
    if kind == "sequential":
        return SEQUENTIAL[segment.slot % len(SEQUENTIAL)]
    return CATEGORICAL[segment.slot % len(CATEGORICAL)]


def _bar(bar: Bar) -> str:
    """A standalone distribution bar with a direct-labelled legend."""
    total = bar.total
    if not bar.segments or total <= 0:
        return ""
    out = ['<div class="glass-soft dist">',
           '<div style="display:flex;align-items:baseline;gap:10px;flex-wrap:wrap">',
           '<span class="kpi-label">%s</span>' % _e(bar.label)]
    if bar.caption:
        out.append('<span class="xsmall muted">%s</span>' % _e(bar.caption))
    out.append('</div><div class="dist-bar">')
    for segment in bar.segments:
        fill = _segment_fill(segment, bar.kind)
        ink = (SEQUENTIAL_INK[segment.slot % len(SEQUENTIAL_INK)]
               if bar.kind == "sequential" else "#FFFFFF")
        label = segment.display or ("%g" % segment.value)
        out.append('<div class="dist-seg" style="flex:%g;background:%s" title="%s">'
                   '<span style="color:%s">%s</span></div>'
                   % (max(segment.value, 0.0001), fill,
                      _e("%s — %g" % (segment.label, segment.value)), ink, _e(label)))
    out.append('</div><div class="key">')
    for segment in bar.segments:
        swatch = ('<i class="sw sw-tex"></i>' if segment.texture
                  else '<i class="sw" style="background:%s"></i>' % _segment_fill(segment, bar.kind))
        out.append('<span>%s%s</span>' % (swatch, _e(segment.label)))
    out.append('</div></div>')
    return "".join(out)


def _meter(bar: Bar) -> str:
    """A composition meter inside a row. Values are percentages of the track."""
    if not bar.segments:
        return ""
    described = ", ".join("%s %s" % (s.label, s.display or ("%g" % s.value)) for s in bar.segments)
    out = ['<div class="meter" role="img" aria-label="%s">' % _e("%s: %s" % (bar.label, described))]
    for segment in bar.segments:
        if segment.texture:
            out.append('<i class="tex" style="width:%.4g%%" title="%s"></i>'
                       % (segment.value, _e(segment.display or segment.label)))
        else:
            out.append('<i style="width:%.4g%%;background:%s" title="%s"></i>'
                       % (segment.value, _segment_fill(segment, "categorical"),
                          _e(segment.display or segment.label)))
    out.append("</div>")
    return "".join(out)


def _meter_key(bar: Bar) -> str:
    if not bar.segments:
        return ""
    out = ['<div class="key" style="padding:0 4px 10px">',
           '<span class="kpi-label" style="margin-right:4px">%s</span>' % _e(bar.label)]
    for segment in bar.segments:
        swatch = ('<i class="sw sw-tex"></i>' if segment.texture
                  else '<i class="sw" style="background:%s"></i>' % _segment_fill(segment, "categorical"))
        out.append('<span>%s%s</span>' % (swatch, _e(segment.label)))
    out.append("</div>")
    return "".join(out)


def _chips(signals: Iterable) -> str:
    return "".join('<span class="chip%s">%s</span>'
                   % ((" chip-" + s.tone) if s.tone in _TONE_INK else "", _e(s.label))
                   for s in signals)


def _flags(flags: Iterable) -> str:
    items = list(flags)
    if not items:
        return ""
    out = ['<div class="flags">']
    for flag in items:
        ink = _TONE_INK.get(flag.tone, "")
        style = ' style="color:%s"' % ink if ink else ""
        out.append('<span class="flag"%s>%s%s</span>'
                   % (style, _icon(flag.tone, 11) if flag.tone in _ICONS else "", _e(flag.label)))
    out.append("</div>")
    return "".join(out)


def _link(url: str) -> str:
    if not url.startswith(("http://", "https://")):
        return '<span class="c-link" style="border:0;background:none"></span>'
    return ('<a class="c-link" href="%s" rel="noopener noreferrer" aria-label="Open source">%s</a>'
            % (_e(url), _icon("link", 14)))


def _event_row(row: Row) -> str:
    """A record row: time, source, type, change, signals, citation."""
    rail = _TONE_RAIL.get(row.tone, "")
    quiet = " row-quiet" if row.tone == "quiet" else ""
    source = ""
    if row.owner or row.source:
        source = ('<div class="c-repo">%s%s</div>'
                  % ('<span class="r-own">%s/</span>' % _e(row.owner) if row.owner else "",
                     '<span class="r-nm">%s</span>' % _e(row.source) if row.source else ""))
    flags = _flags(row.flags)
    quoted = ('<p class="quote">%s</p>' % _e(row.summary)) if row.summary else ""
    below = quoted + flags
    return ('<div class="row%s"><div class="rail" style="background:%s"></div>'
            '<div style="flex:1 1 auto;min-width:0"><div class="cells">'
            '%s%s%s'
            '<div class="c-chg"><span class="chg-title">%s</span>%s</div>'
            '%s%s</div>%s</div></div>'
            % (quiet, rail or "transparent",
               ('<div class="c-time"><span class="t-rel">%s</span>%s</div>'
                % (_e(row.ago),
                   '<span class="t-abs">%s</span>' % _e(row.when) if row.when else "")
                ) if (row.ago or row.when) else "",
               source,
               ('<div class="c-type"><span class="chip-type">%s</span></div>'
                % _e(row.category)) if row.category else "",
               _e(row.title),
               '<span class="chg-by">%s</span>' % _e(row.byline) if row.byline else "",
               '<div class="c-sig">%s</div>' % _chips(row.signals) if row.signals else "",
               _link(row.url),
               '<div style="padding:0 18px 12px">%s</div>' % below if below else ""))


def _ranked_row(row: Row) -> str:
    """A ranked article card: rank, score, meter, flags."""
    meta = []
    if row.source:
        meta.append('<span class="art-outlet">%s</span>' % _e(row.source))
    meta.extend('<span class="chip">%s</span>' % _e(s.label) for s in row.signals)
    when = " · ".join(x for x in (row.ago, row.when) if x)
    if when:
        meta.append('<span class="art-when">%s</span>' % _e(when))
    title = ('<a class="art-title" href="%s" rel="noopener noreferrer">%s</a>'
             % (_e(row.url), _e(row.title)) if row.url.startswith(("http://", "https://"))
             else '<span class="art-title">%s</span>' % _e(row.title))
    marker = {"up": "&#9650;", "down": "&#9660;"}.get(row.marker, "")
    return ('<article class="art"><div class="art-rank"><span class="rk">%s</span>%s</div>'
            '<div class="art-body"><div class="art-top">%s%s</div>'
            '<div class="art-meta">%s</div>%s%s%s</div></article>'
            % (_e(row.rank), '<span class="rk-why">%s</span>' % marker if marker else "",
               title,
               '<span class="art-score">%s</span>' % _e(row.score) if row.score else "",
               "".join(meta),
               '<p class="art-sum">%s</p>' % _e(row.summary) if row.summary else "",
               _meter(row.meter) if row.meter else "",
               _flags(row.flags)))


def _tier(tier: Tier, ranked: bool) -> str:
    ink = _TONE_INK.get(tier.tone, "var(--ink-2)")
    tint = {"critical": "var(--crit-tint)", "notable": "var(--note-tint)"}.get(
        tier.tone, "rgba(0,0,0,.05)")
    head = ('<div class="tier-head"><span class="tier-ico" style="background:%s;color:%s">%s</span>'
            '<h3 class="tier-name" style="color:%s">%s</h3>'
            '<span class="tier-count">%d</span>%s</div>'
            % (tint, ink, _icon(tier.tone or "quiet"), ink, _e(tier.label), tier.count,
               '<span class="tier-note">%s</span>' % _e(tier.note) if tier.note else ""))
    if ranked:
        key = _meter_key(tier.rows[0].meter) if tier.rows and tier.rows[0].meter else ""
        body = '%s<div class="art-list">%s</div>' % (
            key, "".join(_ranked_row(row) for row in tier.rows))
    else:
        shade = "glass-soft" if tier.tone == "quiet" else "glass"
        body = '<div class="rows %s">%s</div>' % (
            shade, "".join(_event_row(row) for row in tier.rows))
    foot = ('<div style="padding:11px 18px"><span class="xsmall muted">%s</span></div>'
            % _e(tier.footnote)) if tier.footnote else ""
    return "<div>%s%s%s</div>" % (head, body, foot)


def render_report(report: Report) -> str:
    """Render one structured report as the report body (no document shell)."""
    scopes = "".join('<span class="pill%s">%s</span>'
                     % (" pill-strong" if index == 0 else "", _e(scope))
                     for index, scope in enumerate(report.scopes))
    meta = []
    if report.window:
        meta.append(_e(report.window))
    if report.generated:
        meta.append("to " + _e(report.generated))
    out = ['<div class="glass report">',
           '<div class="rpt-head">',
           '<div style="flex:1 1 320px;min-width:0;display:flex;flex-direction:column;gap:10px">',
           '<h2 class="rpt-title">%s</h2>' % _e(report.title),
           '<div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">%s%s%s</div>'
           % (scopes, '<span class="dv"></span>' if scopes and meta else "",
              '<span class="small muted">%s</span>' % " · ".join(meta) if meta else ""),
           '</div>',
           '<span class="pill pill-ro">%s Read-only</span>' % _icon("lock", 12),
           '</div>']

    if report.alert:
        out.append('<div class="banner"><span class="banner-ico">%s</span>'
                   '<div style="flex:1 1 auto;min-width:0;display:flex;flex-direction:column;gap:2px">'
                   '<span class="small" style="font-weight:600;color:var(--cov)">%s</span>%s</div></div>'
                   % (_icon("coverage", 15), _e(report.alert),
                      '<span class="small muted">%s</span>' % _e(report.alert_detail)
                      if report.alert_detail else ""))

    if report.kpis:
        tiles = []
        for kpi in report.kpis:
            ink = _TONE_INK.get(kpi.tone, "")
            edge = {"critical": "var(--crit-edge)", "notable": "var(--note-edge)",
                    "coverage": "var(--cov-edge)"}.get(kpi.tone, "")
            tiles.append('<div class="kpi"%s><span class="kpi-label"%s>%s%s</span>'
                         '<span class="kpi-val"%s>%s</span>%s</div>'
                         % (' style="border-color:%s"' % edge if edge else "",
                            ' style="color:%s"' % ink if ink else "",
                            _icon(kpi.tone, 11) if kpi.tone in _ICONS else "", _e(kpi.label),
                            ' style="color:%s"' % ink if ink else "", _e(kpi.value),
                            '<span class="kpi-sub">%s</span>' % _e(kpi.sub) if kpi.sub else ""))
        out.append('<div class="kpis">%s</div>' % "".join(tiles))

    out.extend(_bar(bar) for bar in report.bars)

    populated = report.populated_tiers()
    if populated:
        for tier in populated:
            out.append(_tier(tier, ranked=any(row.meter for row in tier.rows)))
    else:
        out.append('<div class="empty"><span class="empty-ico">%s</span>'
                   '<span class="small" style="font-weight:600">No activity to report</span>%s</div>'
                   % (_icon("empty", 17),
                      '<span class="xsmall muted">%s</span>' % _e(report.empty_note)
                      if report.empty_note else ""))

    if report.boundary:
        out.append('<div class="glass-soft foot">'
                   '<div style="flex:1 1 320px;min-width:0;display:flex;flex-direction:column;gap:4px">'
                   '<span class="kpi-label">Scope &amp; boundary</span>'
                   '<span class="small muted" style="line-height:1.5">%s</span></div></div>'
                   % _e(report.boundary))
    out.append("</div>")
    return "".join(out)


def document(title: str, body: str) -> str:
    """Wrap rendered content in a self-contained page."""
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            '<title>%s</title><style>%s</style></head><body><div class="wrap">%s</div></body></html>'
            % (_e(title), STYLES, body))


def report_page(report: Report, back: str = "/") -> str:
    """A full page for one report."""
    header = ('<p class="eyebrow">Milou report</p>'
              '<div style="display:flex;align-items:baseline;gap:16px;flex-wrap:wrap;margin-bottom:22px">'
              '<h1 class="page">%s</h1><a class="btn" href="%s">All reports</a></div>'
              % (_e(report.title), _e(back)))
    return document("Milou — " + report.title, header + render_report(report))


def markdown_page(title: str, status: str, markdown: str, back: str = "/") -> str:
    """Fallback page for a stored report with no structured payload."""
    header = ('<p class="eyebrow">Milou report · %s</p>'
              '<div style="display:flex;align-items:baseline;gap:16px;flex-wrap:wrap;margin-bottom:22px">'
              '<h1 class="page">%s</h1><a class="btn" href="%s">All reports</a></div>'
              % (_e(status), _e(title), _e(back)))
    body = ('<div class="glass report"><p class="small muted">Stored before structured '
            'reports were introduced — shown as captured.</p><pre class="raw">%s</pre></div>'
            % _e(markdown))
    return document("Milou — " + title, header + body)


def login_page(message: str = "") -> str:
    """The sign-in form. The token is never echoed back into the page."""
    notice = ('<div class="banner" style="margin-bottom:16px"><span class="banner-ico">%s</span>'
              '<span class="small" style="font-weight:600;color:var(--cov)">%s</span></div>'
              % (_icon("coverage", 15), _e(message))) if message else ""
    body = ('<div style="max-width:420px;margin:6vh auto 0">'
            '<p class="eyebrow">Milou</p><h1 class="page" style="margin-bottom:22px">Reports</h1>'
            '%s<div class="glass report">'
            '<form method="post" action="/login" style="display:flex;flex-direction:column;gap:12px">'
            '<label for="token" class="kpi-label">Report token</label>'
            '<input id="token" name="token" type="password" autocomplete="current-password" required '
            'style="height:40px;padding:0 14px;border-radius:12px;border:1px solid var(--hair);'
            'background:rgba(255,255,255,.9);font:inherit;font-size:14px;color:var(--ink-1)">'
            '<button type="submit" class="btn" style="height:40px;justify-content:center">Sign in</button>'
            '</form></div></div>' % notice)
    return document("Milou login", body)


def index_page(entries: Sequence[dict]) -> str:
    """The archive index."""
    rows: List[str] = []
    for entry in entries:
        rows.append('<div class="idx-row"><span class="idx-when">%s</span>'
                    '<a class="idx-name" href="%s">%s</a>'
                    '<span class="chip">%s</span></div>'
                    % (_e(entry.get("generated_at", "")), _e(entry.get("href", "#")),
                       _e(entry.get("routine", "report")), _e(entry.get("status", "stored"))))
    body = ('<p class="eyebrow">Milou</p>'
            '<div style="display:flex;align-items:baseline;gap:16px;flex-wrap:wrap;margin-bottom:22px">'
            '<h1 class="page">Reports</h1>'
            '<span class="small muted">%d stored</span></div>'
            '<div class="glass report">%s</div>'
            '<form method="post" action="/logout" style="margin-top:20px">'
            '<button type="submit" class="btn">Sign out</button></form>'
            % (len(entries),
               '<div class="rows glass-soft">%s</div>' % "".join(rows) if rows
               else '<div class="empty"><span class="empty-ico">%s</span>'
                    '<span class="small" style="font-weight:600">No reports stored yet</span></div>'
                    % _icon("empty", 17)))
    return document("Milou reports", body)
