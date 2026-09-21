from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import re
from typing import Iterable, List, Sequence, Tuple

from .models import Article, SourceDefinition
from .report import Bar, Kpi, Report, Row, Segment, Signal, Tier
from .sources import FetchResult


@dataclass(frozen=True)
class BriefConfig:
    freshness_hours: int = 24
    limit: int = 5
    max_per_outlet: int = 2


#: Ranking weights, as ``(signal, weight, display label)``. Declared once so the
#: ranker and the renderers cannot drift: the score breakdown shown to a reader
#: is the same arithmetic that produced the ordering.
WEIGHTS = (
    ("global_discussion", 0.30, "discussion"),
    ("significance", 0.28, "significance"),
    ("freshness", 0.20, "freshness"),
    ("evidence", 0.22, "evidence"),
)
#: Flat editorial bonus for non-US lead or impact — added on top, not weighted in.
NON_US_BONUS = 0.12
#: The ceiling a score is measured against.
MAX_SCORE = sum(weight for _, weight, _ in WEIGHTS) + NON_US_BONUS


def _tokens(title: str) -> set:
    return set(re.findall(r"[a-z0-9]+", title.lower()))


def _duplicate(a: Article, b: Article) -> bool:
    if a.event_key and b.event_key:
        return a.event_key == b.event_key
    left, right = _tokens(a.title), _tokens(b.title)
    return bool(left and right and len(left & right) / len(left | right) >= 0.55)


def filter_fresh(articles: Iterable[Article], now: datetime, hours: int) -> List[Article]:
    cutoff = now.astimezone(timezone.utc) - timedelta(hours=hours)
    return [article for article in articles if cutoff <= article.published_at <= now]


def partition_duplicates(articles: Iterable[Article]) -> Tuple[List[Article], List[Tuple[Article, Article]]]:
    """Split into kept articles and ``(dropped, kept_match)`` pairs.

    The first member of each duplicate group survives, so callers must order
    ``articles`` by whatever should win. :func:`prepare` ranks first, which
    makes the highest-scoring account the survivor; de-duplicating an unranked
    list instead keeps whichever source happened to be configured earliest.

    Two outlets filing the same event is corroboration, so which account
    survived — and what was given up to keep it — is worth reporting rather
    than reducing to a count.
    """
    kept: List[Article] = []
    dropped: List[Tuple[Article, Article]] = []
    for article in articles:
        match = next((existing for existing in kept if _duplicate(article, existing)), None)
        if match is None:
            kept.append(article)
        else:
            dropped.append((article, match))
    return kept, dropped


def deduplicate(articles: Iterable[Article]) -> Tuple[List[Article], int]:
    kept, dropped = partition_duplicates(articles)
    return kept, len(dropped)


def rank(articles: Iterable[Article], now: datetime) -> List[Article]:
    ranked = []
    for article in articles:
        age = max(0.0, (now - article.published_at).total_seconds() / 86400)
        freshness = max(0.0, 1.0 - age)
        signals = {
            "global_discussion": min(1.0, article.discussion),
            "significance": min(1.0, max(0.0, article.significance)),
            "freshness": freshness,
            "evidence": min(1.0, max(0.0, article.evidence)),
            "non_us_weight": NON_US_BONUS if article.non_us else 0.0,
        }
        article.score_signals = signals
        article.score = (
            sum(weight * signals[key] for key, weight, _ in WEIGHTS)
            + signals["non_us_weight"]
        )
        ranked.append(article)
    return sorted(ranked, key=lambda item: (-item.score, item.title.lower()))


def select_diverse(ranked: Sequence[Article], config: BriefConfig) -> List[Article]:
    selected: List[Article] = []
    outlets = {}
    regions = set()
    remaining = list(ranked)
    while remaining and len(selected) < config.limit:
        eligible = [
            article for article in remaining
            if outlets.get(article.outlet, 0) < config.max_per_outlet
        ]
        if not eligible:
            break
        # Fill the first three slots with distinct regions when credible options exist.
        if len(selected) < min(config.limit, 3) and regions:
            novel = [article for article in eligible if not regions.intersection(article.regions)]
            article = novel[0] if novel else eligible[0]
        else:
            article = eligible[0]
        selected.append(article)
        outlets[article.outlet] = outlets.get(article.outlet, 0) + 1
        regions.update(article.regions)
        remaining.remove(article)
    return selected


def render_markdown(selected: Sequence[Article], results: Sequence[FetchResult], now: datetime, removed: int, config: BriefConfig) -> str:
    failures = [result.source.name + ": " + result.error for result in results if result.error]
    non_us = sum(article.non_us for article in selected)
    regions = sorted({region for article in selected for region in article.regions})
    lines = [
        "# Daily global AI news brief",
        "",
        "## Report KPIs",
        "- **Generated:** %s" % now.isoformat(),
        "- **Window:** previous %d hours" % config.freshness_hours,
        "- **Scope:** configured global AI news sources",
        "- **Sources:** %d" % len(results),
        "- **Total findings/items:** %d" % len(selected),
        "- **High-priority:** 0",
        "- **Warnings/failures:** %d" % len(failures),
        "",
    ]
    if not selected:
        lines.extend(["No activity to report.", "", "## Coverage and warnings",
                      "- No fresh substantive articles were selected from the configured sources.",
                      "- Unavailable sources: %s" % ("; ".join(failures) if failures else "none reported.")])
        return "\n".join(lines) + "\n"
    for index, article in enumerate(selected, 1):
        signal_text = ", ".join("%s=%.2f" % (key, value) for key, value in article.score_signals.items())
        lines += [
            "## %d. [%s](%s)" % (index, article.title, article.url),
            "",
            "%s" % article.summary,
            "",
            "*%s · %s · %s*  " % (article.outlet, ", ".join(article.regions), ", ".join(article.topics) or "AI"),
            "*Published:* %s  " % article.published_at.isoformat(),
            "*Ranking signals:* %s" % signal_text,
        ]
        if article.primary_url:
            lines.append("*Primary source:* [%s](%s)" % (article.primary_url, article.primary_url))
        if article.uncertainty:
            lines.append("*Uncertainty:* %s" % article.uncertainty)
        lines.append("")
    lines += [
        "---",
        "**Diversity:** %d/%d selected items have a non-US lead or impact; regions represented: %s." % (non_us, len(selected), ", ".join(regions) or "none"),
        "**Not included:** %d duplicate(s)." % removed,
    ]
    if failures:
        lines.append("**Unavailable sources:** %s" % "; ".join(failures))
    return "\n".join(lines) + "\n"


def prepare(sources, fetcher, now=None, config=None):
    """Fetch, filter, de-duplicate, rank, and select. Shared by every renderer.

    Callers needing more than one output format pass the result back in as
    ``prepared`` so sources are never fetched twice.
    """
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    config = config or BriefConfig()
    results = [fetcher.fetch(source) for source in sources]
    all_articles = [article for result in results for article in result.articles]
    fresh = filter_fresh(all_articles, now, config.freshness_hours)
    # Rank before de-duplicating so the strongest account of a corroborated
    # event survives. De-duplicating first kept whichever outlet appeared
    # earliest in the configured source list, which discarded better-evidenced
    # reporting purely because of source ordering.
    ranked = rank(fresh, now)
    unique, dropped = partition_duplicates(ranked)
    stale = [article for article in all_articles if article not in fresh]
    selected = select_diverse(unique, config)
    return results, selected, dropped, stale


def generate_brief(sources: Sequence[SourceDefinition], fetcher, now: datetime = None,
                   config: BriefConfig = None, prepared=None) -> str:
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    config = config or BriefConfig()
    results, selected, dropped, _stale = prepared or prepare(sources, fetcher, now, config)
    return render_markdown(selected, results, now, len(dropped), config)


def _score_meter(article) -> "Bar":
    """The weighted contributions that produced this score, as a composition.

    Widths are percentages of :data:`MAX_SCORE`, so a short bar means a low
    score rather than a differently-shaped one.
    """
    segments = []
    for index, (key, weight, label) in enumerate(WEIGHTS):
        contribution = weight * article.score_signals.get(key, 0.0)
        segments.append(Segment(
            label=label,
            value=contribution / MAX_SCORE * 100.0,
            display="%s %.2f x %.2f = %.2f" % (label, article.score_signals.get(key, 0.0),
                                               weight, contribution),
            slot=index,
        ))
    bonus = article.score_signals.get("non_us_weight", 0.0)
    if bonus:
        # Texture, not hue: the bonus is added on top, not weighted in.
        segments.append(Segment("non-US bonus", bonus / MAX_SCORE * 100.0,
                                "non-US bonus +%.2f" % bonus, len(WEIGHTS), texture=True))
    return Bar(label="Score made of", segments=segments, kind="meter")


def _article_row(article, position, marker) -> Row:
    signals = [Signal(region) for region in article.regions]
    signals.extend(Signal(topic) for topic in article.topics)
    flags = []
    if marker == "up":
        flags.append(Signal("Placed above a higher-scoring item so another region "
                            "would be represented", "positive"))
    if article.uncertainty:
        flags.append(Signal(article.uncertainty, "notable"))
    return Row(
        title=article.title,
        rank=str(position),
        score="%.2f" % article.score,
        marker=marker,
        source=article.outlet,
        summary=article.summary,
        url=article.url,
        when=article.published_at.strftime("%b %d, %H:%M"),
        signals=signals,
        flags=flags,
        meter=_score_meter(article),
    )


def build_brief_report(sources: Sequence[SourceDefinition], fetcher, now: datetime = None,
                       config: BriefConfig = None, prepared=None) -> "Report":
    """Build the structured daily brief.

    The ranking, the diversity rule, and what de-duplication discarded are the
    product of this routine, so all three become structure rather than
    trailing footnotes.
    """
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    config = config or BriefConfig()
    results, selected, dropped, stale = prepared or prepare(sources, fetcher, now, config)
    failures = [result.source.name + ": " + result.error for result in results if result.error]

    # Position is not rank: select_diverse promotes items to widen region
    # coverage, so say which ones moved and why.
    by_score = sorted(selected, key=lambda item: -item.score)
    rows = []
    for position, article in enumerate(selected):
        scored_at = by_score.index(article)
        marker = "up" if position < scored_at else ("down" if position > scored_at else "")
        rows.append(_article_row(article, position + 1, marker))
        if marker == "down":
            rows[-1].flags.append(Signal(
                "Scored %.2f — above the item before it; its region was already represented"
                % article.score))

    # Each dropped duplicate names the account that survived and why.
    considered = []
    for article, kept in dropped:
        detail = ("%s · corroborates the %s account, which ranked higher (%.2f vs %.2f)"
                  % (article.outlet, kept.outlet, kept.score, article.score))
        # Ranking decides the survivor, so a dropped account can still lead on a
        # single signal. Say so rather than letting the trade disappear.
        stronger = []
        if article.evidence > kept.evidence:
            stronger.append("evidence %.2f vs %.2f" % (article.evidence, kept.evidence))
        if article.significance > kept.significance:
            stronger.append("significance %.2f vs %.2f" % (article.significance, kept.significance))
        flags = [Signal("Dropped account still leads on " + ", ".join(stronger), "notable")] if stronger else []
        considered.append(Row(title=article.title, category="duplicate", source=article.outlet,
                              byline=detail, url=article.url, tone="quiet",
                              when=article.published_at.strftime("%b %d, %H:%M"), flags=flags))
    for article in stale:
        considered.append(Row(title=article.title, category="stale", source=article.outlet,
                              byline="Published outside the %d-hour window" % config.freshness_hours,
                              url=article.url, tone="quiet",
                              when=article.published_at.strftime("%b %d, %H:%M")))

    regions = []
    for article in selected:
        for region in article.regions:
            if region not in regions:
                regions.append(region)
    bars = []
    if regions:
        counts = {region: sum(1 for a in selected if region in a.regions) for region in regions}
        bars.append(Bar(
            label="Geographic spread",
            caption="The brief weights non-US coverage, so the spread is a headline",
            kind="categorical",
            segments=[Segment(region, float(counts[region]), region, index)
                      for index, region in enumerate(regions)],
        ))

    non_us = sum(1 for article in selected if article.non_us)
    tiers = []
    if rows:
        tiers.append(Tier(label="Selected", rows=rows, tone="",
                          note="Ordered by score, then adjusted for region diversity"))
    if considered:
        tiers.append(Tier(label="Considered, not selected", rows=considered, tone="quiet",
                          note="What was dropped, and why"))
    return Report(
        title="Daily global AI news brief",
        routine="daily-global-ai-news-brief",
        generated=now.strftime("%b %d, %H:%M UTC"),
        window="Previous %d hours" % config.freshness_hours,
        scopes=["%d configured sources" % len(results)],
        kpis=[
            Kpi("Selected", str(len(selected)), "of %d slots" % config.limit),
            Kpi("Sources", "%d/%d" % (len(results) - len(failures), len(results)), "reachable"),
            Kpi("Non-US", "%d/%d" % (non_us, len(selected)), "lead or impact"),
            Kpi("Regions", str(len(regions)), "represented"),
            Kpi("Deduplicated", str(len(dropped)), "same event, 2 outlets"),
            Kpi("Warnings", str(len(failures)), "source failures",
                "coverage" if failures else ""),
        ],
        bars=bars,
        tiers=tiers,
        alert=("%d of %d sources unavailable — this brief is incomplete"
               % (len(failures), len(results))) if failures else "",
        alert_detail="; ".join(failures),
        boundary=("Read-only fetch of configured sources · every item carries a direct citation · "
                  "ranking weights are fixed and shown · nothing outside the %d-hour window "
                  "was considered." % config.freshness_hours),
        empty_note="No fresh substantive articles were selected from the configured sources.",
    )
