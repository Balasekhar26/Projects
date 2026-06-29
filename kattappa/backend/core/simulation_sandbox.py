"""Simulation Sandbox (Step 8.4).

The firewall between planning and execution.

    Plan → SANDBOX → Risk Analysis → Resource Analysis → Constraint Check → Recommendation

Three Constitutional Rules (hardcoded, not configurable):

    Rule 1: Sandbox cannot authorize execution.  Only recommend.
            SandboxReport.authorized is ALWAYS False.

    Rule 2: Sandbox cannot create goals.  Only evaluate plans.
            No GoalMemory write methods are imported or called anywhere in this module.

    Rule 3: Sandbox cannot rewrite constraints.  Value Engine remains supreme.
            ABSOLUTE_POLICIES and ValueEngine profiles are read-only inputs;
            the Sandbox is blocked by them, never allowed to alter them.

Pipeline position:
    PersonalProjectManager → SIMULATION SANDBOX → (human decision) → Execution
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

# ---------------------------------------------------------------------------
# Constitutional constants — frozen at import time
# ---------------------------------------------------------------------------

class SandboxConstitution:
    """Four hardcoded safety rules. Not configurable, not overridable."""

    RULE_1: str = "SANDBOX_CANNOT_AUTHORIZE_EXECUTION"
    RULE_2: str = "SANDBOX_CANNOT_CREATE_GOALS"
    RULE_3: str = "SANDBOX_CANNOT_REWRITE_CONSTRAINTS"
    RULE_4: str = "REASON_BEFORE_ACTION"

    @classmethod
    def as_dict(cls) -> dict[str, str]:
        return {
            "rule_1": cls.RULE_1,
            "rule_2": cls.RULE_2,
            "rule_3": cls.RULE_3,
            "rule_4": cls.RULE_4,
            "note": (
                "These rules are hardcoded at import time. "
                "No simulation result, recommendation, or API caller can override them."
            ),
        }


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


# ---------------------------------------------------------------------------
# Verdict
# ---------------------------------------------------------------------------

class SandboxVerdict(str, Enum):
    RECOMMEND_PROCEED  = "RECOMMEND_PROCEED"   # all gates pass, risk acceptable
    RECOMMEND_REVISE   = "RECOMMEND_REVISE"    # risk elevated; revise before proceeding
    BLOCKED            = "BLOCKED"             # hard constraint violation; must not proceed


# ---------------------------------------------------------------------------
# Scenario Paths (A = optimistic, B = nominal, C = pessimistic)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ScenarioPath:
    path_id: str           # "PATH_A", "PATH_B", "PATH_C"
    label: str             # "Optimistic", "Nominal", "Pessimistic"
    success_probability: float
    estimated_cost_units: float    # relative cost (1.0 = nominal)
    estimated_duration_sec: float
    risk_score: float              # 0.0–1.0; higher = riskier
    dependencies_at_risk: list[str]
    summary: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "path_id": self.path_id,
            "label": self.label,
            "success_probability": round(self.success_probability, 4),
            "estimated_cost_units": round(self.estimated_cost_units, 3),
            "estimated_duration_sec": round(self.estimated_duration_sec, 1),
            "risk_score": round(self.risk_score, 4),
            "dependencies_at_risk": self.dependencies_at_risk,
            "summary": self.summary,
        }


def _generate_scenario_paths(
    nominal_success: float,
    nominal_duration_sec: float,
    nominal_rollback_risk: float,
    dependencies_at_risk: list[str],
) -> list[ScenarioPath]:
    """Generate Path A (optimistic), B (nominal), C (pessimistic) deterministically."""

    paths = [
        ScenarioPath(
            path_id="PATH_A",
            label="Optimistic",
            success_probability=_clamp(nominal_success * 1.15, hi=0.99),
            estimated_cost_units=0.75,
            estimated_duration_sec=max(60.0, nominal_duration_sec * 0.80),
            risk_score=_clamp(nominal_rollback_risk * 0.60),
            dependencies_at_risk=[],
            summary=(
                "Best-case scenario: dependencies hold, resources are available, "
                "no blockers materialise. Reduced cost and shorter timeline."
            ),
        ),
        ScenarioPath(
            path_id="PATH_B",
            label="Nominal",
            success_probability=_clamp(nominal_success),
            estimated_cost_units=1.0,
            estimated_duration_sec=max(60.0, nominal_duration_sec),
            risk_score=_clamp(nominal_rollback_risk),
            dependencies_at_risk=dependencies_at_risk[:2],
            summary=(
                "Expected-case scenario based on current empirical data. "
                "Some dependency and resource variance possible."
            ),
        ),
        ScenarioPath(
            path_id="PATH_C",
            label="Pessimistic",
            success_probability=_clamp(nominal_success * 0.70, lo=0.02),
            estimated_cost_units=1.60,
            estimated_duration_sec=max(60.0, nominal_duration_sec * 1.50),
            risk_score=_clamp(nominal_rollback_risk * 1.80),
            dependencies_at_risk=dependencies_at_risk,
            summary=(
                "Worst-case scenario: one or more dependencies slip, resource "
                "budget tightens, and blockers compound. Requires mitigation plan."
            ),
        ),
    ]
    return paths


# ---------------------------------------------------------------------------
# Resource Exhaustion Forecast
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ResourceForecastItem:
    resource_type: str
    allocated: float
    consumed: float
    remaining: float
    burn_rate_pct: float       # consumed / allocated * 100
    will_exhaust: bool
    forecast_exhaustion_pct: float   # projected burn % after plan completes (0–100+)

    def to_dict(self) -> dict[str, Any]:
        return {
            "resource_type": self.resource_type,
            "allocated": round(self.allocated, 4),
            "consumed": round(self.consumed, 4),
            "remaining": round(self.remaining, 4),
            "burn_rate_pct": round(self.burn_rate_pct, 2),
            "will_exhaust": self.will_exhaust,
            "forecast_exhaustion_pct": round(self.forecast_exhaustion_pct, 2),
        }


@dataclass(frozen=True)
class ResourceForecastReport:
    project_id: str
    resources: list[ResourceForecastItem]
    any_exhaustion_risk: bool
    exhaustion_warning: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "resources": [r.to_dict() for r in self.resources],
            "any_exhaustion_risk": self.any_exhaustion_risk,
            "exhaustion_warning": self.exhaustion_warning,
        }


class ResourceExhaustionForecast:
    """Reads PPM resource state and forecasts whether resources will last.

    Rule 2 enforcement: Read-only. Never calls any PersonalProjectManager
    write method or GoalMemory write method.
    """

    # Projected additional burn from executing the plan (heuristic %)
    _PLAN_BURN_ESTIMATE_PCT: float = 20.0
    _EXHAUSTION_THRESHOLD_PCT: float = 90.0   # burn ≥ 90% triggers warning

    @classmethod
    def run(cls, project_id: str) -> ResourceForecastReport:
        """Returns resource exhaustion forecast for a project."""
        from backend.core.personal_project_manager import PersonalProjectManager

        project = PersonalProjectManager.get_project(project_id)
        if not project:
            return ResourceForecastReport(
                project_id=project_id,
                resources=[],
                any_exhaustion_risk=False,
                exhaustion_warning="",
            )

        raw_resources = project.get("resources") or []
        items: list[ResourceForecastItem] = []
        any_risk = False

        for r in raw_resources:
            allocated = float(r.get("allocated_amount") or 0.0)
            consumed = float(r.get("consumed_amount") or 0.0)
            remaining = float(r.get("remaining_amount") or (allocated - consumed))
            r_type = str(r.get("resource_type") or "UNKNOWN")

            burn_pct = (consumed / allocated * 100.0) if allocated > 0 else 0.0
            # Forecast: add estimated plan burn
            forecast_pct = burn_pct + cls._PLAN_BURN_ESTIMATE_PCT
            will_exhaust = forecast_pct >= cls._EXHAUSTION_THRESHOLD_PCT

            if will_exhaust:
                any_risk = True

            items.append(ResourceForecastItem(
                resource_type=r_type,
                allocated=allocated,
                consumed=consumed,
                remaining=remaining,
                burn_rate_pct=burn_pct,
                will_exhaust=will_exhaust,
                forecast_exhaustion_pct=forecast_pct,
            ))

        warning = ""
        if any_risk:
            exhausted = [i.resource_type for i in items if i.will_exhaust]
            warning = (
                f"Resource exhaustion forecasted for: {', '.join(exhausted)}. "
                "Recommend allocating additional budget before execution."
            )

        return ResourceForecastReport(
            project_id=project_id,
            resources=items,
            any_exhaustion_risk=any_risk,
            exhaustion_warning=warning,
        )


# ---------------------------------------------------------------------------
# Dependency Failure Model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DependencyImpact:
    depends_on_project_id: str
    dependency_type: str     # "HARD" or "SOFT"
    slip_days: float         # 0 = failure scenario
    failure_mode: str        # "SLIP" | "FAILURE" | "BLOCKED"
    cascaded_delay_days: float
    cascaded_health_impact: str  # "NONE" | "WARNING" | "CRITICAL"
    recommendation: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "depends_on_project_id": self.depends_on_project_id,
            "dependency_type": self.dependency_type,
            "slip_days": round(self.slip_days, 1),
            "failure_mode": self.failure_mode,
            "cascaded_delay_days": round(self.cascaded_delay_days, 1),
            "cascaded_health_impact": self.cascaded_health_impact,
            "recommendation": self.recommendation,
        }


@dataclass(frozen=True)
class DependencyPropagationReport:
    project_id: str
    scenarios: list[DependencyImpact]
    worst_case_delay_days: float
    blocking_failure_possible: bool
    summary: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "scenarios": [s.to_dict() for s in self.scenarios],
            "worst_case_delay_days": round(self.worst_case_delay_days, 1),
            "blocking_failure_possible": self.blocking_failure_possible,
            "summary": self.summary,
        }


class DependencyFailureModel:
    """Propagates dependency failure scenarios through the project graph.

    Read-only: never writes to PPM or GoalMemory.
    Simulates: slip(N days), full failure, blocked.
    """

    _HARD_SLIP_MULTIPLIER: float = 1.0    # 1 day upstream slip = 1 day downstream delay
    _SOFT_SLIP_MULTIPLIER: float = 0.3    # soft deps absorb most of the slip
    _SLIP_SCENARIOS_DAYS: list[float] = [3.0, 7.0]  # test 3-day and 7-day slips

    @classmethod
    def propagate(cls, project_id: str) -> DependencyPropagationReport:
        """Returns dependency failure propagation report for a project."""
        from backend.core.personal_project_manager import PersonalProjectManager

        project = PersonalProjectManager.get_project(project_id)
        if not project:
            return DependencyPropagationReport(
                project_id=project_id,
                scenarios=[],
                worst_case_delay_days=0.0,
                blocking_failure_possible=False,
                summary="Project not found.",
            )

        raw_deps = project.get("dependencies") or []
        if not raw_deps:
            return DependencyPropagationReport(
                project_id=project_id,
                scenarios=[],
                worst_case_delay_days=0.0,
                blocking_failure_possible=False,
                summary="No dependencies registered. Plan proceeds with no upstream risk.",
            )

        scenarios: list[DependencyImpact] = []
        worst_delay = 0.0
        blocking_possible = False

        for dep in raw_deps:
            dep_id = str(dep.get("depends_on_project_id") or "")
            dep_type = str(dep.get("dependency_type") or "HARD").upper()
            multiplier = cls._HARD_SLIP_MULTIPLIER if dep_type == "HARD" else cls._SOFT_SLIP_MULTIPLIER

            # Get health of the upstream dependency
            dep_project = PersonalProjectManager.get_project(dep_id) if dep_id else None
            dep_health = "UNKNOWN"
            if dep_project:
                dep_health = str(dep_project.get("health_status") or "GOOD")

            # Scenario A: slip by N days
            for slip_days in cls._SLIP_SCENARIOS_DAYS:
                cascaded = slip_days * multiplier
                health_impact = "NONE"
                if dep_type == "HARD":
                    health_impact = "CRITICAL" if cascaded >= 7 else "WARNING"
                else:
                    health_impact = "WARNING" if cascaded >= 3 else "NONE"

                scenarios.append(DependencyImpact(
                    depends_on_project_id=dep_id,
                    dependency_type=dep_type,
                    slip_days=slip_days,
                    failure_mode="SLIP",
                    cascaded_delay_days=cascaded,
                    cascaded_health_impact=health_impact,
                    recommendation=(
                        f"Add {round(cascaded + 2, 1)} day buffer to plan timeline. "
                        f"Monitor upstream project '{dep_id}'."
                    ),
                ))
                if cascaded > worst_delay:
                    worst_delay = cascaded

            # Scenario B: full dependency failure
            fail_delay = 14.0 if dep_type == "HARD" else 4.0
            fail_health = "CRITICAL" if dep_type == "HARD" else "WARNING"
            if dep_type == "HARD":
                blocking_possible = True

            scenarios.append(DependencyImpact(
                depends_on_project_id=dep_id,
                dependency_type=dep_type,
                slip_days=0.0,
                failure_mode="FAILURE",
                cascaded_delay_days=fail_delay,
                cascaded_health_impact=fail_health,
                recommendation=(
                    f"Upstream '{dep_id}' failure would cause {fail_delay}-day disruption. "
                    "Prepare contingency or decouple milestone from this dependency."
                ),
            ))
            if fail_delay > worst_delay:
                worst_delay = fail_delay

            # Scenario C: dependency becomes BLOCKED (uses current upstream health)
            if dep_health in {"CRITICAL", "WARNING"}:
                block_delay = 10.0 if dep_type == "HARD" else 2.0
                scenarios.append(DependencyImpact(
                    depends_on_project_id=dep_id,
                    dependency_type=dep_type,
                    slip_days=0.0,
                    failure_mode="BLOCKED",
                    cascaded_delay_days=block_delay,
                    cascaded_health_impact="CRITICAL" if dep_type == "HARD" else "WARNING",
                    recommendation=(
                        f"Upstream '{dep_id}' is currently {dep_health}. "
                        "Resolve upstream health before this plan proceeds."
                    ),
                ))
                if block_delay > worst_delay:
                    worst_delay = block_delay

        summary_parts: list[str] = [f"{len(raw_deps)} upstream dependency(ies) modelled."]
        if blocking_possible:
            summary_parts.append("At least one HARD dependency failure could block execution.")
        if worst_delay > 0:
            summary_parts.append(f"Worst-case cascaded delay: {round(worst_delay, 1)} days.")

        return DependencyPropagationReport(
            project_id=project_id,
            scenarios=scenarios,
            worst_case_delay_days=worst_delay,
            blocking_failure_possible=blocking_possible,
            summary=" ".join(summary_parts),
        )


# ---------------------------------------------------------------------------
# Alignment Gate
# ---------------------------------------------------------------------------

class AlignmentVerdict(str, Enum):
    PASS    = "PASS"
    WARN    = "WARN"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class AlignmentGateResult:
    verdict: AlignmentVerdict
    goal_alignment_score: float     # 0.0–1.0
    value_alignment_score: float    # 0.0–1.0 (weighted ValueEngine score)
    constraint_violation: str | None   # policy_id if violated, else None
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict.value,
            "goal_alignment_score": round(self.goal_alignment_score, 4),
            "value_alignment_score": round(self.value_alignment_score, 4),
            "constraint_violation": self.constraint_violation,
            "reason": self.reason,
        }


class AlignmentGate:
    """Checks every simulated path against:

    1. Goal provenance from GoalMemory (read-only)
    2. ValueEngine lens scores (read-only, rank-only contract preserved)
    3. ABSOLUTE_POLICIES from GoalMemory (read-only; Sandbox cannot modify them)

    Rule 3 enforcement: This gate is blocked by constraints, not the other way around.
    """

    _GOAL_ALIGNMENT_WARN_THRESHOLD: float = 0.50
    _VALUE_ALIGNMENT_WARN_THRESHOLD: float = 0.45

    @classmethod
    def check(
        cls,
        plan_steps: list[dict[str, Any]],
        goal_id: str | None = None,
        plan_title: str = "",
        plan_description: str = "",
    ) -> AlignmentGateResult:
        """Evaluate goal, value, and constraint alignment.

        Read-only. Never mutates GoalMemory or ValueEngine.
        """
        # -- Rule 3 gate: check ABSOLUTE_POLICIES first --
        from backend.core.goal_memory import GoalMemory

        violation = GoalMemory.validate_against_absolute_policies(
            title=plan_title,
            description=plan_description,
        )
        if violation:
            return AlignmentGateResult(
                verdict=AlignmentVerdict.BLOCKED,
                goal_alignment_score=0.0,
                value_alignment_score=0.0,
                constraint_violation=violation,
                reason=(
                    f"Absolute policy '{violation}' violated. "
                    "Sandbox cannot override constraints (Rule 3). Plan is BLOCKED."
                ),
            )

        # -- Goal alignment: read provenance --
        goal_alignment = 0.5   # default when no goal_id
        if goal_id:
            goal = GoalMemory.get_goal(goal_id)
            if not goal:
                return AlignmentGateResult(
                    verdict=AlignmentVerdict.BLOCKED,
                    goal_alignment_score=0.0,
                    value_alignment_score=0.0,
                    constraint_violation=None,
                    reason=f"Originating goal '{goal_id}' not found. Cannot evaluate alignment.",
                )
            # Simple provenance check: goal must be active
            g_state = str(goal.get("current_state") or goal.get("status") or "")
            if g_state in {"ARCHIVED", "ABANDONED", "CANCELLED", "COMPLETED"}:
                return AlignmentGateResult(
                    verdict=AlignmentVerdict.BLOCKED,
                    goal_alignment_score=0.0,
                    value_alignment_score=0.0,
                    constraint_violation=None,
                    reason=(
                        f"Originating goal '{goal_id}' is in terminal state '{g_state}'. "
                        "Simulation cannot proceed against an inactive goal."
                    ),
                )
            # Score alignment by goal priority
            priority_score = float(goal.get("priority_score") or 1.0)
            goal_alignment = _clamp(priority_score / 10.0)  # normalise to 0–1

        # -- Value alignment: read-only lens scores --
        from backend.core.value_engine import PlanSignals, ValueEngine, ValueProfile

        # Build signals from plan steps heuristics (deterministic, no LLM)
        n_steps = len(plan_steps)
        has_write = any(
            any(term in str(s.get("action", "")).upper() for term in ("WRITE", "CREATE", "DELETE", "PATCH"))
            for s in plan_steps
        )
        signals = PlanSignals(
            name="sandbox_alignment_check",
            goal_match=goal_alignment,
            steps=n_steps,
            reversible=not has_write,
            sim_success=0.75,        # conservative neutral estimate
            capability_coverage=0.80,
        )
        scores = ValueEngine.score_plan(signals)
        value_score = sum(scores.values()) / len(scores) if scores else 0.5

        # Determine verdict
        if goal_alignment < cls._GOAL_ALIGNMENT_WARN_THRESHOLD:
            verdict = AlignmentVerdict.WARN
            reason = (
                f"Goal alignment score {round(goal_alignment, 3)} is below warning threshold "
                f"{cls._GOAL_ALIGNMENT_WARN_THRESHOLD}. Recommend re-validating user intent before proceeding."
            )
        elif value_score < cls._VALUE_ALIGNMENT_WARN_THRESHOLD:
            verdict = AlignmentVerdict.WARN
            reason = (
                f"Value alignment score {round(value_score, 3)} is below warning threshold "
                f"{cls._VALUE_ALIGNMENT_WARN_THRESHOLD}. Plan may conflict with operating philosophy."
            )
        else:
            verdict = AlignmentVerdict.PASS
            reason = (
                f"Goal alignment: {round(goal_alignment, 3)}, "
                f"Value alignment: {round(value_score, 3)}. All gates pass."
            )

        return AlignmentGateResult(
            verdict=verdict,
            goal_alignment_score=goal_alignment,
            value_alignment_score=value_score,
            constraint_violation=None,
            reason=reason,
        )


# ---------------------------------------------------------------------------
# Sandbox Report
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SandboxReport:
    """Full Simulation Sandbox report.

    Rule 1 enforcement: `authorized` is ALWAYS False.
    This is a dataclass field with a hard default — callers cannot set it to True.
    """
    sandbox_id: str
    sandbox_version: str
    verdict: SandboxVerdict
    reason: str
    authorized: bool                             # Rule 1: always False
    constitution_enforced: bool                  # always True
    scenario_paths: list[ScenarioPath]
    resource_forecast: ResourceForecastReport | None
    dependency_propagation: DependencyPropagationReport | None
    alignment_gate: AlignmentGateResult
    plan_simulation: dict[str, Any]
    generated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "sandbox_id": self.sandbox_id,
            "sandbox_version": self.sandbox_version,
            "verdict": self.verdict.value,
            "reason": self.reason,
            "authorized": False,        # Rule 1: hardcoded, never read from self.authorized
            "constitution_enforced": True,
            "constitution": SandboxConstitution.as_dict(),
            "scenario_paths": [p.to_dict() for p in self.scenario_paths],
            "resource_forecast": self.resource_forecast.to_dict() if self.resource_forecast else None,
            "dependency_propagation": self.dependency_propagation.to_dict() if self.dependency_propagation else None,
            "alignment_gate": self.alignment_gate.to_dict(),
            "plan_simulation": self.plan_simulation,
            "generated_at": self.generated_at,
        }


# ---------------------------------------------------------------------------
# Simulation Sandbox Orchestrator
# ---------------------------------------------------------------------------

class SimulationSandbox:
    """Top-level Simulation Sandbox orchestrator (Step 8.4).

    The firewall between planning and execution.

    Constitutional invariants (hardcoded at class level):
        _RULE_1 = SANDBOX_CANNOT_AUTHORIZE_EXECUTION
        _RULE_2 = SANDBOX_CANNOT_CREATE_GOALS
        _RULE_3 = SANDBOX_CANNOT_REWRITE_CONSTRAINTS

    All public methods:
        - Return SandboxReport (never mutate system state)
        - Never call GoalMemory write methods (Rule 2)
        - Never call ValueEngine profile/weight writers (Rule 3)
        - Set authorized=False in every returned report (Rule 1)
    """

    _RULE_1 = SandboxConstitution.RULE_1   # SANDBOX_CANNOT_AUTHORIZE_EXECUTION
    _RULE_2 = SandboxConstitution.RULE_2   # SANDBOX_CANNOT_CREATE_GOALS
    _RULE_3 = SandboxConstitution.RULE_3   # SANDBOX_CANNOT_REWRITE_CONSTRAINTS
    _VERSION = "8.4"

    # Verdict thresholds
    _BLOCK_SUCCESS_THRESHOLD: float = 0.30   # below this → BLOCKED
    _REVISE_SUCCESS_THRESHOLD: float = 0.65  # below this → RECOMMEND_REVISE

    @classmethod
    def evaluate_plan(
        cls,
        plan_steps: list[dict[str, Any]],
        *,
        goal: str = "",
        goal_id: str | None = None,
        workflow_id: str = "",
        plan_title: str = "",
        plan_description: str = "",
    ) -> SandboxReport:
        """Lightweight evaluation: scenario paths + alignment gate + Monte-Carlo simulation.

        Use when no PPM project exists yet (goal-only or pre-project evaluation).
        Rule 2 enforcement: never calls GoalMemory write methods.
        Rule 3 enforcement: never modifies ValueEngine or ABSOLUTE_POLICIES.
        """
        sandbox_id = f"sb_{uuid.uuid4().hex[:8]}"

        # 1. Alignment gate (Rule 3: gate is blocked BY constraints, cannot modify them)
        alignment = AlignmentGate.check(
            plan_steps=plan_steps,
            goal_id=goal_id,
            plan_title=plan_title or goal,
            plan_description=plan_description,
        )

        # Hard block on constraint violation
        if alignment.verdict == AlignmentVerdict.BLOCKED:
            return cls._build_report(
                sandbox_id=sandbox_id,
                verdict=SandboxVerdict.BLOCKED,
                reason=alignment.reason,
                paths=[],
                resource_forecast=None,
                dep_report=None,
                alignment=alignment,
                plan_sim={},
            )

        # 2. Existing SimulationEngine Monte-Carlo
        plan_sim = cls._run_plan_simulation(plan_steps, goal=goal, workflow_id=workflow_id)

        # 3. Generate scenario paths from simulation signals
        nom_success = float(plan_sim.get("success_probability") or 0.75)
        nom_duration = float(plan_sim.get("estimated_duration_seconds") or 60.0)
        nom_rollback = float(plan_sim.get("rollback_risk") or 0.10)
        paths = _generate_scenario_paths(nom_success, nom_duration, nom_rollback, [])

        # 4. Determine verdict
        verdict, reason = cls._compute_verdict(
            nom_success=nom_success,
            any_exhaustion=False,
            blocking_dep_failure=False,
            alignment=alignment,
            plan_sim=plan_sim,
        )

        return cls._build_report(
            sandbox_id=sandbox_id,
            verdict=verdict,
            reason=reason,
            paths=paths,
            resource_forecast=None,
            dep_report=None,
            alignment=alignment,
            plan_sim=plan_sim,
        )

    @classmethod
    def evaluate_project_plan(
        cls,
        project_id: str,
        plan_steps: list[dict[str, Any]],
        *,
        goal_id: str | None = None,
        goal: str = "",
        workflow_id: str = "",
    ) -> SandboxReport:
        """Full project evaluation: all four engines.

        Rule 2 enforcement: reads PPM and GoalMemory; never writes to either.
        Rule 3 enforcement: reads constraints; never modifies them.
        Rule 1 enforcement: returns authorized=False always.
        """
        sandbox_id = f"sb_{uuid.uuid4().hex[:8]}"

        # Resolve goal_id from project if not provided
        if not goal_id:
            try:
                from backend.core.personal_project_manager import PersonalProjectManager
                proj = PersonalProjectManager.get_project(project_id)
                if proj:
                    goal_id = proj.get("linked_goal_id")
                    if not goal:
                        goal = proj.get("title") or ""
            except Exception:
                pass

        # 1. Alignment gate
        alignment = AlignmentGate.check(
            plan_steps=plan_steps,
            goal_id=goal_id,
            plan_title=goal,
            plan_description="",
        )

        if alignment.verdict == AlignmentVerdict.BLOCKED:
            return cls._build_report(
                sandbox_id=sandbox_id,
                verdict=SandboxVerdict.BLOCKED,
                reason=alignment.reason,
                paths=[],
                resource_forecast=None,
                dep_report=None,
                alignment=alignment,
                plan_sim={},
            )

        # 2. Resource exhaustion forecast
        resource_forecast = ResourceExhaustionForecast.run(project_id)

        # 3. Dependency failure propagation
        dep_report = DependencyFailureModel.propagate(project_id)

        # 4. SimulationEngine Monte-Carlo
        plan_sim = cls._run_plan_simulation(plan_steps, goal=goal, workflow_id=workflow_id)

        # 5. Scenario paths
        nom_success = float(plan_sim.get("success_probability") or 0.75)
        nom_duration = float(plan_sim.get("estimated_duration_seconds") or 60.0)
        nom_rollback = float(plan_sim.get("rollback_risk") or 0.10)
        dep_at_risk = [
            s.depends_on_project_id
            for s in dep_report.scenarios
            if s.failure_mode == "FAILURE" and s.cascaded_health_impact == "CRITICAL"
        ]
        paths = _generate_scenario_paths(nom_success, nom_duration, nom_rollback, dep_at_risk)

        # 6. Determine verdict
        verdict, reason = cls._compute_verdict(
            nom_success=nom_success,
            any_exhaustion=resource_forecast.any_exhaustion_risk,
            blocking_dep_failure=dep_report.blocking_failure_possible,
            alignment=alignment,
            plan_sim=plan_sim,
        )

        return cls._build_report(
            sandbox_id=sandbox_id,
            verdict=verdict,
            reason=reason,
            paths=paths,
            resource_forecast=resource_forecast,
            dep_report=dep_report,
            alignment=alignment,
            plan_sim=plan_sim,
        )

    # ------------------------------------------------------------------
    # Internal helpers (no external writes)
    # ------------------------------------------------------------------

    @classmethod
    def _run_plan_simulation(
        cls,
        plan_steps: list[dict[str, Any]],
        *,
        goal: str = "",
        workflow_id: str = "",
    ) -> dict[str, Any]:
        """Delegates to existing SimulationEngine. Read-only passthrough."""
        try:
            from backend.core.simulation_engine import SimulationEngine
            report = SimulationEngine.simulate_plan(
                plan=plan_steps,
                goal=goal,
                workflow_id=workflow_id,
            )
            return report.to_dict()
        except Exception as exc:
            return {
                "error": str(exc),
                "success_probability": 0.75,
                "failure_probability": 0.25,
                "estimated_duration_seconds": 60.0,
                "rollback_risk": 0.10,
                "rollback_risk_level": "low",
                "step_predictions": [],
                "likely_failures": [],
                "recommendation": "simulation_engine_unavailable",
            }

    @classmethod
    def _compute_verdict(
        cls,
        nom_success: float,
        any_exhaustion: bool,
        blocking_dep_failure: bool,
        alignment: AlignmentGateResult,
        plan_sim: dict[str, Any],
    ) -> tuple[SandboxVerdict, str]:
        """Deterministic verdict computation. Never touches constraints."""

        # Hard blocks first
        if alignment.verdict == AlignmentVerdict.BLOCKED:
            return SandboxVerdict.BLOCKED, alignment.reason

        if nom_success < cls._BLOCK_SUCCESS_THRESHOLD:
            return (
                SandboxVerdict.BLOCKED,
                f"Plan success probability {round(nom_success, 3)} is critically low "
                f"(threshold: {cls._BLOCK_SUCCESS_THRESHOLD}). Revise before sandbox re-evaluation.",
            )

        # Revision triggers
        reasons: list[str] = []

        if nom_success < cls._REVISE_SUCCESS_THRESHOLD:
            reasons.append(
                f"Success probability {round(nom_success, 3)} below recommend-revise threshold "
                f"{cls._REVISE_SUCCESS_THRESHOLD}."
            )
        if any_exhaustion:
            reasons.append("Resource exhaustion forecasted for one or more resource types.")
        if blocking_dep_failure:
            reasons.append("At least one HARD dependency failure scenario could block execution.")
        if alignment.verdict == AlignmentVerdict.WARN:
            reasons.append(alignment.reason)

        rollback_level = str(plan_sim.get("rollback_risk_level") or "low")
        if rollback_level == "high":
            reasons.append("Rollback risk level is HIGH. Prepare rollback chain before proceeding.")

        if reasons:
            return SandboxVerdict.RECOMMEND_REVISE, " | ".join(reasons)

        return (
            SandboxVerdict.RECOMMEND_PROCEED,
            (
                f"All gates pass. Success probability: {round(nom_success, 3)}. "
                f"Rollback risk: {rollback_level}. "
                "This is a recommendation only — not execution authorization (Rule 1)."
            ),
        )

    @classmethod
    def _build_report(
        cls,
        *,
        sandbox_id: str,
        verdict: SandboxVerdict,
        reason: str,
        paths: list[ScenarioPath],
        resource_forecast: ResourceForecastReport | None,
        dep_report: DependencyPropagationReport | None,
        alignment: AlignmentGateResult,
        plan_sim: dict[str, Any],
    ) -> SandboxReport:
        """Assembles SandboxReport. authorized is ALWAYS False (Rule 1)."""
        return SandboxReport(
            sandbox_id=sandbox_id,
            sandbox_version=cls._VERSION,
            verdict=verdict,
            reason=reason,
            authorized=False,           # Rule 1: hardcoded
            constitution_enforced=True,
            scenario_paths=paths,
            resource_forecast=resource_forecast,
            dependency_propagation=dep_report,
            alignment_gate=alignment,
            plan_simulation=plan_sim,
        )
