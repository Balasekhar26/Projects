"""
test_reflection_agent.py
========================
Comprehensive test suite for Reflection Agent V1.

Coverage:
- Module 1: ConfidenceAnalyzer — per-agent DVE evidence aggregation
- Module 2: RetryRollbackAnalyzer — retry/rollback counting from audit log
- Module 3: ResourceCorrelator — failure vs resource-pressure correlation
- Module 4: PlannerPerformanceTracker — block-rate and plan quality
- Module 5: InsightSynthesizer — recommendation priority ordering
- Authority boundaries — confirmed no execution methods
- Persistence — report store capped at 200
- Full reflection cycle E2E
"""

from __future__ import annotations

import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("KATTAPPA_ENV", "test")
# Use KATTAPPA_DATA_DIR — the env var actually read by runtime_data_root() on macOS
_ISOLATION_ROOT = tempfile.mkdtemp(prefix="reflect_test_")
os.environ["KATTAPPA_DATA_DIR"] = _ISOLATION_ROOT


def _set_root(root: str) -> None:
    os.environ["KATTAPPA_DATA_DIR"] = root
    # Invalidate any cached path functions
    import importlib
    import backend.agents.reflection as _ref_mod
    importlib.reload(_ref_mod)


class _ReflectBase(unittest.TestCase):
    """Base with a fresh isolated root per test."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="ref_")
        _set_root(self.root)
        Path(self.root, "backend", "data").mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        import shutil
        # Restore to a clean temp dir so next test doesn't see stale data
        clean = tempfile.mkdtemp(prefix="ref_clean_")
        _set_root(clean)
        shutil.rmtree(self.root, ignore_errors=True)

    def _write_evidence(self, entries: list[dict]) -> None:
        # Write directly using the current env-var path
        from backend.core.config import runtime_data_root
        p = runtime_data_root() / "backend" / "data" / "verification_evidence.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(entries), encoding="utf-8")

    def _write_audit(self, entries: list[dict]) -> None:
        from backend.core.config import runtime_data_root
        p = runtime_data_root() / "backend" / "data" / "action_broker_audit.log"
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("w", encoding="utf-8") as f:
            for e in entries:
                f.write(json.dumps(e) + "\n")

    def _write_monitoring(self, samples: list[dict], stats: dict | None = None) -> None:
        from backend.core.config import runtime_data_root
        p = runtime_data_root() / "backend" / "data" / "monitoring_stats.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        data = stats or {}
        data["samples_history"] = samples
        p.write_text(json.dumps(data), encoding="utf-8")


# ══════════════════════════════════════════════════════════════════════════════
# 1.  ConfidenceAnalyzer
# ══════════════════════════════════════════════════════════════════════════════

class TestConfidenceAnalyzer(_ReflectBase):

    def _make_entry(self, agent, score, ts=None):
        return {
            "target_agent": agent,
            "confidence_score": score,
            "timestamp": ts or time.time(),
            "action": "WRITE_FILE",
        }

    def test_empty_evidence_returns_empty_stats(self):
        from backend.agents.reflection import ConfidenceAnalyzer
        self._write_evidence([])
        evidence = ConfidenceAnalyzer.load_evidence()
        stats = ConfidenceAnalyzer.compute_agent_stats(evidence)
        self.assertEqual(stats, {})

    def test_single_agent_success(self):
        from backend.agents.reflection import ConfidenceAnalyzer
        entries = [self._make_entry("coder", 0.95) for _ in range(10)]
        stats = ConfidenceAnalyzer.compute_agent_stats(entries)
        self.assertIn("coder", stats)
        self.assertEqual(stats["coder"].total_actions, 10)
        self.assertEqual(stats["coder"].verified_success, 10)
        self.assertEqual(stats["coder"].dve_failures, 0)
        self.assertAlmostEqual(stats["coder"].success_rate, 1.0)

    def test_failure_counting(self):
        from backend.agents.reflection import ConfidenceAnalyzer
        entries = (
            [self._make_entry("voice", 0.95)] * 7 +
            [self._make_entry("voice", 0.30)] * 3
        )
        stats = ConfidenceAnalyzer.compute_agent_stats(entries)
        self.assertEqual(stats["voice"].dve_failures, 3)
        self.assertAlmostEqual(stats["voice"].success_rate, 0.7)

    def test_multiple_agents_isolated(self):
        from backend.agents.reflection import ConfidenceAnalyzer
        entries = (
            [self._make_entry("browser", 0.95)] * 5 +
            [self._make_entry("desktop", 0.40)] * 5
        )
        stats = ConfidenceAnalyzer.compute_agent_stats(entries)
        self.assertIn("browser", stats)
        self.assertIn("desktop", stats)
        self.assertEqual(stats["browser"].verified_success, 5)
        self.assertEqual(stats["desktop"].verified_success, 0)

    def test_avg_confidence_running_average(self):
        from backend.agents.reflection import ConfidenceAnalyzer
        # All 1.0 → avg must be 1.0
        entries = [self._make_entry("coder", 1.0) for _ in range(20)]
        stats = ConfidenceAnalyzer.compute_agent_stats(entries)
        self.assertAlmostEqual(stats["coder"].avg_confidence, 1.0, places=3)

    def test_review_zone_not_counted_as_success_or_failure(self):
        """REVIEW zone (0.60–0.89) should not add to verified_success or dve_failures."""
        from backend.agents.reflection import ConfidenceAnalyzer
        entries = [self._make_entry("file", 0.75) for _ in range(5)]
        stats = ConfidenceAnalyzer.compute_agent_stats(entries)
        self.assertEqual(stats["file"].verified_success, 0)
        self.assertEqual(stats["file"].dve_failures, 0)
        self.assertEqual(stats["file"].total_actions, 5)

    def test_load_evidence_caps_at_max(self):
        from backend.agents.reflection import ConfidenceAnalyzer
        from backend.core.config import runtime_data_root
        entries = [self._make_entry("x", 1.0) for _ in range(600)]
        # Write directly using current data root
        p = runtime_data_root() / "backend" / "data" / "verification_evidence.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(entries), encoding="utf-8")
        loaded = ConfidenceAnalyzer.load_evidence(max_entries=500)
        self.assertLessEqual(len(loaded), 500)

    def test_missing_evidence_file_returns_empty(self):
        from backend.agents.reflection import ConfidenceAnalyzer
        from backend.core.config import runtime_data_root
        # Ensure the evidence file does NOT exist in our isolated root
        p = runtime_data_root() / "backend" / "data" / "verification_evidence.json"
        if p.exists():
            p.unlink()
        result = ConfidenceAnalyzer.load_evidence()
        self.assertEqual(result, [])


# ══════════════════════════════════════════════════════════════════════════════
# 2.  RetryRollbackAnalyzer
# ══════════════════════════════════════════════════════════════════════════════

class TestRetryRollbackAnalyzer(_ReflectBase):

    def _make_audit_entry(self, agent, approval_state, result="ok", action="WRITE_FILE"):
        return {
            "timestamp": time.time(),
            "agent": agent,
            "requested_action": action,
            "approval_state": approval_state,
            "execution_result": result,
        }

    def test_empty_audit_log_returns_unchanged_stats(self):
        from backend.agents.reflection import RetryRollbackAnalyzer, AgentStats
        stats = {"coder": AgentStats(agent="coder", total_actions=5)}
        result = RetryRollbackAnalyzer.compute_retry_rollback_counts([], stats)
        self.assertEqual(result["coder"].rollback_count, 0)

    def test_rollback_counted_from_approval_state(self):
        from backend.agents.reflection import RetryRollbackAnalyzer, AgentStats
        entries = [
            self._make_audit_entry("coder", "ROLLBACK_STARTED"),
            self._make_audit_entry("coder", "ROLLBACK_COMPLETED"),
            self._make_audit_entry("coder", "auto_approved"),
        ]
        stats = {"coder": AgentStats(agent="coder", total_actions=10)}
        result = RetryRollbackAnalyzer.compute_retry_rollback_counts(entries, stats)
        self.assertGreater(result["coder"].rollback_count, 0)

    def test_rollback_counted_from_execution_result(self):
        from backend.agents.reflection import RetryRollbackAnalyzer, AgentStats
        entries = [
            self._make_audit_entry("browser", "auto_approved", result="ROLLBACK chain triggered"),
        ]
        stats = {}
        result = RetryRollbackAnalyzer.compute_retry_rollback_counts(entries, stats)
        # Agent not pre-existing — should be created
        self.assertIn("browser", result)

    def test_retry_counted_from_result(self):
        from backend.agents.reflection import RetryRollbackAnalyzer, AgentStats
        entries = [
            self._make_audit_entry("voice", "auto_approved", result="retry attempt 1"),
            self._make_audit_entry("voice", "auto_approved", result="retry attempt 2"),
        ]
        stats = {"voice": AgentStats(agent="voice", total_actions=10)}
        result = RetryRollbackAnalyzer.compute_retry_rollback_counts(entries, stats)
        self.assertGreater(result["voice"].retry_count, 0)

    def test_non_rollback_entries_not_counted(self):
        from backend.agents.reflection import RetryRollbackAnalyzer, AgentStats
        entries = [
            self._make_audit_entry("coder", "auto_approved", "success"),
            self._make_audit_entry("coder", "approved", "all good"),
        ]
        stats = {"coder": AgentStats(agent="coder", total_actions=5)}
        result = RetryRollbackAnalyzer.compute_retry_rollback_counts(entries, stats)
        self.assertEqual(result["coder"].rollback_count, 0)

    def test_load_audit_handles_malformed_lines(self):
        from backend.agents.reflection import RetryRollbackAnalyzer
        from backend.core.config import runtime_data_root
        p = runtime_data_root() / "backend" / "data" / "action_broker_audit.log"
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("w") as f:
            f.write("not json\n")
            f.write(json.dumps({"agent": "coder", "approval_state": "ok", "execution_result": "x"}) + "\n")
            f.write("also not json\n")
        entries = RetryRollbackAnalyzer.load_audit_entries()
        self.assertEqual(len(entries), 1)

    def test_missing_audit_log_returns_empty(self):
        from backend.agents.reflection import RetryRollbackAnalyzer
        from backend.core.config import runtime_data_root
        p = runtime_data_root() / "backend" / "data" / "action_broker_audit.log"
        if p.exists():
            p.unlink()
        entries = RetryRollbackAnalyzer.load_audit_entries()
        self.assertEqual(entries, [])


# ══════════════════════════════════════════════════════════════════════════════
# 3.  ResourceCorrelator
# ══════════════════════════════════════════════════════════════════════════════

class TestResourceCorrelator(_ReflectBase):

    def _make_monitoring_sample(self, ts, cpu=0.0, ram=0.0):
        return {"timestamp": ts, "cpu_percent": cpu, "ram_percent": ram}

    def _make_failure_evidence(self, ts, agent="voice"):
        return {"target_agent": agent, "confidence_score": 0.30, "timestamp": ts}

    def test_empty_inputs_return_no_correlations(self):
        from backend.agents.reflection import ResourceCorrelator
        result = ResourceCorrelator.correlate([], [])
        self.assertEqual(result, [])

    def test_high_cpu_correlated_with_failures(self):
        from backend.agents.reflection import ResourceCorrelator
        now = time.time()
        evidence = [self._make_failure_evidence(now + i) for i in range(10)]
        monitoring = [self._make_monitoring_sample(now + i, cpu=92.0) for i in range(10)]
        correlations = ResourceCorrelator.correlate(evidence, monitoring)
        cpu_corr = next((c for c in correlations if c["resource"] == "CPU"), None)
        self.assertIsNotNone(cpu_corr)
        self.assertGreaterEqual(cpu_corr["failure_correlation"], 0.40)

    def test_low_cpu_no_correlation(self):
        from backend.agents.reflection import ResourceCorrelator
        now = time.time()
        evidence = [self._make_failure_evidence(now + i) for i in range(10)]
        monitoring = [self._make_monitoring_sample(now + i, cpu=20.0) for i in range(10)]
        correlations = ResourceCorrelator.correlate(evidence, monitoring)
        cpu_corr = next((c for c in correlations if c["resource"] == "CPU"), None)
        self.assertIsNone(cpu_corr)

    def test_ram_correlation_detected(self):
        from backend.agents.reflection import ResourceCorrelator
        now = time.time()
        evidence = [self._make_failure_evidence(now + i) for i in range(10)]
        monitoring = [self._make_monitoring_sample(now + i, ram=90.0) for i in range(10)]
        correlations = ResourceCorrelator.correlate(evidence, monitoring)
        ram_corr = next((c for c in correlations if c["resource"] == "RAM"), None)
        self.assertIsNotNone(ram_corr)

    def test_wide_timestamp_gap_skipped(self):
        """Failures and monitoring samples more than 5 min apart should not correlate."""
        from backend.agents.reflection import ResourceCorrelator
        now = time.time()
        evidence = [self._make_failure_evidence(now)]
        # Monitoring sample 10 minutes later — too far
        monitoring = [self._make_monitoring_sample(now + 600, cpu=99.0)]
        correlations = ResourceCorrelator.correlate(evidence, monitoring)
        self.assertEqual(correlations, [])

    def test_successful_actions_not_counted_in_failures(self):
        """Only DVE failures (score < 0.60) should be counted."""
        from backend.agents.reflection import ResourceCorrelator
        now = time.time()
        # All successes → no failures to correlate
        evidence = [{"target_agent": "coder", "confidence_score": 0.95, "timestamp": now}]
        monitoring = [self._make_monitoring_sample(now, cpu=99.0)]
        correlations = ResourceCorrelator.correlate(evidence, monitoring)
        self.assertEqual(correlations, [])


# ══════════════════════════════════════════════════════════════════════════════
# 4.  PlannerPerformanceTracker
# ══════════════════════════════════════════════════════════════════════════════

class TestPlannerPerformanceTracker(_ReflectBase):

    def test_empty_entries(self):
        from backend.agents.reflection import PlannerPerformanceTracker
        quality = PlannerPerformanceTracker.compute_plan_quality([])
        self.assertEqual(quality["total_actions"], 0)
        self.assertEqual(quality["block_rate"], 0.0)

    def test_auto_approved_counted(self):
        from backend.agents.reflection import PlannerPerformanceTracker
        entries = [
            {"agent": "coder", "approval_state": "auto_approved", "requested_action": "READ_FILE", "execution_result": "ok"},
        ] * 10
        quality = PlannerPerformanceTracker.compute_plan_quality(entries)
        self.assertEqual(quality["total_actions"], 10)
        self.assertEqual(quality["auto_approved"], 10)
        self.assertEqual(quality["blocked"], 0)
        self.assertEqual(quality["block_rate"], 0.0)

    def test_block_rate_computed(self):
        from backend.agents.reflection import PlannerPerformanceTracker
        entries = (
            [{"agent": "coder", "approval_state": "auto_approved", "requested_action": "READ_FILE", "execution_result": "ok"}] * 8 +
            [{"agent": "coder", "approval_state": "blocked", "requested_action": "EXFILTRATE_DATA", "execution_result": "blocked"}] * 2
        )
        quality = PlannerPerformanceTracker.compute_plan_quality(entries)
        self.assertAlmostEqual(quality["block_rate"], 0.20)
        self.assertEqual(quality["blocked"], 2)

    def test_top_blocked_actions_sorted(self):
        from backend.agents.reflection import PlannerPerformanceTracker
        entries = (
            [{"agent": "coder", "approval_state": "blocked", "requested_action": "DELETE_DB", "execution_result": "blocked"}] * 5 +
            [{"agent": "coder", "approval_state": "blocked", "requested_action": "EXFILTRATE", "execution_result": "blocked"}] * 3
        )
        quality = PlannerPerformanceTracker.compute_plan_quality(entries)
        top = quality["top_blocked_actions"]
        self.assertGreater(len(top), 0)
        self.assertEqual(top[0]["action"], "DELETE_DB")  # Most frequent first


# ══════════════════════════════════════════════════════════════════════════════
# 5.  InsightSynthesizer
# ══════════════════════════════════════════════════════════════════════════════

class TestInsightSynthesizer(_ReflectBase):

    def _make_stats(self, agent, success_rate, total=20, avg_conf=None, rollback=0):
        from backend.agents.reflection import AgentStats
        s = AgentStats(
            agent=agent,
            total_actions=total,
            verified_success=int(total * success_rate),
            dve_failures=int(total * (1 - success_rate)),
            avg_confidence=avg_conf if avg_conf is not None else success_rate,
            success_rate=success_rate,
            rollback_count=rollback,
        )
        return s

    def test_no_recommendations_when_all_healthy(self):
        from backend.agents.reflection import InsightSynthesizer
        stats = {
            "coder": self._make_stats("coder", 0.97, avg_conf=0.95),
            "browser": self._make_stats("browser", 0.95, avg_conf=0.92),
        }
        recs = InsightSynthesizer.synthesize(stats, [], {}, [])
        # All above thresholds → no failure/low-confidence recs
        failure_recs = [r for r in recs if r.category == "agent_reliability"]
        self.assertEqual(failure_recs, [])

    def test_high_failure_rate_generates_recommendation(self):
        from backend.agents.reflection import InsightSynthesizer
        stats = {"voice": self._make_stats("voice", 0.40, avg_conf=0.55)}
        recs = InsightSynthesizer.synthesize(stats, [], {}, [])
        self.assertTrue(any(r.category == "agent_reliability" for r in recs))

    def test_low_avg_confidence_generates_recommendation(self):
        from backend.agents.reflection import InsightSynthesizer
        # Success rate OK but confidence very low
        stats = {"file": self._make_stats("file", 0.90, avg_conf=0.62)}
        recs = InsightSynthesizer.synthesize(stats, [], {}, [])
        low_conf = [r for r in recs if "confidence" in r.observation.lower()]
        self.assertTrue(len(low_conf) > 0)

    def test_high_rollback_rate_generates_recommendation(self):
        from backend.agents.reflection import InsightSynthesizer
        # Many rollbacks relative to total actions
        stats = {
            "coder": self._make_stats("coder", 0.95, total=50, rollback=10),
        }
        recs = InsightSynthesizer.synthesize(stats, [], {}, [])
        rb_recs = [r for r in recs if r.category == "rollback_frequency"]
        self.assertTrue(len(rb_recs) > 0)

    def test_resource_correlation_generates_recommendation(self):
        from backend.agents.reflection import InsightSynthesizer
        correlations = [{"resource": "CPU", "threshold_pct": 80.0, "failure_correlation": 0.75, "total_failures_analyzed": 20, "pressured_failures": 15}]
        recs = InsightSynthesizer.synthesize({}, correlations, {}, [])
        res_recs = [r for r in recs if r.category == "resource_pressure"]
        self.assertTrue(len(res_recs) > 0)

    def test_high_block_rate_generates_recommendation(self):
        from backend.agents.reflection import InsightSynthesizer
        plan_quality = {
            "total_actions": 100, "auto_approved": 88,
            "approval_required": 2, "blocked": 10,
            "block_rate": 0.10, "top_blocked_actions": [],
        }
        recs = InsightSynthesizer.synthesize({}, [], plan_quality, [])
        plan_recs = [r for r in recs if r.category == "plan_quality"]
        self.assertTrue(len(plan_recs) > 0)

    def test_recommendations_sorted_critical_first(self):
        from backend.agents.reflection import InsightSynthesizer, RecommendationPriority
        stats = {
            # Very high failure rate → CRITICAL
            "voice": self._make_stats("voice", 0.10, avg_conf=0.20),
            # Slight failure → LOW
            "browser": self._make_stats("browser", 0.82, avg_conf=0.85),
        }
        recs = InsightSynthesizer.synthesize(stats, [], {}, [])
        if len(recs) >= 2:
            priorities = [r.priority for r in recs]
            order = {RecommendationPriority.CRITICAL.value: 0, RecommendationPriority.HIGH.value: 1,
                     RecommendationPriority.MEDIUM.value: 2, RecommendationPriority.LOW.value: 3}
            for i in range(len(priorities) - 1):
                self.assertLessEqual(
                    order.get(priorities[i], 99),
                    order.get(priorities[i + 1], 99),
                    "Recommendations must be sorted CRITICAL → HIGH → MEDIUM → LOW"
                )

    def test_recommendation_has_all_required_fields(self):
        from backend.agents.reflection import InsightSynthesizer
        stats = {"voice": self._make_stats("voice", 0.30, avg_conf=0.40)}
        recs = InsightSynthesizer.synthesize(stats, [], {}, [])
        self.assertTrue(len(recs) > 0)
        for rec in recs:
            self.assertTrue(rec.id.startswith("REC-"))
            self.assertIn(rec.priority, ("CRITICAL", "HIGH", "MEDIUM", "LOW"))
            self.assertIsInstance(rec.recommendation, str)
            self.assertGreater(len(rec.recommendation), 0)
            self.assertGreater(rec.confidence, 0.0)
            self.assertLessEqual(rec.confidence, 1.0)

    def test_small_sample_skipped(self):
        """Agents with < 5 actions should not generate recommendations (insufficient data)."""
        from backend.agents.reflection import InsightSynthesizer
        stats = {"tiny": self._make_stats("tiny", 0.0, total=3)}  # only 3 actions
        recs = InsightSynthesizer.synthesize(stats, [], {}, [])
        agent_recs = [r for r in recs if "tiny" in r.observation]
        self.assertEqual(agent_recs, [])


# ══════════════════════════════════════════════════════════════════════════════
# 6.  Authority Boundary Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestReflectionAuthorityBoundaries(_ReflectBase):

    def test_reflection_agent_has_no_execute_method(self):
        from backend.agents.reflection import ReflectionAgent
        self.assertFalse(hasattr(ReflectionAgent, "execute"))

    def test_reflection_agent_has_no_intake_request_method(self):
        from backend.agents.reflection import ReflectionAgent
        self.assertFalse(hasattr(ReflectionAgent, "intake_request"))

    def test_reflection_agent_has_no_modify_policy_method(self):
        from backend.agents.reflection import ReflectionAgent
        self.assertFalse(hasattr(ReflectionAgent, "modify_policy"))

    def test_reflection_agent_has_no_write_capability_method(self):
        from backend.agents.reflection import ReflectionAgent
        self.assertFalse(hasattr(ReflectionAgent, "register_capability"))

    def test_reflection_agent_has_no_reject_plan_method(self):
        from backend.agents.reflection import ReflectionAgent
        self.assertFalse(hasattr(ReflectionAgent, "reject_plan"))

    def test_reflection_agent_has_no_approve_method(self):
        from backend.agents.reflection import ReflectionAgent
        self.assertFalse(hasattr(ReflectionAgent, "approve"))

    def test_reflection_agent_has_no_run_shell_method(self):
        from backend.agents.reflection import ReflectionAgent
        self.assertFalse(hasattr(ReflectionAgent, "run_shell"))

    def test_no_analyzer_has_execution_side_effects(self):
        """All 5 analysis modules must not have write/execute methods."""
        from backend.agents.reflection import (
            ConfidenceAnalyzer, RetryRollbackAnalyzer, ResourceCorrelator,
            PlannerPerformanceTracker, InsightSynthesizer,
        )
        forbidden = ("execute", "write_file", "delete", "run_shell", "intake_request", "approve")
        for cls in [ConfidenceAnalyzer, RetryRollbackAnalyzer, ResourceCorrelator,
                    PlannerPerformanceTracker, InsightSynthesizer]:
            for attr in forbidden:
                self.assertFalse(
                    hasattr(cls, attr),
                    f"Analyzer '{cls.__name__}' must not expose '{attr}'"
                )

    def test_recommendations_are_advisory_not_executed(self):
        """Synthesizer produces Recommendation objects — not executed instructions."""
        from backend.agents.reflection import InsightSynthesizer, AgentStats, Recommendation
        stats = {"voice": AgentStats(agent="voice", total_actions=20, verified_success=4,
                                     dve_failures=10, avg_confidence=0.35, success_rate=0.20)}
        recs = InsightSynthesizer.synthesize(stats, [], {}, [])
        for rec in recs:
            self.assertIsInstance(rec, Recommendation)
            # Recommendations are data objects — confirm no callable __call__
            self.assertFalse(callable(rec), "Recommendation must be a data object, not callable")


# ══════════════════════════════════════════════════════════════════════════════
# 7.  Report Persistence
# ══════════════════════════════════════════════════════════════════════════════

class TestReportPersistence(_ReflectBase):

    def test_report_persisted_to_disk(self):
        from backend.agents.reflection import ReflectionAgent, _reports_path
        # Run cycle with no source data
        ReflectionAgent.run_reflection_cycle()
        path = _reports_path()
        self.assertTrue(path.exists(), "Reports file should be created")
        reports = json.loads(path.read_text())
        self.assertIsInstance(reports, list)
        self.assertGreater(len(reports), 0)

    def test_report_capped_at_200(self):
        from backend.agents.reflection import ReflectionAgent, _reports_path
        for _ in range(205):
            ReflectionAgent.run_reflection_cycle()
        path = _reports_path()
        reports = json.loads(path.read_text())
        self.assertLessEqual(len(reports), 200)

    def test_report_has_required_keys(self):
        from backend.agents.reflection import ReflectionAgent
        report = ReflectionAgent.run_reflection_cycle()
        d = report.to_dict()
        for key in ("report_id", "timestamp", "window_actions", "agent_stats",
                    "resource_correlations", "plan_quality", "recommendations", "narrative"):
            self.assertIn(key, d, f"Report missing key: {key}")

    def test_report_id_is_unique(self):
        from backend.agents.reflection import ReflectionAgent
        r1 = ReflectionAgent.run_reflection_cycle()
        r2 = ReflectionAgent.run_reflection_cycle()
        self.assertNotEqual(r1.report_id, r2.report_id)

    def test_get_latest_report_returns_most_recent(self):
        from backend.agents.reflection import ReflectionAgent
        r1 = ReflectionAgent.run_reflection_cycle()
        r2 = ReflectionAgent.run_reflection_cycle()
        latest = ReflectionAgent.get_latest_report()
        self.assertIsNotNone(latest)
        self.assertEqual(latest["report_id"], r2.report_id)

    def test_get_latest_report_returns_none_when_empty(self):
        from backend.agents.reflection import ReflectionAgent
        from backend.core.config import runtime_data_root
        # Explicitly remove any reports file in this isolated root
        p = runtime_data_root() / "backend" / "data" / "reflection_reports.json"
        if p.exists():
            p.unlink()
        result = ReflectionAgent.get_latest_report()
        self.assertIsNone(result)


# ══════════════════════════════════════════════════════════════════════════════
# 8.  Full Reflection Cycle (E2E)
# ══════════════════════════════════════════════════════════════════════════════

class TestReflectionCycleE2E(_ReflectBase):

    def _populate_data(self):
        """Seed realistic data that should trigger recommendations."""
        now = time.time()

        # DVE evidence: voice agent failing frequently
        evidence = (
            [{"target_agent": "voice", "confidence_score": 0.20, "timestamp": now + i} for i in range(8)] +
            [{"target_agent": "voice", "confidence_score": 0.95, "timestamp": now + 10 + i} for i in range(2)] +
            [{"target_agent": "coder", "confidence_score": 0.95, "timestamp": now + 20 + i} for i in range(20)]
        )
        self._write_evidence(evidence)

        # Audit log: some rollbacks for voice
        audit = [
            {"agent": "voice", "approval_state": "ROLLBACK_STARTED", "requested_action": "VOICE_TTS", "execution_result": "failed"},
            {"agent": "coder", "approval_state": "auto_approved", "requested_action": "WRITE_FILE", "execution_result": "ok"},
        ]
        self._write_audit(audit)

        # Monitoring: high CPU during voice failures
        samples = [
            {"timestamp": now + i, "cpu_percent": 92.0, "ram_percent": 50.0}
            for i in range(8)
        ] + [
            {"timestamp": now + 20 + i, "cpu_percent": 30.0, "ram_percent": 40.0}
            for i in range(20)
        ]
        self._write_monitoring(samples)

    def test_cycle_produces_report(self):
        from backend.agents.reflection import ReflectionAgent
        self._populate_data()
        report = ReflectionAgent.run_reflection_cycle()
        self.assertIsNotNone(report)
        self.assertGreater(report.window_actions, 0)

    def test_cycle_detects_voice_reliability_issue(self):
        from backend.agents.reflection import ReflectionAgent
        self._populate_data()
        report = ReflectionAgent.run_reflection_cycle()
        agent_names = [s["agent"] for s in report.agent_stats]
        self.assertIn("voice", agent_names)

        voice_stat = next(s for s in report.agent_stats if s["agent"] == "voice")
        self.assertLess(voice_stat["success_rate"], 0.50)

    def test_cycle_generates_at_least_one_recommendation(self):
        from backend.agents.reflection import ReflectionAgent
        self._populate_data()
        report = ReflectionAgent.run_reflection_cycle()
        self.assertGreater(len(report.recommendations), 0)

    def test_cycle_narrative_is_non_empty_string(self):
        from backend.agents.reflection import ReflectionAgent
        report = ReflectionAgent.run_reflection_cycle()
        self.assertIsInstance(report.narrative, str)
        self.assertGreater(len(report.narrative), 50)

    def test_cycle_report_narrative_contains_report_header(self):
        from backend.agents.reflection import ReflectionAgent
        report = ReflectionAgent.run_reflection_cycle()
        self.assertIn("KATTAPPA REFLECTION REPORT", report.narrative)

    def test_cycle_with_no_data_does_not_crash(self):
        from backend.agents.reflection import ReflectionAgent
        from backend.core.config import runtime_data_root
        # Explicitly remove all data files to guarantee empty state
        data_dir = runtime_data_root() / "backend" / "data"
        for fname in (
            "verification_evidence.json",
            "action_broker_audit.log",
            "monitoring_stats.json",
            "reflection_reports.json",
        ):
            p = data_dir / fname
            if p.exists():
                p.unlink()
        # Run cycle — should return gracefully with no data
        report = ReflectionAgent.run_reflection_cycle()
        self.assertIsNotNone(report)
        self.assertEqual(report.window_actions, 0)
        self.assertEqual(report.recommendations, [])

    def test_agent_reliability_summary(self):
        from backend.agents.reflection import ReflectionAgent
        self._populate_data()
        summary = ReflectionAgent.get_agent_reliability_summary()
        self.assertIn("voice", summary)
        self.assertIn("success_rate", summary["voice"])
        self.assertIn("avg_confidence", summary["voice"])

    def test_reflection_node_updates_state(self):
        """LangGraph node must update state['result'] and append to state['logs']."""
        from backend.agents.reflection import reflection_node
        state = {"logs": [], "user_input": "test"}
        updated = reflection_node(state)
        self.assertIn("result", updated)
        self.assertTrue(len(updated["logs"]) > 0)
        self.assertIn("reflection:", updated["logs"][-1])


if __name__ == "__main__":
    unittest.main(verbosity=2)
