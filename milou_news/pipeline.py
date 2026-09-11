from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import re
from typing import Iterable, List, Sequence, Tuple

from .models import Article, SourceDefinition
from .sources import FetchResult


@dataclass(frozen=True)
class BriefConfig:
    freshness_hours: int = 24
    limit: int = 5
    max_per_outlet: int = 2


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


def deduplicate(articles: Iterable[Article]) -> Tuple[List[Article], int]:
    kept: List[Article] = []
    removed = 0
    for article in articles:
        if any(_duplicate(article, existing) for existing in kept):
            removed += 1
        else:
            kept.append(article)
    return kept, removed


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
            "non_us_weight": 0.12 if article.non_us else 0.0,
        }
        article.score_signals = signals
        article.score = (
            0.30 * signals["global_discussion"]
            + 0.28 * signals["significance"]
            + 0.20 * signals["freshness"]
            + 0.22 * signals["evidence"]
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
        "Generated %s; freshness window: previous %d hours." % (now.date().isoformat(), config.freshness_hours),
        "",
    ]
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


def generate_brief(sources: Sequence[SourceDefinition], fetcher, now: datetime = None, config: BriefConfig = None) -> str:
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    config = config or BriefConfig()
    results = [fetcher.fetch(source) for source in sources]
    all_articles = [article for result in results for article in result.articles]
    fresh = filter_fresh(all_articles, now, config.freshness_hours)
    unique, removed = deduplicate(fresh)
    selected = select_diverse(rank(unique, now), config)
    return render_markdown(selected, results, now, removed, config)
