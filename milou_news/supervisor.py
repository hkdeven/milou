"""Deterministic, read-only planning and dispatch for registered routines."""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Mapping, Optional, Sequence, Tuple

from .models import RoutineRegistry
from .report import Report
from .routines import (build_routine_report, generate_commitments_tracker,
                       generate_daily_wins, generate_dependabot_pr_triage,
                       generate_launch_decoder, generate_launch_radar,
                       generate_morning_brief, generate_stale_work_finder,
                       generate_travel_logistics_tracker)
from .github_radar import (FixtureApi, RadarConfig, build_radar_report,
                           generate_github_radar, prepare as prepare_radar)
from .outlook import (FixtureGraph, InboxConfig, build_outlook_report,
                      generate_outlook_monitor)


def _generate_github_radar_fixture(payload):
    config = RadarConfig.from_mapping(payload.get("config", {}))
    api = FixtureApi(payload.get("responses", {}), payload.get("errors", {}))
    now = datetime.now(timezone.utc)
    # Collect once; both formats describe the same bounded result set.
    prepared = prepare_radar(api, config, now)
    return (generate_github_radar(api, config, now, prepared=prepared),
            build_radar_report(api, config, now, prepared=prepared))


def _generate_outlook_fixture(payload):
    config = InboxConfig.from_mapping(payload.get("config", {}))
    api = FixtureGraph(payload.get("responses", {}), payload.get("errors", {}))
    report = build_outlook_report(api, config)
    return generate_outlook_monitor(api, config, report=report), report


def _fixture_handler(generate, routine):
    """Pair a Markdown generator with its structured builder for one routine."""
    def handler(payload):
        return generate(payload), build_routine_report(routine, payload)
    return handler


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
    structured: Optional[Report] = None


_HANDLERS = {
    name: _fixture_handler(generate, name) for name, generate in (
        ("daily-wins-recap", generate_daily_wins),
        ("morning-brief-meeting-prep", generate_morning_brief),
        ("commitments-follow-up-tracker", generate_commitments_tracker),
        ("stale-work-finder", generate_stale_work_finder),
        ("dependabot-pr-triage", generate_dependabot_pr_triage),
        ("launch-decoder", generate_launch_decoder),
        ("launch-radar", generate_launch_radar),
        ("travel-logistics-tracker", generate_travel_logistics_tracker),
    )
}
_HANDLERS["github-change-radar"] = _generate_github_radar_fixture
_HANDLERS["outlook-inbox-monitor"] = _generate_outlook_fixture


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
            markdown, structured = _HANDLERS[routine](payload)
            return DispatchResult(routine, markdown, structured=structured)
        except Exception as exc:  # failure visibility is part of the contract
            return DispatchResult(routine, None, "%s: %s" % (type(exc).__name__, exc))

    def dispatch_plan(self, steps: Sequence[PlanStep], payloads: Mapping[str, Mapping]):
        return tuple(self.dispatch(step.routine, payloads.get(step.routine, {})) for step in steps)
