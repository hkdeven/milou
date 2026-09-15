"""Deterministic, read-only planning and dispatch for registered routines."""

from dataclasses import dataclass
from typing import Mapping, Optional, Sequence, Tuple

from .models import RoutineRegistry
from .routines import (generate_commitments_tracker, generate_daily_wins,
                       generate_dependabot_pr_triage, generate_launch_decoder,
                       generate_launch_radar, generate_morning_brief,
                       generate_stale_work_finder,
                       generate_travel_logistics_tracker)
from .github_radar import FixtureApi, RadarConfig, generate_github_radar


def _generate_github_radar_fixture(payload):
    config = RadarConfig.from_mapping(payload.get("config", {}))
    return generate_github_radar(
        FixtureApi(payload.get("responses", {}), payload.get("errors", {})), config
    )


@dataclass(frozen=True)
class PlanStep:
    routine: str
    reason: str
    access: str


@dataclass(frozen=True)
class DispatchResult:
    routine: str
    report: Optional[str]
    error: Optional[str] = None


_HANDLERS = {
    "daily-wins-recap": generate_daily_wins,
    "morning-brief-meeting-prep": generate_morning_brief,
    "commitments-follow-up-tracker": generate_commitments_tracker,
    "stale-work-finder": generate_stale_work_finder,
    "dependabot-pr-triage": generate_dependabot_pr_triage,
    "launch-decoder": generate_launch_decoder,
    "launch-radar": generate_launch_radar,
    "travel-logistics-tracker": generate_travel_logistics_tracker,
    "github-change-radar": _generate_github_radar_fixture,
}


class SupervisorPlanner:
    def __init__(self, registry: RoutineRegistry):
        self.registry = registry

    def plan(self, routines: Sequence[str], reason: str = "requested routine") -> Tuple[PlanStep, ...]:
        steps = []
        for name in routines:
            routine = self.registry.get(name)
            if routine.access != "read-only":
                raise PermissionError("routine is not explicitly read-only: %s" % name)
            if name not in _HANDLERS:
                raise ValueError("no fixture handler registered: %s" % name)
            steps.append(PlanStep(name, reason, routine.access))
        return tuple(steps)

    def scheduled(self, cadence: str) -> Tuple[PlanStep, ...]:
        """Return deterministic read-only work for a declared cadence."""
        names = [name for name in self.registry.names()
                 if self.registry.get(name).schedule == cadence]
        return self.plan(names, reason="declared %s schedule" % cadence)


class SupervisorDispatcher:
    def __init__(self, registry: RoutineRegistry):
        self.planner = SupervisorPlanner(registry)

    def dispatch(self, routine: str, payload: Mapping) -> DispatchResult:
        try:
            if not isinstance(payload, Mapping):
                raise TypeError("payload must be a mapping fixture")
            self.planner.plan((routine,))
            return DispatchResult(routine, _HANDLERS[routine](payload))
        except Exception as exc:  # failure visibility is part of the contract
            return DispatchResult(routine, None, "%s: %s" % (type(exc).__name__, exc))

    def dispatch_plan(self, steps: Sequence[PlanStep], payloads: Mapping[str, Mapping]):
        return tuple(self.dispatch(step.routine, payloads.get(step.routine, {})) for step in steps)
