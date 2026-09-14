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
    aliases: Tuple[str, ...] = ()
    schedule: str = "on-demand"
    input_kind: str = "fixture"


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
COMMITMENTS_ROUTINE = Routine(
    "commitments-follow-up-tracker", "0.1.0",
    "Detect explicit commitments and suggest read-only follow-up from structured fixtures.",
)
STALE_WORK_ROUTINE = Routine(
    "stale-work-finder", "0.1.0",
    "Find aging authored PRs, reviews, issues, and drafts with cited urgency.",
)
DEPENDABOT_ROUTINE = Routine(
    "dependabot-pr-triage", "0.1.0",
    "Classify dependency updates and recommend safe human review.",
)
LAUNCH_DECODER_ROUTINE = Routine(
    "launch-decoder", "0.1.0",
    "Decode last-24-hour AI and product launches using direct fixture sources, evidence, and uncertainty.",
    aliases=("launch-decoder-24h",), schedule="daily",
)
LAUNCH_RADAR_ROUTINE = Routine(
    "launch-radar", "0.1.0",
    "Track relevant upcoming launches for configured team/user areas with timing, sources, confidence, and unknowns.",
    aliases=("weekly-launch-radar",), schedule="weekly",
)
TRAVEL_LOGISTICS_ROUTINE = Routine(
    "travel-logistics-tracker", "0.1.0",
    "Turn structured conference and travel messages/calendar fixtures into a dated logistics brief.",
    aliases=("travel-logistics",), schedule="on-demand",
)


def default_registry() -> RoutineRegistry:
    registry = RoutineRegistry()
    registry.register(NEWS_ROUTINE)
    registry.register(DAILY_WINS_ROUTINE)
    registry.register(MORNING_BRIEF_ROUTINE)
    registry.register(COMMITMENTS_ROUTINE)
    registry.register(STALE_WORK_ROUTINE)
    registry.register(DEPENDABOT_ROUTINE)
    registry.register(LAUNCH_DECODER_ROUTINE)
    registry.register(LAUNCH_RADAR_ROUTINE)
    registry.register(TRAVEL_LOGISTICS_ROUTINE)
    return registry
