# test_goal_verification_engine.py
# ==================================
# Unit and integration test suite for Kattappa Step 8.5 Verification Engine (VE) Core
# and relationship trust updates.

import os
import tempfile
import unittest
import sqlite3
import time
import ast
import hashlib
from pathlib import Path
from unittest.mock import patch, MagicMock

# Environment isolation
os.environ.setdefault("KATTAPPA_ENV", "test")

from backend.core.verification_engine import (
    GoalVerificationEngine,
    VerificationState,
    GoalVerificationReport,
    EvidenceEngine,
    SuccessCriteriaEngine,
    ConstraintEngine,
    AuditEngine,
    ConfidenceEngine,
)
from backend.core.goal_memory import GoalMemory
from backend.core.project_memory import ProjectMemory
from backend.core.personal_project_manager import PersonalProjectManager
from backend.core.human_conversation_engine import HCEStore, TrustRecoveryEngine
from backend.core.relationship_memory import RelationshipMemory
from backend.core.memory_governance import MemoryGovernance
from backend.core.episodic_memory import EpisodicMemory
from backend.core.semantic_memory import SemanticMemory
from backend.core.human_memory import HumanMemoryStore

class NoCloseConnection:
    def __init__(self, conn):
        self._conn = conn

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


class TestGoalVerificationEngine(unittest.TestCase):

    def setUp(self):
        # Setup temporary folder to isolate any filesystem side-effects
        self.test_dir = tempfile.mkdtemp(prefix="kattappa_ve_test_")
        self.prev_root = os.environ.get("KATTAPPA_ROOT")
        os.environ["KATTAPPA_ROOT"] = self.test_dir

        # Create a single shared in-memory DB connection to ensure schema isolation during tests
        if not hasattr(self.__class__, "_shared_conn"):
            self.__class__._shared_conn = sqlite3.connect(":memory:", check_same_thread=False)
            self.__class__._shared_conn.row_factory = sqlite3.Row
            HCEStore._ensure_schema(self.__class__._shared_conn)
            RelationshipMemory._ensure_schema(self.__class__._shared_conn)
            MemoryGovernance._ensure_schema(self.__class__._shared_conn)
            EpisodicMemory._ensure_schema(self.__class__._shared_conn)
            GoalMemory._ensure_schema(self.__class__._shared_conn)
            ProjectMemory._ensure_schema(self.__class__._shared_conn)
            HumanMemoryStore._ensure_schema(self.__class__._shared_conn)

        # Clear HCE and memory tables between tests
        self.__class__._shared_conn.execute("DELETE FROM hce_relationships")
        self.__class__._shared_conn.execute("DELETE FROM hce_relationship_metrics")
        self.__class__._shared_conn.execute("DELETE FROM hm_entities")
        self.__class__._shared_conn.execute("DELETE FROM hm_preferences")
        self.__class__._shared_conn.execute("DELETE FROM hm_projects")
        self.__class__._shared_conn.execute("DELETE FROM hm_user_goals")
        self.__class__._shared_conn.execute("DELETE FROM goals")
        self.__class__._shared_conn.execute("DELETE FROM projects")
        self.__class__._shared_conn.commit()

        HCEStore._schema_ensured = True
        GoalMemory._schema_ensured = True
        ProjectMemory._schema_ensured = True

        # Patch connection getters to return our shared in-memory connection
        self.conn_patchers = [
            patch.object(HCEStore, "_get_conn", return_value=NoCloseConnection(self.__class__._shared_conn)),
            patch.object(RelationshipMemory, "_get_sqlite_conn", return_value=NoCloseConnection(self.__class__._shared_conn)),
            patch.object(MemoryGovernance, "_get_sqlite_conn", return_value=NoCloseConnection(self.__class__._shared_conn)),
            patch.object(EpisodicMemory, "_get_sqlite_conn", return_value=NoCloseConnection(self.__class__._shared_conn)),
            patch.object(GoalMemory, "_get_sqlite_conn", return_value=NoCloseConnection(self.__class__._shared_conn)),
            patch.object(PersonalProjectManager, "_get_sqlite_conn", return_value=NoCloseConnection(self.__class__._shared_conn)),
            patch.object(HumanMemoryStore, "_connect", return_value=NoCloseConnection(self.__class__._shared_conn)),
        ]
        for p in self.conn_patchers:
            p.start()

    def tearDown(self):
        for p in self.conn_patchers:
            p.stop()
        if self.prev_root:
            os.environ["KATTAPPA_ROOT"] = self.prev_root
        else:
            os.environ.pop("KATTAPPA_ROOT", None)
        import shutil
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_safety_rules_no_execution_imports(self):
        """Rule 1: Verification can never execute. No imports from execution modules."""
        engine_path = Path(__file__).parent.parent / "core" / "verification_engine.py"
        with open(engine_path, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=str(engine_path))
            
        execution_modules = {
            "backend.agents.coder",
            "backend.agents.browser",
            "backend.agents.desktop",
            "backend.agents.terminal",
            "backend.agents.voice",
            "backend.agents.voice_agent",
            "backend.agents.file_agent",
            "backend.agents.executive",
            "backend.agents.autonomous_agent",
            "backend.agents.self_improver",
            "backend.agents.strategy",
            "backend.agents.researcher",
            "backend.agents.safety_agent",
            "backend.agents.builder",
            "backend.agents.evaluator",
            "backend.agents.monitoring",
            "backend.agents.vision",
            "backend.agents.vision_agent"
        }
        
        imported_modules = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for name in node.names:
                    imported_modules.add(name.name)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_modules.add(node.module)
                for name in node.names:
                    imported_modules.add(f"{node.module}.{name.name}")
                    
        for exe_mod in execution_modules:
            for imp_mod in imported_modules:
                self.assertFalse(
                    imp_mod.startswith(exe_mod),
                    f"Safety Violation: VerificationEngine imports execution module '{imp_mod}'"
                )

    def test_evidence_engine_collect(self):
        """Rule 3: Verification evidence is never trusted by itself (collect files, MD5, and size)."""
        temp_file_path = os.path.join(self.test_dir, "evidence_test.txt")
        content = "verification_engine_test_content"
        with open(temp_file_path, "w", encoding="utf-8") as f:
            f.write(content)

        # Collect evidence
        evidence = EvidenceEngine.collect(
            file_paths=[temp_file_path, "nonexistent.txt"],
            log_check_events=["test_log_event"],
            api_responses=[{"endpoint": "/api/test", "status_code": 200}]
        )

        # Check temp file evidence
        self.assertIn(temp_file_path, evidence["files"])
        self.assertTrue(evidence["files"][temp_file_path]["exists"])
        self.assertEqual(evidence["files"][temp_file_path]["size"], len(content))
        self.assertEqual(evidence["files"][temp_file_path]["checksum"], hashlib.md5(content.encode("utf-8")).hexdigest())
        self.assertEqual(evidence["files"][temp_file_path]["content"], content)

        # Check nonexistent file evidence
        self.assertIn("nonexistent.txt", evidence["files"])
        self.assertFalse(evidence["files"]["nonexistent.txt"]["exists"])

        # Check logs and API
        self.assertEqual(len(evidence["logs"]), 1)
        self.assertEqual(evidence["logs"][0]["event"], "test_log_event")
        self.assertEqual(len(evidence["api_responses"]), 1)
        self.assertEqual(evidence["api_responses"][0]["endpoint"], "/api/test")
        self.assertEqual(evidence["api_responses"][0]["status_code"], 200)

    def test_success_criteria_engine_evaluate(self):
        """Test the SuccessCriteriaEngine independently evaluating checklist items."""
        temp_file_path = os.path.join(self.test_dir, "criteria_test.txt")
        content = "hello world, this is verification"
        
        evidence = {
            "files": {
                temp_file_path: {
                    "exists": True,
                    "size": len(content),
                    "content": content
                },
                "absent.txt": {
                    "exists": False
                }
            },
            "api_responses": [
                {"endpoint": "/health", "status_code": 200}
            ],
            "logs": [
                {"event": "system_booted"}
            ]
        }

        criteria = {
            f"file_exists: {temp_file_path}": True,
            "file_exists: absent.txt": False,
            f"file_contains: {temp_file_path} -> verification": True,
            f"file_contains: {temp_file_path} -> missing": False,
            "api_status: /health": 200,
            "log_event: system_booted": True,
            "log_event: system_crashed": False
        }

        results = SuccessCriteriaEngine.evaluate(criteria, evidence)
        
        self.assertTrue(results[f"file_exists: {temp_file_path}"])
        self.assertTrue(results["file_exists: absent.txt"])
        self.assertTrue(results[f"file_contains: {temp_file_path} -> verification"])
        self.assertFalse(results[f"file_contains: {temp_file_path} -> missing"])
        self.assertTrue(results["api_status: /health"])
        self.assertTrue(results["log_event: system_booted"])
        self.assertFalse(results["log_event: system_crashed"])

    def test_constraint_engine_validate(self):
        """Test ConstraintEngine bounds limits (time, token budget, safety paths)."""
        # Scenario 1: All constraints passed
        constraints = {
            "max_time_seconds": 60.0,
            "max_cost_tokens": 1000
        }
        evidence = {
            "time_spent_seconds": 45.5,
            "cost_tokens": 800,
            "files": {
                "safe_file.txt": {}
            }
        }
        
        with patch("backend.core.action_broker.ActionBroker.is_safe_workspace_path", return_value=True):
            res = ConstraintEngine.validate(constraints, evidence)
            self.assertTrue(res["time_limit"]["passed"])
            self.assertTrue(res["cost_limit"]["passed"])
            self.assertTrue(res["safety_limit"]["passed"])

        # Scenario 2: Constraints violated
        evidence_violating = {
            "time_spent_seconds": 120.0,
            "cost_tokens": 2000,
            "files": {
                "/absolute/unsafe/path.py": {}
            }
        }
        
        with patch("backend.core.action_broker.ActionBroker.is_safe_workspace_path", return_value=False):
            res_fail = ConstraintEngine.validate(constraints, evidence_violating)
            self.assertFalse(res_fail["time_limit"]["passed"])
            self.assertFalse(res_fail["cost_limit"]["passed"])
            self.assertFalse(res_fail["safety_limit"]["passed"])
            self.assertIn("Unsafe path detected", res_fail["safety_limit"]["details"])

    def test_audit_engine_contradiction_and_fabrication(self):
        """Test AuditEngine contradiction and fabrication check flags."""
        # 1. Contradiction: File does not exist but has size > 0 or has content
        evidence_contradict_1 = {
            "files": {
                "ghost.txt": {"exists": False, "size": 10}
            }
        }
        res_contradict_1 = AuditEngine.audit(evidence_contradict_1, {"dummy": True}, {})
        self.assertFalse(res_contradict_1["passed"])
        self.assertTrue(any("reported non-existent but has size" in issue for issue in res_contradict_1["issues"]))

        # 2. Contradiction: File has size 0 but non-empty content
        evidence_contradict_2 = {
            "files": {
                "empty.txt": {"exists": True, "size": 0, "content": "not_empty"}
            }
        }
        res_contradict_2 = AuditEngine.audit(evidence_contradict_2, {"dummy": True}, {})
        self.assertFalse(res_contradict_2["passed"])
        self.assertTrue(any("has size 0 but non-empty content" in issue for issue in res_contradict_2["issues"]))

        # 3. Fabrication: File has non-zero size but empty MD5 checksum
        evidence_fabricate = {
            "files": {
                "forged.txt": {
                    "exists": True,
                    "size": 120,
                    "checksum": "d41d8cd98f00b204e9800998ecf8427e" # MD5 for empty string
                }
            }
        }
        res_fabricate = AuditEngine.audit(evidence_fabricate, {"dummy": True}, {})
        self.assertFalse(res_fabricate["passed"])
        self.assertTrue(any("non-zero size but empty MD5 checksum" in issue for issue in res_fabricate["issues"]))

    def test_confidence_engine_scoring(self):
        """Test ConfidenceEngine calculates correct score and penalty reductions."""
        # Baseline score: 3 of 4 criteria passed = 0.75
        criteria = {"c1": True, "c2": True, "c3": True, "c4": False}
        
        # Scenario 1: All constraints passed, audit passed
        score_base = ConfidenceEngine.score(criteria, {}, {"passed": True})
        self.assertEqual(score_base, 0.75)

        # Scenario 2: Constraint failed (non-safety, e.g., budget) -> -0.20 penalty
        constraints_failed = {
            "cost_limit": {"passed": False, "details": "Cost limit exceeded"}
        }
        score_penalty_1 = ConfidenceEngine.score(criteria, constraints_failed, {"passed": True})
        self.assertEqual(score_penalty_1, 0.55)

        # Scenario 3: Audit failed -> -0.40 penalty
        score_penalty_2 = ConfidenceEngine.score(criteria, {}, {"passed": False})
        self.assertEqual(score_penalty_2, 0.35)

        # Scenario 4: Safety limit failed -> Instant 0.0 confidence score
        constraints_safety_failed = {
            "safety_limit": {"passed": False, "details": "Unsafe path detected"}
        }
        score_safety_fail = ConfidenceEngine.score(criteria, constraints_safety_failed, {"passed": True})
        self.assertEqual(score_safety_fail, 0.0)

    def test_goal_verification_engine_verify_goal(self):
        """Test GoalVerificationEngine orchestrates the full pipeline and returns correct report."""
        goal_id = "goal_999"
        temp_file = os.path.join(self.test_dir, "output_report.txt")
        with open(temp_file, "w", encoding="utf-8") as f:
            f.write("verified content")

        evidence_params = {
            "file_paths": [temp_file],
            "time_spent_seconds": 15.0,
            "cost_tokens": 120
        }
        success_criteria = {
            f"file_exists: {temp_file}": True,
            f"file_contains: {temp_file} -> verified": True
        }
        constraints = {
            "max_time_seconds": 30.0,
            "max_cost_tokens": 500
        }

        # Successful verification
        with patch("backend.core.action_broker.ActionBroker.is_safe_workspace_path", return_value=True):
            report = GoalVerificationEngine.verify_goal(
                goal_id=goal_id,
                evidence_params=evidence_params,
                success_criteria=success_criteria,
                constraints=constraints
            )
            self.assertEqual(report.goal_id, goal_id)
            self.assertEqual(report.state, VerificationState.VERIFIED)
            self.assertEqual(report.confidence_score, 1.0)
            self.assertTrue(report.audit_passed)
            
            report_dict = report.to_dict()
            self.assertEqual(report_dict["state"], "VERIFIED")

    def test_hce_trust_updates(self):
        """Test that verified outcome outcomes adjust HCE relationship trust metrics correctly."""
        user_id = "user_rel_test"
        goal_id = "goal_rel_test"
        proj_id = "ppm_proj_rel_test"

        # 1. Initialize HCE relationship
        rel = HCEStore.create_relationship(user_id, "Trust Testing User")
        rel_id = rel["relationship_id"]

        # Verify initial trust score is default 50.0
        initial_metrics = HCEStore.get_metrics(rel_id)
        self.assertEqual(initial_metrics["trust_score"], 50.0)

        # 2. Setup project mapping back to goal
        # Since _update_hce_trust queries SQLite to find linked projects, insert records manually
        self.__class__._shared_conn.execute(
            "INSERT INTO projects (project_id, linked_goal_id, name, status, created_at) VALUES (?, ?, ?, ?, ?)",
            (proj_id, goal_id, "Relationship PPM Project", "PROPOSED", time.time())
        )
        self.__class__._shared_conn.commit()

        # Mock PPM get_project returning the custom mock project with user_entity_id matching user_id
        mock_proj = {
            "project_id": proj_id,
            "linked_goal_id": goal_id,
            "title": "Relationship PPM Project",
            "user_entity_id": user_id
        }

        # 3. Test verification success -> Increases trust (+2.0 points)
        with patch.object(PersonalProjectManager, "get_project", return_value=mock_proj):
            # Trigger successful verified outcome callback
            GoalVerificationEngine._update_hce_trust(goal_id, VerificationState.VERIFIED)
            
            updated_metrics = HCEStore.get_metrics(rel_id)
            self.assertEqual(updated_metrics["trust_score"], 52.0)

            # 4. Test verification failure -> Decreases trust via TrustRecoveryEngine
            GoalVerificationEngine._update_hce_trust(goal_id, VerificationState.FAILED)
            
            failed_metrics = HCEStore.get_metrics(rel_id)
            self.assertEqual(failed_metrics["trust_score"], 50.0)


if __name__ == "__main__":
    unittest.main()
