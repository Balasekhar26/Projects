"""
test_strategy_agent.py
======================
Comprehensive test suite for Strategy Agent V1.

Coverage:
1.  TestObservationParser          — maps Reflection recommendations → TypedObservations
2.  TestPolicySynthesizer          — each rule produces a well-formed ProposedPolicy
3.  TestPolicyLedger               — persistence, dedup, conflict detection, lifecycle
4.  TestPolicyLifecycle            — PROPOSED → ACCEPTED / REJECTED state transitions
5.  TestAuthorityBoundaries        — no execution methods on StrategyAgent
6.  TestConflictDetection          — duplicate / contradictory policy guard
7.  TestStrategyNode               — LangGraph integration
8.  TestExecutiveFeedback          — accept/reject API
9.  TestStrategyCycleE2E           — full end-to-end with seeded Reflection reports
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
import unittest
from pathlib import Path

os.environ.setdefault("KATTAPPA_ENV", "test")
_ISOLATION_ROOT = tempfile.mkdtemp(prefix="strategy_test_")
os.environ["KATTAPPA_DATA_DIR"] = _ISOLATION_ROOT


def _set_root(root: str) -> None:
    os.environ["KATTAPPA_DATA_DIR"] = root
    import importlib
    import backend.agents.strategy as _mod
    importlib.reload(_mod)


class _StratBase(unittest.TestCase):
    """Fresh isolated filesystem per test."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="strat_")
        _set_root(self.root)
        Path(self.root, "backend", "data").mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        clean = tempfile.mkdtemp(prefix="strat_clean_")
        _set_root(clean)
        shutil.rmtree(self.root, ignore_errors=True)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _make_reflection_report(
        self,
        recommendations: list[dict] | None = None,
        agent_stats: list[dict] | None = None,
    ) -> dict:
        return {
            "report_id": "RPT-TEST",
            "timestamp": time.time(),
            "window_actions": 30,
            "agent_stats": agent_stats or [],
            "resource_correlations": [],
            "plan_quality": {"total_actions": 10, "block_rate": 0.0, "top_blocked_actions": []},
            "recommendations": recommendations or [],
            "narrative": "test",
        }

    def _write_reflection_report(self, report: dict) -> None:
        from backend.core.config import runtime_data_root
        p = runtime_data_root() / "backend" / "data" / "reflection_reports.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps([report]), encoding="utf-8")

    def _make_recommendation(
        self,
        category: str,
        observation: str = "",
        confidence: float = 0.80,
        rec_id: str | None = None,
    ) -> dict:
        return {
            "id": rec_id or f"REC-{category[:4].upper()}",
            "priority": "HIGH",
            "category": category,
            "observation": observation,
            "correlation": "test",
            "recommendation": "test recommendation",
            "target": "planner",
            "confidence": confidence,
        }

    def _make_agent_stat(self, agent: str, success_rate: float, avg_conf: float, total: int = 20) -> dict:
        return {
            "agent": agent,
            "total_actions": total,
            "verified_success": int(total * success_rate),
            "dve_failures": int(total * (1 - success_rate)),
            "avg_confidence": avg_conf,
            "success_rate": success_rate,
            "rollback_count": 0,
            "retry_count": 0,
        }


# ══════════════════════════════════════════════════════════════════════════════
# 1. ObservationParser
# ══════════════════════════════════════════════════════════════════════════════

class TestObservationParser(_StratBase):

    def test_empty_recommendations_returns_empty(self):
        from backend.agents.strategy import ObservationParser
        obs = ObservationParser.parse_recommendations([])
        self.assertEqual(obs, [])

    def test_agent_reliability_mapped_to_failure_rate_obs(self):
        from backend.agents.strategy import ObservationParser, ObservationType
        recs = [self._make_recommendation("agent_reliability", "Agent 'voice' has a failure rate of 40%")]
        stats = [self._make_agent_stat("voice", 0.60, 0.65)]
        obs = ObservationParser.parse_recommendations(recs, stats)
        types = [o.obs_type for o in obs]
        self.assertIn(ObservationType.AGENT_FAILURE_RATE, types)

    def test_low_confidence_obs_generated_when_avg_conf_low(self):
        from backend.agents.strategy import ObservationParser, ObservationType
        recs = [self._make_recommendation("agent_reliability", "Agent 'voice' has a low average DVE confidence score of 0.55")]
        stats = [self._make_agent_stat("voice", 0.90, 0.55)]  # success OK, confidence low
        obs = ObservationParser.parse_recommendations(recs, stats)
        types = [o.obs_type for o in obs]
        self.assertIn(ObservationType.LOW_CONFIDENCE, types)

    def test_resource_correlation_obs_extracts_cpu(self):
        from backend.agents.strategy import ObservationParser, ObservationType
        recs = [self._make_recommendation(
            "resource_pressure",
            "75% of DVE-verified failures occurred when CPU utilization exceeded 80%."
        )]
        obs = ObservationParser.parse_recommendations(recs)
        resource_obs = [o for o in obs if o.obs_type == ObservationType.RESOURCE_CORRELATION]
        self.assertTrue(len(resource_obs) > 0)
        self.assertEqual(resource_obs[0].resource, "CPU")
        self.assertIsNotNone(resource_obs[0].threshold)

    def test_resource_correlation_obs_extracts_ram(self):
        from backend.agents.strategy import ObservationParser, ObservationType
        recs = [self._make_recommendation(
            "resource_pressure",
            "65% of DVE-verified failures occurred when RAM utilization exceeded 85%."
        )]
        obs = ObservationParser.parse_recommendations(recs)
        ram_obs = [o for o in obs if o.obs_type == ObservationType.RESOURCE_CORRELATION and o.resource == "RAM"]
        self.assertTrue(len(ram_obs) > 0)

    def test_rollback_frequency_obs_generated(self):
        from backend.agents.strategy import ObservationParser, ObservationType
        recs = [self._make_recommendation("rollback_frequency", "System rollback rate is 15%")]
        obs = ObservationParser.parse_recommendations(recs)
        types = [o.obs_type for o in obs]
        self.assertIn(ObservationType.ROLLBACK_FREQUENCY, types)

    def test_plan_quality_obs_generated(self):
        from backend.agents.strategy import ObservationParser, ObservationType
        recs = [self._make_recommendation("plan_quality", "Policy engine is blocking 10% of actions")]
        obs = ObservationParser.parse_recommendations(recs)
        types = [o.obs_type for o in obs]
        self.assertIn(ObservationType.PLAN_BLOCK_RATE, types)

    def test_latency_trend_obs_generated(self):
        from backend.agents.strategy import ObservationParser, ObservationType
        recs = [self._make_recommendation("latency_trend", "Average network latency is 200ms")]
        obs = ObservationParser.parse_recommendations(recs)
        types = [o.obs_type for o in obs]
        self.assertIn(ObservationType.LATENCY_TREND, types)

    def test_unknown_category_skipped(self):
        from backend.agents.strategy import ObservationParser
        recs = [self._make_recommendation("unknown_category", "some text")]
        obs = ObservationParser.parse_recommendations(recs)
        self.assertEqual(obs, [])

    def test_load_latest_reflection_report_returns_none_when_empty(self):
        from backend.agents.strategy import ObservationParser
        result = ObservationParser.load_latest_reflection_report()
        self.assertIsNone(result)

    def test_load_latest_reflection_report_returns_last_entry(self):
        from backend.agents.strategy import ObservationParser
        r1 = self._make_reflection_report()
        r2 = self._make_reflection_report()
        r2["report_id"] = "RPT-SECOND"
        self._write_reflection_report(r2)
        result = ObservationParser.load_latest_reflection_report()
        self.assertIsNotNone(result)
        self.assertEqual(result["report_id"], "RPT-SECOND")


# ══════════════════════════════════════════════════════════════════════════════
# 2. PolicySynthesizer
# ══════════════════════════════════════════════════════════════════════════════

class TestPolicySynthesizer(_StratBase):

    def _make_obs(self, obs_type, agent=None, metric=0.5, resource=None, threshold=None, confidence=0.8):
        from backend.agents.strategy import TypedObservation, ObservationType
        return TypedObservation(
            obs_type=obs_type,
            agent=agent,
            metric_value=metric,
            resource=resource,
            threshold=threshold,
            recommendation_id="REC-TEST",
            confidence=confidence,
        )

    def test_agent_failure_generates_scheduling_constraint(self):
        from backend.agents.strategy import PolicySynthesizer, ObservationType, PolicyCategory
        obs = [self._make_obs(ObservationType.AGENT_FAILURE_RATE, agent="voice", metric=0.40)]
        policies = PolicySynthesizer.synthesize(obs)
        self.assertEqual(len(policies), 1)
        self.assertEqual(policies[0].category, PolicyCategory.SCHEDULING_CONSTRAINT.value)
        self.assertEqual(policies[0].effect.get("action"), "defer")

    def test_low_confidence_generates_plan_constraint(self):
        from backend.agents.strategy import PolicySynthesizer, ObservationType, PolicyCategory
        obs = [self._make_obs(ObservationType.LOW_CONFIDENCE, agent="coder", metric=0.60)]
        policies = PolicySynthesizer.synthesize(obs)
        self.assertEqual(len(policies), 1)
        self.assertEqual(policies[0].category, PolicyCategory.PLAN_CONSTRAINT.value)
        self.assertEqual(policies[0].effect.get("action"), "require_rollback")

    def test_resource_correlation_generates_resource_gate(self):
        from backend.agents.strategy import PolicySynthesizer, ObservationType, PolicyCategory
        obs = [self._make_obs(ObservationType.RESOURCE_CORRELATION, resource="CPU", threshold=80.0, metric=0.75)]
        policies = PolicySynthesizer.synthesize(obs)
        self.assertEqual(len(policies), 1)
        self.assertEqual(policies[0].category, PolicyCategory.RESOURCE_GATE.value)
        self.assertEqual(policies[0].condition.get("resource"), "CPU")
        self.assertAlmostEqual(policies[0].condition.get("threshold"), 80.0)

    def test_rollback_frequency_generates_retry_budget(self):
        from backend.agents.strategy import PolicySynthesizer, ObservationType, PolicyCategory
        obs = [self._make_obs(ObservationType.ROLLBACK_FREQUENCY, metric=0.15)]
        policies = PolicySynthesizer.synthesize(obs)
        self.assertEqual(len(policies), 1)
        self.assertEqual(policies[0].category, PolicyCategory.RETRY_BUDGET.value)
        self.assertEqual(policies[0].effect.get("action"), "limit_retries")
        self.assertEqual(policies[0].effect.get("max_retries"), 2)

    def test_plan_block_rate_generates_plan_constraint(self):
        from backend.agents.strategy import PolicySynthesizer, ObservationType, PolicyCategory
        obs = [self._make_obs(ObservationType.PLAN_BLOCK_RATE, metric=0.10)]
        policies = PolicySynthesizer.synthesize(obs)
        self.assertEqual(len(policies), 1)
        self.assertEqual(policies[0].category, PolicyCategory.PLAN_CONSTRAINT.value)
        self.assertEqual(policies[0].effect.get("action"), "require_capability_check")

    def test_latency_trend_generates_cooldown(self):
        from backend.agents.strategy import PolicySynthesizer, ObservationType, PolicyCategory
        obs = [self._make_obs(ObservationType.LATENCY_TREND, metric=0.40)]
        policies = PolicySynthesizer.synthesize(obs)
        self.assertEqual(len(policies), 1)
        self.assertEqual(policies[0].category, PolicyCategory.COOLDOWN.value)
        self.assertEqual(policies[0].effect.get("cooldown_sec"), 5)

    def test_low_confidence_observation_skipped(self):
        """Observations below MIN_CONFIDENCE_TO_PROPOSE must be skipped."""
        from backend.agents.strategy import PolicySynthesizer, ObservationType
        obs = [self._make_obs(ObservationType.AGENT_FAILURE_RATE, agent="voice", metric=0.40, confidence=0.20)]
        policies = PolicySynthesizer.synthesize(obs)
        self.assertEqual(policies, [])

    def test_all_policies_are_proposed_status(self):
        from backend.agents.strategy import PolicySynthesizer, ObservationType, PolicyStatus
        obs = [
            self._make_obs(ObservationType.AGENT_FAILURE_RATE, agent="voice", metric=0.40),
            self._make_obs(ObservationType.RESOURCE_CORRELATION, resource="CPU", threshold=80.0, metric=0.75),
            self._make_obs(ObservationType.ROLLBACK_FREQUENCY, metric=0.15),
        ]
        policies = PolicySynthesizer.synthesize(obs)
        for p in policies:
            self.assertEqual(p.status, PolicyStatus.PROPOSED.value)

    def test_policy_has_required_fields(self):
        from backend.agents.strategy import PolicySynthesizer, ObservationType
        obs = [self._make_obs(ObservationType.AGENT_FAILURE_RATE, agent="voice", metric=0.40)]
        policies = PolicySynthesizer.synthesize(obs)
        p = policies[0]
        self.assertTrue(p.policy_id.startswith("POL-"))
        self.assertEqual(p.version, 1)
        self.assertIsInstance(p.title, str)
        self.assertGreater(len(p.title), 0)
        self.assertIsInstance(p.condition, dict)
        self.assertIsInstance(p.effect, dict)
        self.assertIsInstance(p.derived_from, list)
        self.assertGreater(p.confidence, 0.0)
        self.assertLessEqual(p.confidence, 1.0)

    def test_policy_fingerprint_is_deterministic(self):
        from backend.agents.strategy import PolicySynthesizer, ObservationType
        obs = [self._make_obs(ObservationType.RESOURCE_CORRELATION, resource="CPU", threshold=80.0, metric=0.75)]
        p1 = PolicySynthesizer.synthesize(obs)[0]
        obs2 = [self._make_obs(ObservationType.RESOURCE_CORRELATION, resource="CPU", threshold=80.0, metric=0.75)]
        p2 = PolicySynthesizer.synthesize(obs2)[0]
        self.assertEqual(p1.fingerprint(), p2.fingerprint())

    def test_different_resources_have_different_fingerprints(self):
        from backend.agents.strategy import PolicySynthesizer, ObservationType
        obs_cpu = [self._make_obs(ObservationType.RESOURCE_CORRELATION, resource="CPU", threshold=80.0, metric=0.75)]
        obs_ram = [self._make_obs(ObservationType.RESOURCE_CORRELATION, resource="RAM", threshold=80.0, metric=0.75)]
        p_cpu = PolicySynthesizer.synthesize(obs_cpu)[0]
        p_ram = PolicySynthesizer.synthesize(obs_ram)[0]
        self.assertNotEqual(p_cpu.fingerprint(), p_ram.fingerprint())


# ══════════════════════════════════════════════════════════════════════════════
# 3. PolicyLedger — Persistence
# ══════════════════════════════════════════════════════════════════════════════

class TestPolicyLedger(_StratBase):

    def _make_policy(self, category="resource_gate", resource="CPU", threshold=80.0, action="defer"):
        from backend.agents.strategy import ProposedPolicy, PolicyStatus
        return ProposedPolicy(
            policy_id=f"POL-{id(self):X}"[:12],
            version=1,
            status=PolicyStatus.PROPOSED.value,
            category=category,
            title="Test policy",
            condition={"resource": resource, "operator": "gt", "threshold": threshold},
            effect={"action": action, "rationale": "test"},
            derived_from=["REC-TEST"],
            confidence=0.80,
            proposed_at=time.time(),
        )

    def test_empty_ledger_returns_empty(self):
        from backend.agents.strategy import PolicyLedger
        result = PolicyLedger.load_all()
        self.assertEqual(result, [])

    def test_submit_policy_persisted(self):
        from backend.agents.strategy import PolicyLedger
        policy = self._make_policy()
        result = PolicyLedger.submit(policy)
        self.assertTrue(result["submitted"])
        all_p = PolicyLedger.load_all()
        self.assertEqual(len(all_p), 1)
        self.assertEqual(all_p[0]["policy_id"], policy.policy_id)

    def test_duplicate_submission_rejected(self):
        from backend.agents.strategy import PolicyLedger
        policy = self._make_policy(resource="CPU", threshold=80.0, action="defer")
        r1 = PolicyLedger.submit(policy)
        # Build second policy with same fingerprint but different ID
        policy2 = self._make_policy(resource="CPU", threshold=80.0, action="defer")
        r2 = PolicyLedger.submit(policy2)
        self.assertTrue(r1["submitted"])
        self.assertFalse(r2["submitted"])
        self.assertTrue(r2["duplicate"])

    def test_different_category_not_duplicate(self):
        from backend.agents.strategy import PolicyLedger
        p1 = self._make_policy(category="resource_gate", resource="CPU", action="defer")
        p2 = self._make_policy(category="retry_budget", resource="", action="limit_retries")
        r1 = PolicyLedger.submit(p1)
        r2 = PolicyLedger.submit(p2)
        self.assertTrue(r1["submitted"])
        self.assertTrue(r2["submitted"])

    def test_get_proposed_returns_only_proposed(self):
        from backend.agents.strategy import PolicyLedger
        p = self._make_policy()
        PolicyLedger.submit(p)
        proposed = PolicyLedger.get_proposed_policies()
        self.assertEqual(len(proposed), 1)

    def test_get_active_returns_empty_before_acceptance(self):
        from backend.agents.strategy import PolicyLedger
        p = self._make_policy()
        PolicyLedger.submit(p)
        active = PolicyLedger.get_active_policies()
        self.assertEqual(active, [])

    def test_ledger_capped_at_500(self):
        from backend.agents.strategy import PolicyLedger, ProposedPolicy, PolicyStatus
        # Submit 510 unique policies
        for i in range(510):
            p = ProposedPolicy(
                policy_id=f"POL-{i:06d}",
                version=1,
                status=PolicyStatus.PROPOSED.value,
                category="cooldown",
                title=f"Policy {i}",
                condition={"resource": f"RES{i}"},
                effect={"action": f"act{i}"},
                derived_from=[],
                confidence=0.8,
                proposed_at=time.time(),
            )
            PolicyLedger._save(PolicyLedger.load_all() + [p.to_dict()])
        all_p = PolicyLedger.load_all()
        self.assertLessEqual(len(all_p), 500)

    def test_get_by_id_returns_correct_policy(self):
        from backend.agents.strategy import PolicyLedger
        p = self._make_policy()
        PolicyLedger.submit(p)
        found = PolicyLedger.get_by_id(p.policy_id)
        self.assertIsNotNone(found)
        self.assertEqual(found["policy_id"], p.policy_id)

    def test_get_by_id_returns_none_for_missing(self):
        from backend.agents.strategy import PolicyLedger
        result = PolicyLedger.get_by_id("POL-NOTEXIST")
        self.assertIsNone(result)


# ══════════════════════════════════════════════════════════════════════════════
# 4. Policy Lifecycle
# ══════════════════════════════════════════════════════════════════════════════

class TestPolicyLifecycle(_StratBase):

    def _submit_policy(self, resource="CPU", threshold=80.0, action="defer"):
        from backend.agents.strategy import PolicyLedger, ProposedPolicy, PolicyStatus
        p = ProposedPolicy(
            policy_id=f"POL-{uuid_hex()}",
            version=1,
            status=PolicyStatus.PROPOSED.value,
            category="resource_gate",
            title="Test lifecycle policy",
            condition={"resource": resource, "operator": "gt", "threshold": threshold},
            effect={"action": action},
            derived_from=[],
            confidence=0.80,
            proposed_at=time.time(),
        )
        PolicyLedger.submit(p)
        return p.policy_id

    def test_accept_transitions_to_accepted(self):
        from backend.agents.strategy import PolicyLedger, PolicyStatus
        pid = self._submit_policy()
        result = PolicyLedger.accept_policy(pid)
        self.assertTrue(result["success"])
        p = PolicyLedger.get_by_id(pid)
        self.assertEqual(p["status"], PolicyStatus.ACCEPTED.value)
        self.assertIsNotNone(p.get("accepted_at"))

    def test_reject_transitions_to_rejected(self):
        from backend.agents.strategy import PolicyLedger, PolicyStatus
        pid = self._submit_policy()
        result = PolicyLedger.reject_policy(pid, reason="Not applicable now")
        self.assertTrue(result["success"])
        p = PolicyLedger.get_by_id(pid)
        self.assertEqual(p["status"], PolicyStatus.REJECTED.value)
        self.assertEqual(p.get("rejection_reason"), "Not applicable now")

    def test_accepted_policy_appears_in_active(self):
        from backend.agents.strategy import PolicyLedger
        pid = self._submit_policy()
        PolicyLedger.accept_policy(pid)
        active = PolicyLedger.get_active_policies()
        ids = [p["policy_id"] for p in active]
        self.assertIn(pid, ids)

    def test_rejected_policy_not_in_active(self):
        from backend.agents.strategy import PolicyLedger
        pid = self._submit_policy()
        PolicyLedger.reject_policy(pid)
        active = PolicyLedger.get_active_policies()
        ids = [p["policy_id"] for p in active]
        self.assertNotIn(pid, ids)

    def test_accept_nonexistent_policy_fails(self):
        from backend.agents.strategy import PolicyLedger
        result = PolicyLedger.accept_policy("POL-GHOST")
        self.assertFalse(result["success"])

    def test_expired_policy_not_in_active(self):
        from backend.agents.strategy import PolicyLedger, ProposedPolicy, PolicyStatus
        p = ProposedPolicy(
            policy_id=f"POL-{uuid_hex()}",
            version=1,
            status=PolicyStatus.ACCEPTED.value,
            category="resource_gate",
            title="Expiring policy",
            condition={},
            effect={"action": "defer"},
            derived_from=[],
            confidence=0.8,
            proposed_at=time.time(),
            accepted_at=time.time() - 1000,
            expires_at=time.time() - 1,  # already expired
        )
        PolicyLedger._save([p.to_dict()])
        active = PolicyLedger.get_active_policies()
        self.assertEqual(active, [])

    def test_expire_old_policies_transitions_status(self):
        from backend.agents.strategy import PolicyLedger, ProposedPolicy, PolicyStatus
        old_ts = time.time() - (86400 * 8)  # 8 days old
        p = ProposedPolicy(
            policy_id=f"POL-{uuid_hex()}",
            version=1,
            status=PolicyStatus.ACCEPTED.value,
            category="resource_gate",
            title="Stale policy",
            condition={},
            effect={"action": "defer"},
            derived_from=[],
            confidence=0.8,
            proposed_at=old_ts,
            accepted_at=old_ts,
        )
        PolicyLedger._save([p.to_dict()])
        expired = PolicyLedger.expire_old_policies(ttl_seconds=86400 * 7)
        self.assertEqual(expired, 1)
        stored = PolicyLedger.get_by_id(p.policy_id)
        self.assertEqual(stored["status"], PolicyStatus.EXPIRED.value)


# ══════════════════════════════════════════════════════════════════════════════
# 5. Authority Boundaries
# ══════════════════════════════════════════════════════════════════════════════

class TestAuthorityBoundaries(_StratBase):

    def test_strategy_agent_has_no_execute_method(self):
        from backend.agents.strategy import StrategyAgent
        self.assertFalse(hasattr(StrategyAgent, "execute"))

    def test_strategy_agent_has_no_intake_request(self):
        from backend.agents.strategy import StrategyAgent
        self.assertFalse(hasattr(StrategyAgent, "intake_request"))

    def test_strategy_agent_has_no_modify_policy(self):
        from backend.agents.strategy import StrategyAgent
        self.assertFalse(hasattr(StrategyAgent, "modify_policy"))

    def test_strategy_agent_has_no_approve_method(self):
        from backend.agents.strategy import StrategyAgent
        # StrategyAgent.accept_policy exists but it delegates EXCLUSIVELY to Executive
        # The agent itself has no self_approve or just_approve method
        self.assertFalse(hasattr(StrategyAgent, "self_approve"))

    def test_strategy_agent_has_no_run_shell(self):
        from backend.agents.strategy import StrategyAgent
        self.assertFalse(hasattr(StrategyAgent, "run_shell"))

    def test_proposed_policy_is_not_callable(self):
        from backend.agents.strategy import ProposedPolicy, PolicyStatus
        p = ProposedPolicy(
            policy_id="POL-X",
            version=1,
            status=PolicyStatus.PROPOSED.value,
            category="resource_gate",
            title="test",
            condition={},
            effect={"action": "defer"},
            derived_from=[],
            confidence=0.8,
            proposed_at=time.time(),
        )
        self.assertFalse(callable(p), "ProposedPolicy must be a data object, not callable")

    def test_all_synthesized_policies_are_proposed(self):
        """No policy can be born ACCEPTED — only Executive can accept."""
        from backend.agents.strategy import PolicySynthesizer, ObservationType, PolicyStatus
        from backend.agents.strategy import TypedObservation
        obs = [
            TypedObservation(ObservationType.AGENT_FAILURE_RATE, "voice", 0.40, confidence=0.9, recommendation_id="R1"),
            TypedObservation(ObservationType.RESOURCE_CORRELATION, None, 0.75, resource="CPU", threshold=80.0, confidence=0.9, recommendation_id="R2"),
            TypedObservation(ObservationType.ROLLBACK_FREQUENCY, None, 0.20, confidence=0.9, recommendation_id="R3"),
        ]
        policies = PolicySynthesizer.synthesize(obs)
        for p in policies:
            self.assertEqual(
                p.status,
                PolicyStatus.PROPOSED.value,
                f"Policy '{p.policy_id}' must be born PROPOSED, not {p.status}"
            )

    def test_observation_parser_has_no_write_method(self):
        from backend.agents.strategy import ObservationParser
        for forbidden in ("write", "execute", "run", "delete", "modify"):
            self.assertFalse(hasattr(ObservationParser, forbidden))

    def test_policy_synthesizer_has_no_execution_methods(self):
        from backend.agents.strategy import PolicySynthesizer
        for forbidden in ("execute", "run_shell", "intake_request", "approve", "accept"):
            self.assertFalse(hasattr(PolicySynthesizer, forbidden))


# ══════════════════════════════════════════════════════════════════════════════
# 6. Conflict Detection
# ══════════════════════════════════════════════════════════════════════════════

class TestConflictDetection(_StratBase):

    def _submit_and_accept(self, resource="CPU", threshold=80.0, action="defer", cat="resource_gate") -> str:
        from backend.agents.strategy import PolicyLedger, ProposedPolicy, PolicyStatus
        p = ProposedPolicy(
            policy_id=f"POL-{uuid_hex()}",
            version=1,
            status=PolicyStatus.PROPOSED.value,
            category=cat,
            title="Active policy",
            condition={"resource": resource, "operator": "gt", "threshold": threshold},
            effect={"action": action},
            derived_from=[],
            confidence=0.80,
            proposed_at=time.time(),
        )
        PolicyLedger.submit(p)
        PolicyLedger.accept_policy(p.policy_id)
        return p.policy_id

    def test_conflict_with_active_policy_flagged(self):
        from backend.agents.strategy import PolicyLedger, ProposedPolicy, PolicyStatus
        # Accept a policy first
        existing_id = self._submit_and_accept(resource="CPU", threshold=80.0, action="defer")

        # Submit another with same fingerprint (conflict)
        p2 = ProposedPolicy(
            policy_id=f"POL-{uuid_hex()}",
            version=1,
            status=PolicyStatus.PROPOSED.value,
            category="resource_gate",
            title="Conflicting policy",
            condition={"resource": "CPU", "operator": "gt", "threshold": 80.0},
            effect={"action": "defer"},
            derived_from=[],
            confidence=0.75,
            proposed_at=time.time(),
        )
        result = PolicyLedger.submit(p2)
        # Should still submit (conflict is advisory) but flag the conflict
        self.assertTrue(result["submitted"])
        self.assertIn(existing_id, result["conflicts"])

    def test_no_conflict_for_different_resource(self):
        from backend.agents.strategy import PolicyLedger, ProposedPolicy, PolicyStatus
        self._submit_and_accept(resource="CPU", threshold=80.0, action="defer")

        p2 = ProposedPolicy(
            policy_id=f"POL-{uuid_hex()}",
            version=1,
            status=PolicyStatus.PROPOSED.value,
            category="resource_gate",
            title="RAM policy",
            condition={"resource": "RAM", "operator": "gt", "threshold": 80.0},
            effect={"action": "defer"},
            derived_from=[],
            confidence=0.75,
            proposed_at=time.time(),
        )
        result = PolicyLedger.submit(p2)
        self.assertTrue(result["submitted"])
        self.assertEqual(result["conflicts"], [])

    def test_exact_duplicate_proposed_rejected(self):
        from backend.agents.strategy import PolicyLedger, ProposedPolicy, PolicyStatus
        p1 = ProposedPolicy(
            policy_id=f"POL-{uuid_hex()}",
            version=1,
            status=PolicyStatus.PROPOSED.value,
            category="resource_gate",
            title="Original",
            condition={"resource": "CPU", "operator": "gt", "threshold": 80.0},
            effect={"action": "defer"},
            derived_from=[],
            confidence=0.80,
            proposed_at=time.time(),
        )
        PolicyLedger.submit(p1)
        p2 = ProposedPolicy(
            policy_id=f"POL-{uuid_hex()}",  # Different ID
            version=1,
            status=PolicyStatus.PROPOSED.value,
            category="resource_gate",
            title="Duplicate",
            condition={"resource": "CPU", "operator": "gt", "threshold": 80.0},
            effect={"action": "defer"},
            derived_from=[],
            confidence=0.80,
            proposed_at=time.time(),
        )
        result = PolicyLedger.submit(p2)
        self.assertFalse(result["submitted"])
        self.assertTrue(result["duplicate"])


# ══════════════════════════════════════════════════════════════════════════════
# 7. LangGraph Strategy Node
# ══════════════════════════════════════════════════════════════════════════════

class TestStrategyNode(_StratBase):

    def test_node_updates_state_result(self):
        from backend.agents.strategy import strategy_node
        state = {"logs": [], "user_input": "test"}
        updated = strategy_node(state)
        self.assertIn("result", updated)

    def test_node_appends_to_logs(self):
        from backend.agents.strategy import strategy_node
        state = {"logs": []}
        updated = strategy_node(state)
        self.assertGreater(len(updated["logs"]), 0)
        self.assertIn("strategy:", updated["logs"][-1])

    def test_node_graceful_with_no_reflection_data(self):
        from backend.agents.strategy import strategy_node
        state = {"logs": []}
        updated = strategy_node(state)
        # Should not crash with empty data
        self.assertIsNotNone(updated)

    def test_node_preserves_existing_logs(self):
        from backend.agents.strategy import strategy_node
        state = {"logs": ["prior log entry"], "user_input": "test"}
        updated = strategy_node(state)
        self.assertIn("prior log entry", updated["logs"])


# ══════════════════════════════════════════════════════════════════════════════
# 8. Executive Feedback (accept/reject via StrategyAgent API)
# ══════════════════════════════════════════════════════════════════════════════

class TestExecutiveFeedback(_StratBase):

    def _submit_policy_direct(self) -> str:
        from backend.agents.strategy import PolicyLedger, ProposedPolicy, PolicyStatus
        p = ProposedPolicy(
            policy_id=f"POL-{uuid_hex()}",
            version=1,
            status=PolicyStatus.PROPOSED.value,
            category="resource_gate",
            title="Executive feedback test policy",
            condition={"resource": "CPU", "operator": "gt", "threshold": 80.0},
            effect={"action": "defer"},
            derived_from=["REC-TEST"],
            confidence=0.85,
            proposed_at=time.time(),
        )
        PolicyLedger.submit(p)
        return p.policy_id

    def test_executive_accept_via_strategy_agent(self):
        from backend.agents.strategy import StrategyAgent, PolicyLedger, PolicyStatus
        pid = self._submit_policy_direct()
        result = StrategyAgent.accept_policy(pid)
        self.assertTrue(result["success"])
        p = PolicyLedger.get_by_id(pid)
        self.assertEqual(p["status"], PolicyStatus.ACCEPTED.value)

    def test_executive_reject_with_reason(self):
        from backend.agents.strategy import StrategyAgent, PolicyLedger, PolicyStatus
        pid = self._submit_policy_direct()
        result = StrategyAgent.reject_policy(pid, reason="Not applicable in current phase")
        self.assertTrue(result["success"])
        p = PolicyLedger.get_by_id(pid)
        self.assertEqual(p["status"], PolicyStatus.REJECTED.value)
        self.assertEqual(p["rejection_reason"], "Not applicable in current phase")

    def test_policy_summary_counts_by_status(self):
        from backend.agents.strategy import StrategyAgent, PolicyLedger, ProposedPolicy, PolicyStatus
        # Submit two policies with DIFFERENT fingerprints
        p1 = ProposedPolicy(
            policy_id=f"POL-{uuid_hex()}",
            version=1, status=PolicyStatus.PROPOSED.value,
            category="resource_gate", title="Policy A",
            condition={"resource": "CPU", "operator": "gt", "threshold": 80.0},
            effect={"action": "defer"}, derived_from=[], confidence=0.85, proposed_at=time.time(),
        )
        p2 = ProposedPolicy(
            policy_id=f"POL-{uuid_hex()}",
            version=1, status=PolicyStatus.PROPOSED.value,
            category="retry_budget", title="Policy B",
            condition={},  # different fingerprint
            effect={"action": "limit_retries"}, derived_from=[], confidence=0.80, proposed_at=time.time(),
        )
        PolicyLedger.submit(p1)
        PolicyLedger.submit(p2)
        StrategyAgent.accept_policy(p1.policy_id)
        summary = StrategyAgent.get_policy_summary()
        self.assertGreaterEqual(summary["active"], 1)
        self.assertGreaterEqual(summary["pending_review"], 1)

    def test_get_active_policies_after_acceptance(self):
        from backend.agents.strategy import StrategyAgent
        pid = self._submit_policy_direct()
        StrategyAgent.accept_policy(pid)
        active = StrategyAgent.get_active_policies()
        ids = [p["policy_id"] for p in active]
        self.assertIn(pid, ids)

    def test_get_proposed_policies_after_rejection(self):
        from backend.agents.strategy import StrategyAgent
        pid = self._submit_policy_direct()
        StrategyAgent.reject_policy(pid)
        proposed = StrategyAgent.get_proposed_policies()
        ids = [p["policy_id"] for p in proposed]
        self.assertNotIn(pid, ids)


# ══════════════════════════════════════════════════════════════════════════════
# 9. End-to-End Strategy Cycle
# ══════════════════════════════════════════════════════════════════════════════

class TestStrategyCycleE2E(_StratBase):

    def _seed_reflection_with_voice_failure(self):
        """Seed a realistic Reflection report that should trigger policies."""
        recs = [
            {
                "id": "REC-VOICEFAIL",
                "priority": "HIGH",
                "category": "agent_reliability",
                "observation": "Agent 'voice' has a failure rate of 39.0% over 20 verified actions (avg confidence: 0.55).",
                "correlation": "DVE flagged 8 critical failures.",
                "recommendation": "Reduce load on 'voice' or investigate its failure causes.",
                "target": "planner",
                "confidence": 0.85,
            },
            {
                "id": "REC-CPUCORR",
                "priority": "HIGH",
                "category": "resource_pressure",
                "observation": "75% of DVE-verified failures occurred when CPU utilization exceeded 80%.",
                "correlation": "DVE and monitoring co-occurrence.",
                "recommendation": "Defer actions when CPU > 80%.",
                "target": "planner",
                "confidence": 0.80,
            },
        ]
        stats = [
            self._make_agent_stat("voice", 0.61, 0.55),
            self._make_agent_stat("coder", 0.97, 0.94),
        ]
        report = self._make_reflection_report(recs, stats)
        self._write_reflection_report(report)

    def test_cycle_returns_success(self):
        from backend.agents.strategy import StrategyAgent
        self._seed_reflection_with_voice_failure()
        result = StrategyAgent.run_strategy_cycle()
        self.assertTrue(result["success"])

    def test_cycle_proposes_policies_from_reflection(self):
        from backend.agents.strategy import StrategyAgent
        self._seed_reflection_with_voice_failure()
        result = StrategyAgent.run_strategy_cycle()
        self.assertGreater(result["policies_proposed"], 0)

    def test_cycle_submits_at_least_one_policy(self):
        from backend.agents.strategy import StrategyAgent
        self._seed_reflection_with_voice_failure()
        result = StrategyAgent.run_strategy_cycle()
        self.assertGreater(result["policies_submitted"], 0)

    def test_cycle_policies_appear_in_ledger(self):
        from backend.agents.strategy import StrategyAgent, PolicyLedger
        self._seed_reflection_with_voice_failure()
        StrategyAgent.run_strategy_cycle()
        proposed = PolicyLedger.get_proposed_policies()
        self.assertGreater(len(proposed), 0)

    def test_second_cycle_deduplicates(self):
        from backend.agents.strategy import StrategyAgent
        self._seed_reflection_with_voice_failure()
        r1 = StrategyAgent.run_strategy_cycle()
        r2 = StrategyAgent.run_strategy_cycle()
        # Second run should produce duplicates (not new submissions)
        self.assertGreater(r2["policies_duplicate"], 0)
        self.assertEqual(r2["policies_submitted"], 0)

    def test_narrative_contains_strategy_header(self):
        from backend.agents.strategy import StrategyAgent
        self._seed_reflection_with_voice_failure()  # ensure data present
        result = StrategyAgent.run_strategy_cycle()
        self.assertIn("KATTAPPA STRATEGY REPORT", result.get("narrative", ""))

    def test_narrative_says_none_self_applied(self):
        from backend.agents.strategy import StrategyAgent
        self._seed_reflection_with_voice_failure()
        result = StrategyAgent.run_strategy_cycle()
        narrative = result.get("narrative", "")
        self.assertIn("PENDING Executive review", narrative)

    def test_cycle_with_no_reflection_data_graceful(self):
        from backend.agents.strategy import StrategyAgent
        result = StrategyAgent.run_strategy_cycle()
        self.assertTrue(result["success"])
        self.assertEqual(result["policies_proposed"], 0)


# ── Helper ────────────────────────────────────────────────────────────────────

def uuid_hex() -> str:
    import uuid
    return uuid.uuid4().hex[:8].upper()


if __name__ == "__main__":
    unittest.main(verbosity=2)
