"""Markdown rendering for a structured report.

The stored, quotable record of any report built on :class:`~milou_news.report.Report`.
It keeps the same ordering and tiering the HTML renderer uses, so the two
formats cannot disagree about what a routine found — only about how much
presentation they carry.
"""

from .report import Report


def render_markdown(report: Report) -> str:
    lines = ["# %s" % report.title, ""]
    for label, value in (("Generated", report.generated), ("Window", report.window),
                         ("Scope", ", ".join(report.scopes))):
        if value:
            lines.append("- **%s:** %s" % (label, value))
    lines.append("")
    lines.extend("- **%s:** %s%s" % (kpi.label, kpi.value, " (%s)" % kpi.sub if kpi.sub else "")
                 for kpi in report.kpis)
    lines.append("")
    if report.alert:
        lines.extend(["## Coverage and access", "- %s" % report.alert])
        if report.alert_detail:
            lines.append("- %s" % report.alert_detail)
        lines.append("")
    if not report.populated_tiers():
        lines.extend(["No action needed.", ""])
        if report.empty_note:
            lines.extend(["- %s" % report.empty_note, ""])
    for tier in report.populated_tiers():
        lines.append("## %s (%d)" % (tier.label, tier.count))
        for row in tier.rows:
            suffix = " ([open](%s))" % row.url if row.url.startswith(("http://", "https://")) else ""
            lines.append("- **%s**%s%s%s" % (
                row.title, " — %s" % row.byline if row.byline else "",
                " [%s]" % row.ago if row.ago else "", suffix))
            if row.summary:
                lines.append("  - > %s" % row.summary)
            for flag in row.flags:
                lines.append("  - why: %s" % flag.label)
        if tier.footnote:
            lines.append("- %s" % tier.footnote)
        lines.append("")
    for bar in report.bars:
        lines.append("## %s" % bar.label)
        lines.extend("- %s: %d" % (segment.label, int(segment.value)) for segment in bar.segments)
        lines.append("")
    if report.boundary:
        lines.extend(["## Safety boundary", "- %s" % report.boundary])
    return "\n".join(lines) + "\n"
