"""Simulation Engine — Phase K16.5.

Evaluates candidate execution plans by simulating outcome state transitions,
predicting risks and utility values using the World Model, and returning
the optimal plan branch.
"""
from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from backend.core.config import runtime_data_root  # noqa: F401 – re-exported for monkeypatching
from backend.core.logger import log_event

logger = logging.getLogger(__name__)


@dataclass
class SimulationBranchResult:
    branch_id: str
    steps: List[Dict[str, Any]]
    expected_utility: float  # Score from 0.0 to 1.0
    predicted_risk: float  # Score from 0.0 to 1.0
    completion_probability: float  # Score from 0.0 to 1.0
    reason: str


class SimulationEngine:
    """Simulates plan scenarios and computes optimal execution paths."""
    REVIEW_THRESHOLD = 0.10

    @classmethod
    def simulate_plans(
        cls,
        candidate_plans: List[Dict[str, Any]],
        world_state_context: Dict[str, Any]
    ) -> List[SimulationBranchResult]:
        """Simulates outcome state transitions for candidate plans."""
        log_event("simulation_engine_start", f"Simulating {len(candidate_plans)} plan branches")
        results = []

        for idx, plan in enumerate(candidate_plans):
            branch_id = plan.get("id") or f"branch-{idx}"
            steps = plan.get("steps") or []
            
            # Predict outcome per step using mock/transient World Model transitions
            accumulated_risk = 0.0
            accumulated_utility = 1.0
            failures = 0

            for step in steps:
                action = step.get("action", "").lower()
                
                # Simple rule-based prediction transitions:
                # 1. Shell commands carry execution risks
                if "shell" in action or "terminal" in action:
                    accumulated_risk += 0.25
                # 2. Deleting files carries high risk
                if "delete" in action or "remove" in action:
                    accumulated_risk += 0.40
                # 3. Actions with invalid params degrade completion probability
                if not step.get("params"):
                    accumulated_utility *= 0.8
                    failures += 1

            # Normalize risk and compute completion probability
            predicted_risk = min(1.0, accumulated_risk)
            completion_prob = max(0.0, 1.0 - (failures * 0.3))
            
            # Utility = (completion_prob * (1 - risk)) * goal_alignment
            expected_utility = completion_prob * (1.0 - (predicted_risk * 0.5))

            results.append(
                SimulationBranchResult(
                    branch_id=branch_id,
                    steps=steps,
                    expected_utility=round(expected_utility, 3),
                    predicted_risk=round(predicted_risk, 3),
                    completion_probability=round(completion_prob, 3),
                    reason=f"Risk: {predicted_risk:.2f}, Completion Probability: {completion_prob:.2f}"
                )
            )

        # Sort branches descending by expected utility
        results.sort(key=lambda b: b.expected_utility, reverse=True)
        
        if results:
            log_event("simulation_engine_complete", f"Best branch: {results[0].branch_id} (utility={results[0].expected_utility})")
        return results

    @classmethod
    def get_best_plan(
        cls,
        candidate_plans: List[Dict[str, Any]],
        world_state_context: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Simulates all candidates and returns the plan dict with highest utility."""
        branches = cls.simulate_plans(candidate_plans, world_state_context)
        if not branches:
            return None
        
        best_branch = branches[0]
        # Locate the original plan dict matching best branch id
        for plan in candidate_plans:
            if plan.get("id") == best_branch.branch_id:
                # Inject simulation metadata
                plan["simulation"] = {
                    "expected_utility": best_branch.expected_utility,
                    "predicted_risk": best_branch.predicted_risk,
                    "completion_probability": best_branch.completion_probability,
                    "reason": best_branch.reason
                }
                return plan
        return candidate_plans[0]

    @classmethod
    def simulate(cls, scenario: Scenario, *, trials: int = 1000, seed: int = 42) -> SimulationReport:
        rng = random.Random(seed)
        success = 0
        fail_attrib: dict[str, int] = {r.name: 0 for r in scenario.risks}

        for _ in range(trials):
            failed = False
            cause: str | None = None
            if rng.random() > scenario.base_success_prob:
                failed = True  # base uncertainty (unattributed)
            for r in scenario.risks:
                occurred = rng.random() < r.probability
                if occurred and rng.random() < r.impact:
                    if not failed:
                        cause = r.name
                    failed = True
            if failed:
                if cause is not None:
                    fail_attrib[cause] += 1
            else:
                success += 1

        success_rate = success / trials if trials else 0.0
        failure_rate = 1.0 - success_rate
        top_risks = sorted(
            ({"risk": name, "failure_contribution": round(count / trials, 4)}
             for name, count in fail_attrib.items() if count > 0),
            key=lambda d: d["failure_contribution"], reverse=True,
        )
        if failure_rate > cls.REVIEW_THRESHOLD:
            recommendation = "human review advised: failure risk exceeds threshold"
        else:
            recommendation = "acceptable risk: proceed to validation"
        return SimulationReport(
            scenario=scenario.name, trials=trials, seed=seed,
            success_rate=success_rate, failure_rate=failure_rate,
            top_risks=top_risks, recommendation=recommendation,
        )

    @classmethod
    def simulate_dict(cls, raw: dict[str, Any], *, trials: int = 1000, seed: int = 42) -> SimulationReport:
        return cls.simulate(Scenario.from_dict(raw), trials=trials, seed=seed)

    # ------------------------------------------------------------------
    # Extended API — Phase K17+
    # ------------------------------------------------------------------

    # Default action durations (ms) and agent cost multipliers
    _ACTION_DURATIONS: Dict[str, int] = {
        "SEARCH_WEB": 2000,
        "READ_FILE": 1000,
        "WRITE_FILE": 2000,
        "CREATE_FILE": 1500,
        "DELETE_FILE": 500,
        "RUN_TESTS": 5000,
        "EXECUTE_SHELL": 3000,
        "DEPLOY": 8000,
        "BUILD": 6000,
        "ANALYZE": 3000,
        "PLAN": 2000,
        "REVIEW": 2500,
        "UNKNOWN": 2000,
    }

    _AGENT_MULTIPLIERS: Dict[str, float] = {
        "coder": 1.5,
        "browser": 0.8,
        "planner": 1.0,
        "tester": 1.3,
        "reviewer": 1.1,
        "deployer": 2.0,
        "unknown": 1.0,
    }

    # Global calibration modifier — updated by recalibrate_from_ledger()
    _calibration_modifier: float = 1.0

    @staticmethod
    def _wilson_interval(successes: int, total: int, confidence: float = 0.95) -> tuple[float, float]:
        """Compute Wilson score confidence interval for a Bernoulli proportion.

        Returns (low, high) where both are in [0.0, 1.0]. When total == 0,
        returns (0.0, 1.0) indicating maximum uncertainty.
        """
        import math
        if total == 0:
            return 0.0, 1.0
        # z-score for 95% confidence
        z = 1.96
        p = successes / total
        denom = 1.0 + z * z / total
        center = (p + z * z / (2 * total)) / denom
        half = (z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total))) / denom
        low = max(0.0, center - half)
        high = min(1.0, center + half)
        return round(low, 4), round(high, 4)

    @classmethod
    def _predict_step(
        cls,
        step: "PlanStep",
        active_policies: List[Any],
        reflection_agent_stats: Dict[str, Any],
        reflection_recommendations: List[Any],
        context: Dict[str, Any],
        workflow_step_overrides: Dict[str, Dict[str, Any]] | None = None,
    ) -> tuple["StepPrediction", List[str], List[str]]:
        """Predict outcome metrics for a single plan step.

        Returns (prediction, warnings, failure_reasons).
        """
        from backend.core.action_memory import ActionMemory
        from backend.core.simulation_calibration import SimulationCalibrator

        action = step.action.upper()
        agent = step.agent.lower()

        # Check for workflow-level per-step override (from WorkflowMemory goal lookup)
        step_key = f"{agent}:{action}"
        override = (workflow_step_overrides or {}).get(step_key)
        if override and override["total"] > 0:
            total = override["total"]
            succ = override["successes"]
            rollback_count_override = override["rollback_count"]
            # Apply Bayesian prior with prior_total=3, prior_successes=2, prior_rollback=0.65
            base_success = (succ + 2) / (total + 3)
            evidence_count = total
            rollback_risk = (rollback_count_override + 0.65) / (total + 3)
        else:
            # Look up empirical action-level stats from ActionMemory
            try:
                stats = ActionMemory.get_action_type_statistics(action)
            except Exception:
                stats = {}

            total = int(stats.get("total_executions") or 0)
            succ = int(stats.get("success_count") or 0)

            if total > 0:
                low, high = cls._wilson_interval(succ, total)
                base_success = (low + high) / 2.0
                evidence_count = total
            else:
                # Cold-start defaults
                base_success = 0.75
                evidence_count = 0

            rollback_risk = float(stats.get("rollback_count", 0)) / max(1, total) if total > 0 else 0.10
        # Failure / rollback probability
        failure_prob = 1.0 - base_success

        # Duration estimate
        base_duration = cls._ACTION_DURATIONS.get(action, cls._ACTION_DURATIONS["UNKNOWN"])
        multiplier = cls._AGENT_MULTIPLIERS.get(agent, 1.0)
        resource_cost = round((base_duration / 1000.0) * multiplier, 3)

        # Apply calibration weights from SimulationCalibrator
        cal_key = f"{agent}:{action}"
        try:
            weights = SimulationCalibrator.get_all_weights()
            if cal_key in weights:
                w = weights[cal_key]
                base_success = min(1.0, base_success * float(w.get("success_factor", 1.0)))
                failure_prob = 1.0 - base_success
                base_duration = int(base_duration * float(w.get("duration_factor", 1.0)))
                rollback_risk = min(1.0, rollback_risk * float(w.get("rollback_factor", 1.0)))
        except Exception:
            pass

        # Apply reflection agent stats if available (lowers success if agent is performing poorly)
        if agent in reflection_agent_stats:
            agent_stat = reflection_agent_stats[agent]
            agent_success_rate = float(agent_stat.get("success_rate", 1.0))
            if agent_success_rate < base_success:
                # Weight reflection signal 2:1 to ensure it pulls success below the threshold
                base_success = round((base_success + 2 * agent_success_rate) / 3.0, 4)
                failure_prob = 1.0 - base_success

        # Risk score: composite of failure and rollback risk
        risk_score = round(failure_prob * 0.7 + rollback_risk * 0.3, 4)

        prediction = StepPrediction(
            step_id=step.step_id,
            agent=agent,
            action=action,
            success_probability=round(base_success, 4),
            failure_probability=round(failure_prob, 4),
            resource_cost=round(resource_cost, 3),
            risk_score=risk_score,
            rollback_risk=round(rollback_risk, 4),
            expected_duration_ms=base_duration,
            evidence_count=evidence_count,
        )

        warnings: List[str] = []
        failure_reasons: List[str] = []
        if failure_prob > 0.15:
            failure_reasons.append(f"{action} has non-trivial failure probability ({failure_prob:.0%})")
        if rollback_risk > 0.3:
            warnings.append(f"{action} has elevated rollback risk ({rollback_risk:.0%})")

        return prediction, warnings, failure_reasons

    @classmethod
    def _get_sqlite_conn(cls) -> Any:
        """Return a sqlite3 connection to the simulation ledger database."""
        import sqlite3
        db_path = runtime_data_root() / "backend" / "data" / "simulation_ledger.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS simulation_runs (
                run_id      TEXT PRIMARY KEY,
                goal        TEXT NOT NULL,
                workflow_id TEXT,
                created_at  TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS counterfactual_scenarios (
                id                  TEXT PRIMARY KEY,
                run_id              TEXT NOT NULL,
                name                TEXT NOT NULL,
                predicted_success   REAL NOT NULL,
                predicted_risk      REAL NOT NULL,
                predicted_duration_ms INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS decision_forecasts (
                decision_id         TEXT PRIMARY KEY,
                decision            TEXT NOT NULL,
                predicted_success   REAL NOT NULL,
                predicted_cost      REAL NOT NULL,
                predicted_time      TEXT NOT NULL,
                actual_success      REAL,
                actual_cost         REAL,
                actual_time         TEXT,
                status              TEXT NOT NULL DEFAULT 'pending',
                created_at          TEXT NOT NULL
            );
        """)
        conn.commit()
        return conn

    @classmethod
    def _load_active_policies(cls) -> List[Dict[str, Any]]:
        """Load active policies from policy_ledger.json if available."""
        import json
        try:
            ledger_path = runtime_data_root() / "backend" / "data" / "policy_ledger.json"
            if ledger_path.exists():
                data = json.loads(ledger_path.read_text(encoding="utf-8"))
                return [p for p in data if p.get("status") == "ACTIVE"]
        except Exception:
            pass
        return []

    @classmethod
    def _load_reflection_signals(cls) -> tuple[Dict[str, Any], List[Dict[str, Any]]]:
        """Load agent stats and recommendations from reflection_reports.json."""
        import json
        agent_stats: Dict[str, Any] = {}
        recommendations: List[Dict[str, Any]] = []
        try:
            rpt_path = runtime_data_root() / "backend" / "data" / "reflection_reports.json"
            if rpt_path.exists():
                reports = json.loads(rpt_path.read_text(encoding="utf-8"))
                if reports:
                    latest = reports[-1]
                    for stat in latest.get("agent_stats", []):
                        agent_stats[stat["agent"]] = stat
                    recommendations = latest.get("recommendations", [])
        except Exception:
            pass
        return agent_stats, recommendations

    @classmethod
    def simulate_plan(
        cls,
        plan: List[Dict[str, Any]],
        *,
        goal: str = "",
        workflow_id: str = "",
        active_policies: List[Any] | None = None,
        reflection_agent_stats: Dict[str, Any] | None = None,
        reflection_recommendations: List[Any] | None = None,
        context: Dict[str, Any] | None = None,
    ) -> "PlanSimulationReport":
        """Simulate a list of step dicts and return a PlanSimulationReport."""
        # Auto-load policies and reflection signals if not provided
        if active_policies is None:
            active_policies = cls._load_active_policies()
        if reflection_agent_stats is None or reflection_recommendations is None:
            loaded_stats, loaded_recs = cls._load_reflection_signals()
            if reflection_agent_stats is None:
                reflection_agent_stats = loaded_stats
            if reflection_recommendations is None:
                reflection_recommendations = loaded_recs

        steps = [PlanStep.from_dict(d, i) for i, d in enumerate(plan)]
        predictions: List[StepPrediction] = []
        all_warnings: List[str] = []
        failure_reasons: List[str] = []
        policy_adjustments: List[Dict[str, Any]] = []
        reflection_signals: List[Dict[str, Any]] = []

        # Build per-agent stats from WorkflowMemory for this goal (goal-aware calibration)
        workflow_agent_stats: Dict[str, Any] = {}
        workflow_step_overrides: Dict[str, Dict[str, Any]] = {}  # key: "agent:action"
        if goal:
            try:
                from backend.core.workflow_memory import WorkflowMemory
                wf_summaries = WorkflowMemory.search_workflows_by_goal(goal, limit=20)
                if wf_summaries:
                    step_data: Dict[tuple[str, str], list] = {}
                    for summary in wf_summaries:
                        run = WorkflowMemory.get_workflow_run(summary["workflow_id"])
                        if run is None:
                            continue
                        for s in run.get("steps", []):
                            key = (s.get("agent", ""), s.get("action", ""))
                            step_data.setdefault(key, []).append(s)
                    for (wf_agent, wf_action), step_list in step_data.items():
                        n = len(step_list)
                        if n == 0:
                            continue
                        successes = sum(1 for s in step_list if s.get("success", False))
                        rollback_count = sum(1 for s in step_list if s.get("rollback_executed", False))
                        step_key = f"{wf_agent}:{wf_action}"
                        workflow_step_overrides[step_key] = {
                            "total": n,
                            "successes": successes,
                            "rollback_count": rollback_count,
                        }
                        # Also build agent-level stats (used for reflection_signals check)
                        if wf_agent not in workflow_agent_stats:
                            workflow_agent_stats[wf_agent] = {
                                "agent": wf_agent,
                                "success_rate": successes / n,
                                "total_actions": n,
                            }
                        else:
                            existing = workflow_agent_stats[wf_agent]
                            total = existing["total_actions"] + n
                            existing["success_rate"] = (
                                (existing["success_rate"] * existing["total_actions"] + successes) / total
                            )
                            existing["total_actions"] = total
            except Exception:
                pass

        # Merge workflow agent stats into reflection_agent_stats (explicit reflection_agent_stats takes priority)
        merged_agent_stats = dict(workflow_agent_stats)
        merged_agent_stats.update(reflection_agent_stats or {})

        for step in steps:
            pred, warns, fails = cls._predict_step(
                step,
                active_policies=active_policies,
                reflection_agent_stats=merged_agent_stats,
                reflection_recommendations=reflection_recommendations,
                context=context or {},
                workflow_step_overrides=workflow_step_overrides,
            )
            predictions.append(pred)
            all_warnings.extend(warns)
            failure_reasons.extend(fails)

            # Check policy matches
            for pol in active_policies:
                cond = pol.get("condition", {})
                if cond.get("agent") == step.agent and cond.get("action_type") == step.action:
                    policy_adjustments.append({"policy_id": pol["policy_id"], "step_id": step.step_id, "effect": pol.get("effect", {})})

            # Check reflection signals
            if step.agent in merged_agent_stats:
                stat = merged_agent_stats[step.agent]
                if float(stat.get("success_rate", 1.0)) < 0.5:
                    reflection_signals.append({"agent": step.agent, "success_rate": stat["success_rate"]})

        if not predictions:
            success_prob = 1.0
            rollback_risk = 0.0
            total_duration = 0
        else:
            joint = 1.0
            for p in predictions:
                joint *= p.success_probability
            success_prob = min(1.0, joint * cls._calibration_modifier)
            # Use average rollback_risk across steps (not max, to avoid over-penalizing single risky steps)
            rollback_risk = sum(p.rollback_risk for p in predictions) / len(predictions)
            total_duration = sum(p.expected_duration_ms for p in predictions)


        return PlanSimulationReport(
            goal=goal,
            workflow_id=workflow_id,
            steps=predictions,
            success_probability=round(success_prob, 4),
            rollback_risk=round(rollback_risk, 4),
            estimated_duration_ms=total_duration,
            likely_failures=failure_reasons,
            warnings=all_warnings,
            policy_adjustments=policy_adjustments,
            reflection_signals=reflection_signals,
        )

    @classmethod
    def simulate_project(cls, project_id: str) -> Dict[str, Any]:
        """Simulate a project by computing critical path and resource demand."""
        from backend.core.project_manager_v2 import ProjectManagerV2
        from backend.core.goal_manager import GoalManager
        from backend.core.goal_memory import GoalMemory
        import datetime

        project = ProjectManagerV2.get_project(project_id)
        if not project:
            return {
                "completion_probability": 0.0,
                "predicted_finish_date": None,
                "critical_path": [],
                "resource_demand": {},
            }

        goal_ids = [g["goal_id"] for g in project.get("goals", [])]

        # Build dependency graph and collect milestones
        milestones = []
        deps: Dict[str, List[str]] = {}
        for gid in goal_ids:
            goal = GoalManager.get(gid)
            if not goal:
                continue
            for m in goal.get("milestones", []):
                milestones.append({"goal_id": gid, **m})
            # Get goal dependencies from GoalMemory.get_goal which returns a full dict
            goal_full = GoalMemory.get_goal(gid)
            goal_deps = goal_full.get("dependencies", []) if goal_full else []
            if goal_deps:
                deps[gid] = goal_deps

        # Topological sort (Kahn's algorithm) to find critical path
        in_degree: Dict[str, int] = {m["milestone_id"]: 0 for m in milestones}
        m_map = {m["milestone_id"]: m for m in milestones}
        # Map goal deps to milestone deps
        goal_to_milestones: Dict[str, List[str]] = {}
        for m in milestones:
            goal_to_milestones.setdefault(m["goal_id"], []).append(m["milestone_id"])

        milestone_deps: Dict[str, List[str]] = {}
        for gid, parent_ids in deps.items():
            child_mids = goal_to_milestones.get(gid, [])
            parent_mids: List[str] = []
            for pid in parent_ids:
                parent_mids.extend(goal_to_milestones.get(pid, []))
            for cmid in child_mids:
                milestone_deps[cmid] = parent_mids
                in_degree[cmid] = len(parent_mids)

        queue = [mid for mid, deg in in_degree.items() if deg == 0]
        topo: List[str] = []
        while queue:
            mid = queue.pop(0)
            topo.append(mid)
            for cmid, pmids in milestone_deps.items():
                if mid in pmids:
                    in_degree[cmid] -= 1
                    if in_degree[cmid] == 0:
                        queue.append(cmid)

        critical_path = [m_map[mid]["title"] for mid in topo if mid in m_map]

        # Estimate resource demand from milestone titles
        resource_demand: Dict[str, float] = {}
        for m in milestones:
            title_lower = m["title"].lower()
            weight = float(m.get("weight", 1.0))
            if any(kw in title_lower for kw in ["write", "code", "implement", "develop", "build"]):
                resource_demand["coder"] = resource_demand.get("coder", 0.0) + weight
            if any(kw in title_lower for kw in ["research", "read", "browse", "search"]):
                resource_demand["browser"] = resource_demand.get("browser", 0.0) + weight
            if any(kw in title_lower for kw in ["test", "verify", "validate", "check"]):
                resource_demand["tester"] = resource_demand.get("tester", 0.0) + weight
            if any(kw in title_lower for kw in ["plan", "design", "architect"]):
                resource_demand["planner"] = resource_demand.get("planner", 0.0) + weight

        # Estimate completion probability
        completion_prob = round(0.7 ** max(1, len(milestones) - 1), 4) if milestones else 0.0
        estimated_days = len(milestones) * 3
        finish_date = (datetime.date.today() + datetime.timedelta(days=estimated_days)).isoformat()

        return {
            "completion_probability": completion_prob,
            "predicted_finish_date": finish_date,
            "critical_path": critical_path,
            "resource_demand": resource_demand,
        }

    @classmethod
    def run_counterfactual_simulations(
        cls,
        plan: List[Dict[str, Any]],
        goal: str = "",
        workflow_id: str = "",
    ) -> Dict[str, Any]:
        """Run counterfactual scenario analysis on a plan."""
        import uuid
        import datetime

        reality_report = cls.simulate_plan(plan, goal=goal)
        reality_success = reality_report.success_probability
        reality_risk = reality_report.rollback_risk
        reality_duration = reality_report.estimated_duration_ms

        scenarios: Dict[str, Any] = {
            "Reality": {
                "predicted_success": reality_success,
                "predicted_risk": reality_risk,
                "predicted_duration_ms": reality_duration,
            },
            "No Action": {
                "predicted_success": 0.0,
                "predicted_risk": 0.0,
                "predicted_duration_ms": 0,
            },
            "Delay 7 Days": {
                "predicted_success": round(reality_success * 0.95, 4),
                "predicted_risk": reality_risk,
                "predicted_duration_ms": reality_duration + 7 * 24 * 3600 * 1000,
            },
            "Budget Decrease 50%": {
                "predicted_success": round(reality_success * 0.80, 4),
                "predicted_risk": round(min(0.95, reality_risk * 2.0), 4),
                "predicted_duration_ms": reality_duration,
            },
        }

        run_id = str(uuid.uuid4())
        created_at = datetime.datetime.utcnow().isoformat() + "Z"

        conn = cls._get_sqlite_conn()
        conn.execute(
            "INSERT INTO simulation_runs (run_id, goal, workflow_id, created_at) VALUES (?, ?, ?, ?)",
            (run_id, goal, workflow_id, created_at),
        )
        for name, data in scenarios.items():
            conn.execute(
                "INSERT INTO counterfactual_scenarios (id, run_id, name, predicted_success, predicted_risk, predicted_duration_ms) VALUES (?, ?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), run_id, name,
                 data["predicted_success"], data["predicted_risk"], data["predicted_duration_ms"]),
            )
        conn.commit()

        return {
            "run_id": run_id,
            "goal": goal,
            "workflow_id": workflow_id,
            "scenarios": scenarios,
        }

    @classmethod
    def record_decision_forecast(
        cls,
        decision_id: str,
        decision: str,
        predicted_success: float,
        predicted_cost: float,
        predicted_time: str,
    ) -> None:
        """Store a decision forecast in the ledger."""
        import datetime
        conn = cls._get_sqlite_conn()
        conn.execute(
            """INSERT OR REPLACE INTO decision_forecasts
               (decision_id, decision, predicted_success, predicted_cost, predicted_time,
                actual_success, actual_cost, actual_time, status, created_at)
               VALUES (?, ?, ?, ?, ?, NULL, NULL, NULL, 'pending', ?)""",
            (decision_id, decision, predicted_success, predicted_cost, predicted_time,
             datetime.datetime.utcnow().isoformat() + "Z"),
        )
        conn.commit()
        conn.close()

    @classmethod
    def record_decision_outcome(
        cls,
        decision_id: str,
        actual_success: float,
        actual_cost: float,
        actual_time: str,
    ) -> None:
        """Update a forecast with the actual outcome."""
        conn = cls._get_sqlite_conn()
        conn.execute(
            """UPDATE decision_forecasts
               SET actual_success=?, actual_cost=?, actual_time=?, status='resolved'
               WHERE decision_id=?""",
            (actual_success, actual_cost, actual_time, decision_id),
        )
        conn.commit()
        conn.close()

    @classmethod
    def recalibrate_from_ledger(cls) -> Dict[str, Any]:
        """Compute calibration error from resolved decision forecasts and update the global modifier."""
        import math
        conn = cls._get_sqlite_conn()
        rows = conn.execute(
            "SELECT predicted_success, actual_success FROM decision_forecasts WHERE status='resolved'"
        ).fetchall()
        conn.close()

        if not rows:
            return {"status": "no_data", "total_decisions": 0}

        errors = [abs(float(r["actual_success"]) - float(r["predicted_success"])) for r in rows]
        mae = sum(errors) / len(errors)
        rmse = math.sqrt(sum(e * e for e in errors) / len(errors))

        avg_predicted = sum(float(r["predicted_success"]) for r in rows) / len(rows)
        avg_actual = sum(float(r["actual_success"]) for r in rows) / len(rows)

        if avg_predicted > 0:
            ratio = avg_actual / avg_predicted
            cls._calibration_modifier = round(min(2.0, max(0.1, ratio)), 4)
        else:
            cls._calibration_modifier = 1.0

        return {
            "status": "success",
            "total_decisions": len(rows),
            "mean_absolute_error": round(mae, 4),
            "root_mean_squared_error": round(rmse, 4),
            "calibration_modifier": cls._calibration_modifier,
        }


@dataclass
class PlanSimulationReport:
    """Structured result of simulate_plan()."""
    goal: str
    steps: List["StepPrediction"]
    success_probability: float
    rollback_risk: float
    estimated_duration_ms: int
    workflow_id: str = ""
    likely_failures: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    policy_adjustments: List[Dict[str, Any]] = field(default_factory=list)
    reflection_signals: List[Dict[str, Any]] = field(default_factory=list)

    def _recommendation(self) -> str:
        if not self.steps:
            return "no executable steps supplied"
        if self.rollback_risk > 0.5 or self.success_probability < 0.4:
            return "revise plan: high failure risk detected"
        if self.rollback_risk > 0.25 or self.success_probability < 0.65:
            return "caution: moderate risk; review before execution"
        return "acceptable risk: proceed to validation"

    def _rollback_risk_level(self) -> str:
        if self.rollback_risk > 0.5:
            return "high"
        if self.rollback_risk > 0.25:
            return "medium"
        return "low"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "goal": self.goal,
            "workflow_id": self.workflow_id,
            "success_probability": self.success_probability,
            "rollback_risk": self.rollback_risk,
            "rollback_risk_level": self._rollback_risk_level(),
            "estimated_duration_ms": self.estimated_duration_ms,
            "likely_failures": self.likely_failures,
            "warnings": self.warnings,
            "step_count": len(self.steps),
            "step_predictions": [
                {
                    "step_id": p.step_id,
                    "agent": p.agent,
                    "action": p.action,
                    "success_probability": p.success_probability,
                    "failure_probability": p.failure_probability,
                    "resource_cost": p.resource_cost,
                    "risk_score": p.risk_score,
                    "rollback_risk": p.rollback_risk,
                    "expected_duration_ms": p.expected_duration_ms,
                    "evidence_count": p.evidence_count,
                }
                for p in self.steps
            ],
            "recommendation": self._recommendation(),
            "policy_adjustments": self.policy_adjustments,
            "reflection_signals": self.reflection_signals,
            "data_sources": {
                "action_memory": "enabled",
                "policy_ledger": "enabled" if self.policy_adjustments else "none",
                "reflection_reports": "enabled" if self.reflection_signals else "none",
            },
        }


@dataclass(frozen=True)
class PlanStep:
    step_id: str
    agent: str
    action: str
    reason: str = ""
    expected_outcome: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any], index: int) -> "PlanStep":
        return cls(
            step_id=str(data.get("step_id") or data.get("id") or f"step_{index + 1}"),
            agent=str(data.get("agent") or data.get("owner") or "unknown").strip().lower(),
            action=str(data.get("action") or data.get("action_type") or "UNKNOWN").strip().upper(),
            reason=str(data.get("reason") or data.get("description") or ""),
            expected_outcome=str(data.get("expected_outcome") or data.get("expected") or ""),
            metadata={k: v for k, v in data.items() if k not in {
                "step_id", "id", "agent", "owner", "action", "action_type",
                "reason", "description", "expected_outcome", "expected",
            }},
        )


@dataclass(frozen=True)
class StepPrediction:
    step_id: str
    agent: str
    action: str
    success_probability: float
    failure_probability: float
    resource_cost: float = 0.0
    risk_score: float = 0.0
    rollback_risk: float = 0.0
    expected_duration_ms: int = 0
    adjustments: list[dict[str, Any]] = field(default_factory=list)
    evidence_count: int = 0


@dataclass(frozen=True)
class Risk:
    name: str
    probability: float
    impact: float

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Risk":
        return cls(
            name=str(data.get("name", "risk")),
            probability=max(0.0, min(1.0, float(data.get("probability", 0.0)))),
            impact=max(0.0, min(1.0, float(data.get("impact", 0.0)))),
        )


@dataclass(frozen=True)
class Scenario:
    name: str
    base_success_prob: float = 1.0
    risks: tuple[Risk, ...] = ()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Scenario":
        return cls(
            name=str(data.get("name", "scenario")),
            base_success_prob=max(0.0, min(1.0, float(data.get("base_success_prob", 1.0)))),
            risks=tuple(Risk.from_dict(r) for r in data.get("risks", [])),
        )


@dataclass(frozen=True)
class SimulationReport:
    scenario: str
    trials: int
    seed: int
    success_rate: float
    failure_rate: float
    top_risks: list[dict[str, Any]] = field(default_factory=list)
    recommendation: str = ""

    @property
    def success_pct(self) -> float:
        return round(self.success_rate * 100, 1)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario": self.scenario,
            "trials": self.trials,
            "seed": self.seed,
            "success_rate": round(self.success_rate, 4),
            "failure_rate": round(self.failure_rate, 4),
            "success_pct": self.success_pct,
            "failure_pct": round(self.failure_rate * 100, 1),
            "top_risks": self.top_risks,
            "recommendation": self.recommendation,
        }



