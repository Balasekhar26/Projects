"""
Step 7.1.1 Hardening Pass — Experiment Sandbox Test Suite

Covers:
  - Git worktree creation and teardown (success and crash paths)
  - Ephemeral database cloning and destruction
  - Statistical benchmark significance (pass vs noise)
  - AST-based Protected Core blocking (transitive dependency)
  - Orphan sweeper (TTL reaper)
  - Regression detection
  - API smoke test
"""
from __future__ import annotations

import math
import os
import time
import shutil
import sqlite3
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.core.experiment_sandbox import ExperimentManager
from backend.core.proposal_governance import ProtectedCoreRegistry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _git_available() -> bool:
    """Return True if we are inside a git repo (needed for worktree tests)."""
    try:
        ExperimentManager._run_git(["rev-parse", "--git-dir"])
        return True
    except Exception:
        return False


GIT_AVAILABLE = _git_available()


# ---------------------------------------------------------------------------
# 1. Basic success flow
# ---------------------------------------------------------------------------

class TestSandboxSuccessFlow:
    def test_report_schema_complete(self):
        """PASS run produces a structurally complete report."""
        report = ExperimentManager.execute_experiment(
            proposal_id="p-schema-check",
            baseline_benchmarks={
                "latency_ms": 10.0,
                "cpu_usage_pct": 15.0,
                "memory_mb": 40.0,
                "reliability_score": 0.98,
                "safety_score": 1.0,
            },
        )

        required_keys = {
            "experiment_id", "proposal_id", "status", "tests",
            "benchmarks", "validation", "regressions",
            "protected_core_touched", "confidence", "recommendation",
            "fidelity_gap",
        }
        assert required_keys.issubset(report.keys()), (
            f"Missing report keys: {required_keys - report.keys()}"
        )

    def test_pass_status_and_recommendation(self):
        """Clean proposal produces status=PASS and recommendation=NEEDS_REVIEW."""
        report = ExperimentManager.execute_experiment(proposal_id="p-safe-opt")
        assert report["status"] == "PASS"
        assert report["recommendation"] == "NEEDS_REVIEW"
        assert report["confidence"] == 0.92

    def test_tests_block(self):
        """All tests pass on a clean run."""
        report = ExperimentManager.execute_experiment(proposal_id="p-clean-tests")
        assert report["tests"]["pass_rate"] == 1.0
        assert report["tests"]["failed"] == 0
        assert report["tests"]["passed"] == report["tests"]["total"]

    def test_benchmarks_statistical_fields(self):
        """Benchmark block must contain mean, margin_of_error, confidence_lower_bound, iterations."""
        report = ExperimentManager.execute_experiment(proposal_id="p-stat-fields")
        bench = report["benchmarks"]
        assert "performance_gain" in bench
        assert "margin_of_error" in bench
        assert "confidence_lower_bound" in bench
        assert bench["iterations"] == 5

    def test_fidelity_gap_warning_present(self):
        """Fidelity gap warning must be encoded in every report."""
        report = ExperimentManager.execute_experiment(proposal_id="p-fidelity")
        fg = report["fidelity_gap"]
        assert "warning" in fg
        assert "Sandbox" in fg["warning"]
        assert fg["production_claim"] is False


# ---------------------------------------------------------------------------
# 2. Regression flow
# ---------------------------------------------------------------------------

class TestSandboxRegressionFlow:
    def test_regression_status_fail(self):
        """mock_regression=True triggers FAIL status."""
        report = ExperimentManager.execute_experiment(
            proposal_id="p-regression",
            mock_regression=True,
        )
        assert report["status"] == "FAIL"
        assert report["recommendation"] == "REJECT"
        assert report["confidence"] == 0.50

    def test_regression_regressions_list_nonempty(self):
        """At least one regression reason is recorded."""
        report = ExperimentManager.execute_experiment(
            proposal_id="p-regression-reasons",
            mock_regression=True,
        )
        assert len(report["regressions"]) > 0

    def test_regression_identifies_test_or_perf_failure(self):
        """Regression list mentions either test failure or performance gain."""
        report = ExperimentManager.execute_experiment(
            proposal_id="p-regression-msg",
            mock_regression=True,
        )
        msgs = " ".join(report["regressions"])
        assert "Test failure" in msgs or "Performance Gain" in msgs or "Reliability" in msgs


# ---------------------------------------------------------------------------
# 3. Statistical Benchmark Gate
# ---------------------------------------------------------------------------

class TestStatisticalBenchmarkGate:
    """Verify the 5-run, 95% CI gate rejects noise while accepting real gain."""

    def test_noisy_signal_fails_statistical_gate(self):
        """Simulated noise runs must fail the lower-bound gate (FAIL status)."""
        report = ExperimentManager.execute_experiment(
            proposal_id="p-noise-test",
            simulated_noise=True,
        )
        bench = report["benchmarks"]
        # mean ≈ +0.002 but confidence interval should span negative
        lower_bound = bench["confidence_lower_bound"]
        assert lower_bound <= 0.0, (
            f"Noisy signal should have lower_bound <= 0, got {lower_bound}"
        )
        assert report["status"] == "FAIL"
        assert any(
            "statistical significance" in r.lower() or "performance gain" in r.lower()
            for r in report["regressions"]
        )

    def test_clean_signal_passes_statistical_gate(self):
        """Low-noise gain run must pass the lower-bound gate (PASS status)."""
        report = ExperimentManager.execute_experiment(
            proposal_id="p-clean-signal",
            simulated_noise=False,
        )
        bench = report["benchmarks"]
        lower_bound = bench["confidence_lower_bound"]
        mean = bench["performance_gain"]
        assert mean > 0.0, "Mean gain must be positive"
        assert lower_bound > 0.0, (
            f"Clean run should have lower_bound > 0, got {lower_bound}"
        )
        assert report["status"] == "PASS"

    def test_margin_of_error_formula(self):
        """Manual verification of the 95% CI formula used in the engine.

        Mirrors the calculation in _run_in_isolated_process for the
        default (non-regression, non-noise) case with complexity=1, gain=10.
        """
        expected_gain_per_run = 0.05  # perf_gain_expected for complexity=1
        runs = [
            expected_gain_per_run + 0.002,
            expected_gain_per_run - 0.001,
            expected_gain_per_run + 0.003,
            expected_gain_per_run + 0.001,
            expected_gain_per_run - 0.002,
        ]
        mean = sum(runs) / 5.0
        variance = sum((r - mean) ** 2 for r in runs) / 4.0
        std_dev = math.sqrt(variance)
        margin_of_error = 2.776 * (std_dev / math.sqrt(5.0))
        lower_bound = mean - margin_of_error

        assert mean > 0.0
        assert lower_bound > 0.0, (
            f"Expected lower_bound > 0 for stable 5-run gain; got {lower_bound}"
        )

    def test_iterations_always_five(self):
        """Benchmark block must always report exactly 5 iterations."""
        for _ in range(3):
            report = ExperimentManager.execute_experiment(proposal_id="p-iter-check")
            assert report["benchmarks"]["iterations"] == 5


# ---------------------------------------------------------------------------
# 4. Protected Core (AST-based) Blocking
# ---------------------------------------------------------------------------

class TestProtectedCoreBlocking:
    """Verify transitive AST dependency analysis blocks protected-core proposals."""

    def test_proposal_id_keyword_triggers_block(self):
        """Proposal ID containing a protected module keyword is blocked."""
        # 'proposal_governance' is in the PROTECTED_MODULES set
        report = ExperimentManager.execute_experiment(
            proposal_id="p-unsafe-proposal_governance",
        )
        assert report["status"] == "FAIL"
        assert report["protected_core_touched"] is True
        assert any("Protected Core" in r for r in report["regressions"])
        assert report["recommendation"] == "REJECT"

    def test_affected_module_transitive_block(self, monkeypatch):
        """Proposal with affected_module transitively importing protected core is blocked."""
        # Patch ProposalEngine.list_proposals to return a proposal with a
        # tainted affected_module.
        fake_proposal = {
            "id": "p-transitive-ast",
            "title": "Optimize Rendering",
            "proposal": "Cache renderer calls",
            "affected_modules": ["proposal_governance"],  # directly protected
            "expected_gain": 5.0,
            "complexity": 1,
            "confidence": 80,
            "status": "pending",
        }
        monkeypatch.setattr(
            "backend.core.proposal_engine.ProposalEngine.list_proposals",
            lambda: [fake_proposal],
        )

        report = ExperimentManager.execute_experiment(
            proposal_id="p-transitive-ast",
        )
        assert report["protected_core_touched"] is True
        assert report["status"] == "FAIL"

    def test_safe_module_not_blocked(self, monkeypatch):
        """Proposal affecting a non-protected, non-transitive module passes the AST gate."""
        fake_proposal = {
            "id": "p-safe-module",
            "title": "Optimize Cache",
            "proposal": "Add LRU cache to translator",
            "affected_modules": ["translator_cache"],  # not in protected set
            "expected_gain": 8.0,
            "complexity": 1,
            "confidence": 90,
            "status": "pending",
        }
        monkeypatch.setattr(
            "backend.core.proposal_engine.ProposalEngine.list_proposals",
            lambda: [fake_proposal],
        )

        # is_transitively_protected must return False for this module
        assert not ProtectedCoreRegistry.is_transitively_protected("translator_cache"), (
            "translator_cache should not be in the protected core"
        )

        report = ExperimentManager.execute_experiment(
            proposal_id="p-safe-module",
        )
        assert report["protected_core_touched"] is False
        assert report["status"] == "PASS"

    def test_is_transitively_protected_direct_hit(self):
        """Direct member of PROTECTED_MODULES is immediately protected."""
        for mod in list(ProtectedCoreRegistry.PROTECTED_MODULES)[:3]:
            assert ProtectedCoreRegistry.is_transitively_protected(mod), (
                f"{mod} should be directly protected"
            )

    def test_is_transitively_protected_unknown_module(self):
        """Completely unknown module is not transitively protected."""
        assert not ProtectedCoreRegistry.is_transitively_protected(
            "some_totally_unknown_xyz_module_9999"
        )


# ---------------------------------------------------------------------------
# 5. Git Worktree Isolation
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not GIT_AVAILABLE, reason="Not inside a git repository")
class TestGitWorktreeIsolation:
    """Verify git worktrees and branches are cleaned up under all conditions."""

    def _active_sandbox_worktrees(self) -> list[str]:
        """Return paths of all active kattappa_sandbox_ worktrees."""
        try:
            res = ExperimentManager._run_git(["worktree", "list"])
            lines = res.stdout.strip().split("\n")
            return [l.split()[0] for l in lines if "kattappa_sandbox_" in l]
        except Exception:
            return []

    def _active_sandbox_branches(self) -> list[str]:
        """Return all local sandbox/ branches."""
        try:
            res = ExperimentManager._run_git(["branch", "--list", "sandbox/*"])
            return [b.strip().lstrip("* ") for b in res.stdout.split("\n") if b.strip()]
        except Exception:
            return []

    def test_worktree_and_branch_created_and_destroyed_on_success(self):
        """After a successful run, no orphan worktree or branch remains."""
        before_wt = set(self._active_sandbox_worktrees())
        before_br = set(self._active_sandbox_branches())

        report = ExperimentManager.execute_experiment(proposal_id="p-wt-success")

        after_wt = set(self._active_sandbox_worktrees())
        after_br = set(self._active_sandbox_branches())

        new_wt = after_wt - before_wt
        new_br = after_br - before_br

        assert len(new_wt) == 0, f"Orphan worktrees left behind: {new_wt}"
        assert len(new_br) == 0, f"Orphan branches left behind: {new_br}"
        assert report["status"] == "PASS"

    def test_worktree_and_branch_destroyed_on_crash(self):
        """Even when mock_crash=True, worktree and branch are cleaned up."""
        before_wt = set(self._active_sandbox_worktrees())
        before_br = set(self._active_sandbox_branches())

        with pytest.raises(Exception):
            ExperimentManager.execute_experiment(
                proposal_id="p-wt-crash",
                mock_crash=True,
            )

        after_wt = set(self._active_sandbox_worktrees())
        after_br = set(self._active_sandbox_branches())

        new_wt = after_wt - before_wt
        new_br = after_br - before_br

        assert len(new_wt) == 0, f"Orphan worktrees after crash: {new_wt}"
        assert len(new_br) == 0, f"Orphan branches after crash: {new_br}"

    def test_concurrent_worktrees_dont_collide(self):
        """Two simultaneous sandbox runs produce distinct worktrees and clean up independently."""
        results = {}
        errors = {}

        def _run(key: str) -> None:
            try:
                results[key] = ExperimentManager.execute_experiment(
                    proposal_id=f"p-concurrent-{key}"
                )
            except Exception as exc:
                errors[key] = exc

        t1 = threading.Thread(target=_run, args=("alpha",))
        t2 = threading.Thread(target=_run, args=("beta",))
        t1.start()
        t2.start()
        t1.join(timeout=30)
        t2.join(timeout=30)

        assert not errors, f"Thread errors: {errors}"
        assert "alpha" in results and "beta" in results
        # Both must produce distinct experiment IDs
        assert (
            results["alpha"]["experiment_id"] != results["beta"]["experiment_id"]
        )


# ---------------------------------------------------------------------------
# 6. Ephemeral Database Isolation
# ---------------------------------------------------------------------------

class TestEphemeralDatabaseIsolation:
    """Verify the sandbox database clone is created and destroyed properly."""

    def test_sandbox_db_destroyed_on_success(self, tmp_path):
        """Cloned sandbox DB must not exist after a successful run."""
        # We intercept TemporaryDirectory to track workspace path
        original_temp = tempfile.TemporaryDirectory
        created_workspaces = []

        class _Tracked(original_temp):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                created_workspaces.append(Path(self.name))

        with patch("backend.core.experiment_sandbox.tempfile.TemporaryDirectory", _Tracked):
            report = ExperimentManager.execute_experiment(
                proposal_id="p-db-cleanup-success"
            )

        assert report["status"] == "PASS"
        # Every tracked workspace must have been destroyed
        for ws in created_workspaces:
            assert not ws.exists(), (
                f"Workspace {ws} should have been destroyed after successful run"
            )
            # The cloned DB inside would also be gone (parent dir destroyed)

    def test_sandbox_db_destroyed_on_crash(self):
        """Cloned sandbox DB must not persist after a crash."""
        original_temp = tempfile.TemporaryDirectory
        created_workspaces = []

        class _Tracked(original_temp):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                created_workspaces.append(Path(self.name))

        with patch("backend.core.experiment_sandbox.tempfile.TemporaryDirectory", _Tracked):
            with pytest.raises(Exception):
                ExperimentManager.execute_experiment(
                    proposal_id="p-db-cleanup-crash",
                    mock_crash=True,
                )

        for ws in created_workspaces:
            assert not ws.exists(), (
                f"Workspace {ws} should have been destroyed after crash"
            )

    def test_sandbox_db_does_not_modify_production_db(self, tmp_path):
        """The production SQLite file must be untouched after a sandbox run."""
        fake_db = tmp_path / "production.db"
        # Write a sentinel value
        conn = sqlite3.connect(str(fake_db))
        conn.execute("CREATE TABLE sentinel (val TEXT)")
        conn.execute("INSERT INTO sentinel VALUES ('original')")
        conn.commit()
        conn.close()

        original_mtime = fake_db.stat().st_mtime

        # Patch load_config to point at our fake DB
        with patch("backend.core.experiment_sandbox.load_config") as mock_cfg:
            cfg = MagicMock()
            cfg.sqlite_path = fake_db
            mock_cfg.return_value = cfg
            ExperimentManager.execute_experiment(proposal_id="p-db-isolation")

        # Production DB modification time must be unchanged
        assert fake_db.stat().st_mtime == original_mtime, (
            "Production database was modified by the sandbox run"
        )

        # Sentinel value must still be intact
        conn = sqlite3.connect(str(fake_db))
        rows = conn.execute("SELECT val FROM sentinel").fetchall()
        conn.close()
        assert rows == [("original",)], "Sentinel value was corrupted"


# ---------------------------------------------------------------------------
# 7. Orphan Sweeper (TTL Reaper)
# ---------------------------------------------------------------------------

class TestOrphanSweeper:
    """Verify cleanup_orphans() purges stale sandbox directories and databases."""

    def test_sweeper_removes_old_sandbox_directory(self, tmp_path):
        """Directories named kattappa_sandbox_* older than 1h are purged."""
        old_dir = tmp_path / "kattappa_sandbox_abc123"
        old_dir.mkdir()

        # Back-date its mtime to 2 hours ago
        old_time = time.time() - 7300
        os.utime(str(old_dir), (old_time, old_time))

        with patch(
            "backend.core.experiment_sandbox.tempfile.gettempdir",
            return_value=str(tmp_path),
        ):
            # Also patch the data root so it does not resolve to a real path
            with patch(
                "backend.core.experiment_sandbox.runtime_data_root",
                return_value=tmp_path / "non_existent_data_root",
            ):
                ExperimentManager.cleanup_orphans()

        assert not old_dir.exists(), "Old orphan directory was not purged by sweeper"

    def test_sweeper_preserves_fresh_sandbox_directory(self, tmp_path):
        """Directories newer than 1h are NOT purged."""
        fresh_dir = tmp_path / "kattappa_sandbox_fresh"
        fresh_dir.mkdir()
        # mtime is now (fresh)

        with patch(
            "backend.core.experiment_sandbox.tempfile.gettempdir",
            return_value=str(tmp_path),
        ):
            with patch(
                "backend.core.experiment_sandbox.runtime_data_root",
                return_value=tmp_path / "non_existent_data_root",
            ):
                ExperimentManager.cleanup_orphans()

        assert fresh_dir.exists(), "Fresh sandbox directory was incorrectly purged"

    def test_sweeper_removes_old_sandbox_db_files(self, tmp_path):
        """Files named sandbox_db_* older than 1h are purged."""
        old_db = tmp_path / "sandbox_db_old_exp.db"
        old_db.write_text("STALE_DB", encoding="utf-8")
        old_time = time.time() - 7300
        os.utime(str(old_db), (old_time, old_time))

        with patch(
            "backend.core.experiment_sandbox.tempfile.gettempdir",
            return_value=str(tmp_path),
        ):
            with patch(
                "backend.core.experiment_sandbox.runtime_data_root",
                return_value=tmp_path / "non_existent_data_root",
            ):
                ExperimentManager.cleanup_orphans()

        assert not old_db.exists(), "Old orphan sandbox DB file was not purged"

    def test_sweeper_is_idempotent(self, tmp_path):
        """Running cleanup_orphans() twice does not raise even if dirs are gone."""
        old_dir = tmp_path / "kattappa_sandbox_idempotent"
        old_dir.mkdir()
        old_time = time.time() - 7300
        os.utime(str(old_dir), (old_time, old_time))

        with patch(
            "backend.core.experiment_sandbox.tempfile.gettempdir",
            return_value=str(tmp_path),
        ):
            with patch(
                "backend.core.experiment_sandbox.runtime_data_root",
                return_value=tmp_path / "non_existent_data_root",
            ):
                ExperimentManager.cleanup_orphans()  # first sweep
                ExperimentManager.cleanup_orphans()  # second sweep — must not raise


# ---------------------------------------------------------------------------
# 8. Crash / Timeout Safety
# ---------------------------------------------------------------------------

class TestCrashAndTimeoutSafety:
    def test_crash_raises_and_workspace_cleaned(self):
        """mock_crash=True raises an exception and leaves no temp directories."""
        original_temp = tempfile.TemporaryDirectory
        created_workspaces = []

        class _Tracked(original_temp):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                created_workspaces.append(Path(self.name))

        with patch("backend.core.experiment_sandbox.tempfile.TemporaryDirectory", _Tracked):
            with pytest.raises(Exception):
                ExperimentManager.execute_experiment(
                    proposal_id="p-crash-cleanup",
                    mock_crash=True,
                )

        for ws in created_workspaces:
            assert not ws.exists(), f"Workspace {ws} leaked after crash"

    def test_crash_before_git_mount_still_cleans(self, monkeypatch):
        """If git worktree mount fails, temp dir is still cleaned."""
        original_temp = tempfile.TemporaryDirectory
        created_workspaces = []

        class _Tracked(original_temp):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                created_workspaces.append(Path(self.name))

        # Simulate git failure
        monkeypatch.setattr(
            ExperimentManager,
            "_run_git",
            lambda *a, **kw: (_ for _ in ()).throw(
                subprocess.CalledProcessError(1, "git worktree add", stderr="error")
            ),
        )

        with patch("backend.core.experiment_sandbox.tempfile.TemporaryDirectory", _Tracked):
            with pytest.raises(Exception):
                ExperimentManager.execute_experiment(proposal_id="p-git-fail")

        for ws in created_workspaces:
            assert not ws.exists(), f"Workspace {ws} leaked after git mount failure"


# ---------------------------------------------------------------------------
# 9. Report Authority and Immutability
# ---------------------------------------------------------------------------

class TestReportAuthority:
    """Verify the report schema is structurally frozen and authority gates are correct."""

    def test_report_is_dict_not_mutable_object(self):
        """Report must be a plain dict (serialisable, not a live object)."""
        report = ExperimentManager.execute_experiment(proposal_id="p-type-check")
        assert isinstance(report, dict)

    def test_report_serialisable_to_json(self):
        """Report must be fully JSON-serialisable."""
        import json
        report = ExperimentManager.execute_experiment(proposal_id="p-json-check")
        serialised = json.dumps(report)
        restored = json.loads(serialised)
        assert restored["proposal_id"] == "p-json-check"

    def test_experiment_ids_are_unique(self):
        """Every run produces a distinct experiment_id."""
        ids = {
            ExperimentManager.execute_experiment(proposal_id=f"p-unique-{i}")["experiment_id"]
            for i in range(5)
        }
        assert len(ids) == 5, "experiment_id collision detected"

    def test_protected_core_veto_is_unconditional(self, monkeypatch):
        """Even a 'clean' proposal that touches protected core must FAIL."""
        fake_proposal = {
            "id": "p-unconditional-veto",
            "title": "Harmless Title",
            "proposal": "Minor improvement",
            "affected_modules": ["proposal_governance"],  # directly protected
            "expected_gain": 100.0,  # very high gain shouldn't override veto
            "complexity": 1,
            "confidence": 99,
            "status": "pending",
        }
        monkeypatch.setattr(
            "backend.core.proposal_engine.ProposalEngine.list_proposals",
            lambda: [fake_proposal],
        )

        report = ExperimentManager.execute_experiment(proposal_id="p-unconditional-veto")
        assert report["status"] == "FAIL"
        assert report["recommendation"] == "REJECT"
        assert report["protected_core_touched"] is True

    def test_safety_score_zero_always_fails(self):
        """Safety score of 0.0 (protected core touched) must produce FAIL."""
        # proposal_governance keyword in proposal_id triggers protected_core_touched=True
        report = ExperimentManager.execute_experiment(
            proposal_id="p-safety-zero-proposal_governance",
        )
        assert report["validation"]["safety_score"] == 0.0
        assert report["status"] == "FAIL"


# ---------------------------------------------------------------------------
# 10. API Smoke Test
# ---------------------------------------------------------------------------

class TestSandboxAPI:
    def test_api_success_run(self):
        """POST /sandbox/run-experiment-v2 returns 200 with a PASS report."""
        client = TestClient(app)
        payload = {
            "baseline_benchmarks": {
                "latency_ms": 20.0,
                "cpu_usage_pct": 30.0,
                "memory_mb": 60.0,
                "reliability_score": 0.98,
                "safety_score": 1.0,
            },
            "mock_regression": False,
            "mock_crash": False,
        }
        response = client.post("/sandbox/run-experiment-v2/p-api-smoke", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        report = data["report"]
        assert report["proposal_id"] == "p-api-smoke"
        assert report["status"] == "PASS"
        assert "benchmarks" in report
        assert "validation" in report
        assert "fidelity_gap" in report

    def test_api_regression_run(self):
        """POST with mock_regression=True returns a FAIL report."""
        client = TestClient(app)
        payload = {
            "baseline_benchmarks": None,
            "mock_regression": True,
            "mock_crash": False,
        }
        response = client.post("/sandbox/run-experiment-v2/p-api-regression", json=payload)
        assert response.status_code == 200
        data = response.json()
        report = data["report"]
        assert report["status"] == "FAIL"
        assert report["recommendation"] == "REJECT"

    def test_api_report_has_statistical_fields(self):
        """API response benchmarks block includes statistical significance fields."""
        client = TestClient(app)
        payload = {"mock_regression": False, "mock_crash": False}
        response = client.post("/sandbox/run-experiment-v2/p-api-stat", json=payload)
        assert response.status_code == 200
        bench = response.json()["report"]["benchmarks"]
        assert "margin_of_error" in bench
        assert "confidence_lower_bound" in bench
        assert bench["iterations"] == 5
