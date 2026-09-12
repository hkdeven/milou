from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class SourceDefinition:
    name: str
    url: str
    region: str
    role: str
    non_us: bool = True


@dataclass
class Article:
    title: str
    url: str
    outlet: str
    published_at: datetime
    summary: str
    regions: Tuple[str, ...] = ()
    topics: Tuple[str, ...] = ()
    significance: float = 0.5
    evidence: float = 0.5
    discussion: float = 0.0
    non_us: bool = True
    primary_url: Optional[str] = None
    uncertainty: Optional[str] = None
    event_key: Optional[str] = None
    score: float = field(default=0.0, init=False)
    score_signals: Dict[str, float] = field(default_factory=dict, init=False)


@dataclass(frozen=True)
class Routine:
    name: str
    version: str
    purpose: str
    access: str = "read-only"


class RoutineRegistry:
    def __init__(self) -> None:
        self._routines: Dict[str, Routine] = {}

    def register(self, routine: Routine) -> None:
        if routine.name in self._routines:
            raise ValueError("routine already registered: %s" % routine.name)
        self._routines[routine.name] = routine

    def get(self, name: str) -> Routine:
        return self._routines[name]

    def names(self) -> Tuple[str, ...]:
        return tuple(sorted(self._routines))


NEWS_ROUTINE = Routine(
    "daily-global-ai-news-brief",
    "0.1.0",
    "Produce a concise, cited global AI news brief.",
)

DAILY_WINS_ROUTINE = Routine(
    "daily-wins-recap",
    "0.1.0",
    "Summarize verified accomplishments from structured activity fixtures and separate inferred impact.",
)

MORNING_BRIEF_ROUTINE = Routine(
    "morning-brief-meeting-prep",
    "0.1.0",
    "Prepare read-only, evidence-linked preparation notes for calendar meetings.",
)


def default_registry() -> RoutineRegistry:
    registry = RoutineRegistry()
    registry.register(NEWS_ROUTINE)
    registry.register(DAILY_WINS_ROUTINE)
    registry.register(MORNING_BRIEF_ROUTINE)
    return registry
