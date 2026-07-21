from __future__ import annotations

import unittest
from unittest.mock import patch, MagicMock
import json

from backend.core.config import load_config
from backend.agents.planner import PlannerAgent, planner_node
from backend.core.reflection_engine import ReflectionEngine
from backend.core.failure_recovery import FailureRecoveryEngine
from backend.core.context.models import ContextItem, ContextPriority, ContextSource
from backend.core.context.compression import CompressionEngine as ContextCompressionEngine
from backend.core.human_memory import CompressionEngine as MemoryCompressionEngine
from backend.core.safety import classify_risk, RiskDecision


class TestCognitiveWorkers(unittest.TestCase):

    def test_config_registry(self):
        """Verifies new cognitive roles are registered in the BackendConfig model_map."""
        cfg = load_config()
        self.assertIn("planning", cfg.model_map)
        self.assertIn("reflection", cfg.model_map)
        self.assertIn("recovery", cfg.model_map)
        self.assertIn("compression", cfg.model_map)
        self.assertIn("safety", cfg.model_map)
        
        self.assertEqual(cfg.model_map["planning"], "glm-5.2")
        self.assertEqual(cfg.model_map["reflection"], "glm-5.2")
        self.assertEqual(cfg.model_map["recovery"], "glm-5.2")
        self.assertEqual(cfg.model_map["compression"], "glm-5.2")
        self.assertEqual(cfg.model_map["safety"], "glm-5.2")

    @patch("backend.core.planner.planner_engine._should_use_mock_planner", return_value=False)
    @patch("backend.core.planner.planner_engine.ask_model")
    def test_planner_routing(self, mock_ask_model, _mock_mode):
        """Verifies planner CoT and decomposition route requests to the planning model."""
        mock_ask_model.return_value = '[]'
        
        # Test Decomposition
        with patch(
            "backend.core.skills.skill_selector.SkillSelector.select_skill",
            return_value=None,
        ):
            PlannerAgent().decompose("test goal", context={})
        
        # Verify ask_model was called with role="planning"
        called_roles = [kwargs.get("role") for _, kwargs in mock_ask_model.call_args_list]
        self.assertIn("planning", called_roles)

    @patch("backend.core.reflection_engine.ask_model")
    def test_reflection_routing(self, mock_ask_model):
        """Verifies reflection engine routes significance evaluation and lesson synthesis to reflection model."""
        mock_ask_model.return_value = '{"category": "PERFORMANCE", "problem": "test", "cause": "test", "improvement": "test", "confidence": 0.8}'
        
        # Trigger reflection evaluation with logs containing failures to make it actionable
        ReflectionEngine.analyze_and_propose("exit_code=1 exception failed error runtimeerror", source_window_days=1)
        
        # Verify ask_model called with role="reflection"
        called_roles = [kwargs.get("role") for _, kwargs in mock_ask_model.call_args_list]
        self.assertIn("reflection", called_roles)

    @patch("backend.core.model_router.ask_model")
    def test_failure_recovery_routing(self, mock_ask_model):
        """Verifies recovery engine queries the recovery model dynamically and falls back gracefully."""
        mock_ask_model.return_value = '{"rca": "Dynamic RCA", "recovery_path": "Dynamic Path"}'
        
        report = FailureRecoveryEngine.trigger_failure(
            mission_id="m_test_123",
            stage="TestStage",
            agent="TestAgent",
            reason="Port conflict during startup."
        )
        
        self.assertEqual(report["reason"], "Dynamic RCA")
        self.assertEqual(report["recovery_path"], "Dynamic Path")
        
        # Verify ask_model called with role="recovery"
        mock_ask_model.assert_called_with(unittest.mock.ANY, role="recovery")

    @patch("backend.core.model_router.ask_model")
    def test_context_compression_routing(self, mock_ask_model):
        """Verifies context compressor uses the compression model for dynamic text summarization."""
        mock_ask_model.return_value = "Concise context"
        
        # Item exceeding 15 words limit
        long_val = "This is a very long sequence of words designed to trigger the context compression engine threshold."
        item = ContextItem(item_id="id1", source=ContextSource.WORKING, value=long_val, priority=ContextPriority.OPTIONAL)
        
        compressed = ContextCompressionEngine.compress_item(item, max_words=10)
        self.assertEqual(compressed.value, "Concise context")
        
        # Verify ask_model called with role="compression"
        mock_ask_model.assert_called_with(unittest.mock.ANY, role="compression")

    @patch("backend.core.model_router.ask_model")
    def test_memory_summarization_routing(self, mock_ask_model):
        """Verifies memory consolidation synthesizes memories with compression model."""
        mock_ask_model.return_value = "Semantic synthesis of memories"
        
        summary = MemoryCompressionEngine.summarise(["memory one", "memory two"])
        self.assertEqual(summary, "Semantic synthesis of memories")
        
        # Verify ask_model called with role="compression"
        mock_ask_model.assert_called_with(unittest.mock.ANY, role="compression")

    @patch("backend.core.model_router.ask_model")
    def test_governance_safety_routing(self, mock_ask_model):
        """Verifies secondary safety reviewer queries the safety model for complex requests."""
        mock_ask_model.return_value = '{"risk": "blocked", "reason": "Adversarial command injection"}'
        
        decision = classify_risk("Complex request description")
        
        self.assertEqual(decision.level, "blocked")
        self.assertTrue(decision.blocked)
        self.assertIn("Adversarial command injection", decision.reason)
        
        # Verify ask_model called with role="safety"
        mock_ask_model.assert_called_with(unittest.mock.ANY, role="safety")
