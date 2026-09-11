import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Iterable, List, Mapping
from urllib.request import Request, urlopen

from .models import Article, SourceDefinition


class SourceFetchError(RuntimeError):
    """A source was unavailable or returned data that cannot be trusted."""


@dataclass
class FetchResult:
    source: SourceDefinition
    articles: List[Article]
    error: str = ""


def _time(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(
            timezone.utc
        )
    except (TypeError, ValueError) as exc:
        raise SourceFetchError("invalid publication time %r" % value) from exc


def parse_articles(payload: object, source: SourceDefinition) -> List[Article]:
    if not isinstance(payload, list):
        raise SourceFetchError("%s requires a JSON array response" % source.name)
    articles: List[Article] = []
    for index, item in enumerate(payload):
        if not isinstance(item, Mapping):
            raise SourceFetchError("%s item %d is not an object" % (source.name, index))
        required = ("title", "url", "published_at", "summary")
        missing = [key for key in required if not item.get(key)]
        if missing:
            raise SourceFetchError(
                "%s item %d missing %s" % (source.name, index, ", ".join(missing))
            )
        try:
            articles.append(
                Article(
                    title=str(item["title"]),
                    url=str(item["url"]),
                    outlet=str(item.get("outlet") or source.name),
                    published_at=_time(str(item["published_at"])),
                    summary=str(item["summary"]),
                    regions=tuple(item.get("regions") or (source.region,)),
                    topics=tuple(item.get("topics") or ()),
                    significance=float(item.get("significance", 0.5)),
                    evidence=float(item.get("evidence", 0.5)),
                    discussion=float(item.get("discussion", 0.0)),
                    non_us=bool(item.get("non_us", source.non_us)),
                    primary_url=item.get("primary_url"),
                    uncertainty=item.get("uncertainty"),
                    event_key=item.get("event_key"),
                )
            )
        except (TypeError, ValueError) as exc:
            raise SourceFetchError("%s item %d has invalid fields" % (source.name, index)) from exc
    return articles


class JsonSourceFetcher:
    """Fetch JSON using GET only; callers can inject a function for tests."""

    def __init__(self, opener: Callable[[str], bytes] = None, timeout: int = 10):
        self.timeout = timeout
        self._opener = opener or self._open

    def _open(self, url: str) -> bytes:
        request = Request(url, headers={"Accept": "application/json"})
        with urlopen(request, timeout=self.timeout) as response:
            return response.read()

    def fetch(self, source: SourceDefinition) -> FetchResult:
        try:
            raw = self._opener(source.url)
            payload = json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else raw)
            return FetchResult(source, parse_articles(payload, source))
        except SourceFetchError as exc:
            return FetchResult(source, [], str(exc))
        except (OSError, TypeError, UnicodeDecodeError, ValueError) as exc:
            # Preserve a clear, bounded source failure without hiding
            # programming errors in the caller or parser.
            return FetchResult(source, [], "%s: %s" % (type(exc).__name__, exc))


class FixtureFetcher:
    def __init__(self, payloads: Mapping[str, object]):
        self.payloads = payloads

    def fetch(self, source: SourceDefinition) -> FetchResult:
        if source.name not in self.payloads:
            return FetchResult(source, [], "fixture missing")
        try:
            return FetchResult(source, parse_articles(self.payloads[source.name], source))
        except SourceFetchError as exc:
            return FetchResult(source, [], str(exc))
        except (TypeError, ValueError, UnicodeDecodeError) as exc:
            return FetchResult(source, [], "%s: %s" % (type(exc).__name__, exc))
