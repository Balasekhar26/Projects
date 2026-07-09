"""Unit tests for Program 38.0: Curated Tool Exploration and Registration.

Verifies plugin manifest queries, dependency safety, execution scanners,
trust evaluation, and dynamic CapabilityRegistry updates.
"""
from __future__ import annotations

import pytest

from backend.core.capability_registry import CapabilityRegistry
from backend.core.planning import (
    ToolRegistryExplorer,
    DependencyAnalyzer,
    SafetySandboxVerifier,
    PluginIsolationRuntime,
    TrustScoringEngine,
    CapabilityRegistryUpdater,
)


@pytest.fixture
def sample_manifests():
    return [
        {
            "name": "MathPlugin",
            "description": "Performs fast arithmetic calculations",
            "capabilities": ["CAP_MATH_ADD"],
            "dependencies": ["numpy>=1.20"],
        },
        {
            "name": "ShellTool",
            "description": "Executes shell commands in target folders",
            "capabilities": ["CAP_SHELL_EXEC"],
            "dependencies": ["subprocess", "requests"],
        },
    ]


# ── Tool Exploration & Registration Tests ─────────────────────────────────────

class TestToolAcquisition:
    def test_search_tool_registry(self, sample_manifests):
        # Search by capability name
        res = ToolRegistryExplorer.search_tool_registry(sample_manifests, "math")
        assert len(res) == 1
        assert res[0]["name"] == "MathPlugin"

    def test_dependency_analyzer_forbidden(self, sample_manifests):
        # MathPlugin should be clean
        ok, unsafe = DependencyAnalyzer.analyze_dependencies(sample_manifests[0])
        assert ok is True
        assert len(unsafe) == 0

        # ShellTool has forbidden dependency (subprocess)
        ok_b, unsafe_b = DependencyAnalyzer.analyze_dependencies(sample_manifests[1])
        assert ok_b is False
        assert "subprocess" in unsafe_b

    def test_safety_sandbox_verifier(self):
        safe_code = "def add(a, b):\n    return a + b"
        ok, msg = SafetySandboxVerifier.verify_source_code(safe_code)
        assert ok is True

        unsafe_code = "def run():\n    eval('import os; os.system(\"rm -rf /\")')"
        ok_b, msg_b = SafetySandboxVerifier.verify_source_code(unsafe_code)
        assert ok_b is False
        assert "eval" in msg_b

    def test_plugin_isolation_runtime(self):
        # Successful run
        res = PluginIsolationRuntime.simulate_plugin_run(lambda: 42)
        assert res["status"] == "success"
        assert res["result"] == 42

        # Crashing run
        res_fail = PluginIsolationRuntime.simulate_plugin_run(lambda: 1 / 0)
        assert res_fail["status"] == "failed"
        assert "division by zero" in res_fail["error"]

    def test_trust_scoring_engine(self):
        # High trust score: verified author, signed, 0 failures
        score1 = TrustScoringEngine.compute_trust_score(
            creator="KattappaTeam",
            past_failures=0,
            has_signature=True,
        )
        assert score1 == 1.0

        # Low trust score: anonymous author, unsigned, 2 failures
        score2 = TrustScoringEngine.compute_trust_score(
            creator="unknown",
            past_failures=2,
            has_signature=False,
        )
        # 1.0 - 0.2 (anonymous) - 0.2 (failures) - 0.3 (unsigned) = 0.3
        assert score2 == 0.3

    def test_verify_and_register_capability(self):
        agent_name = "test_custom_agent"
        target_cap = "CAP_DYNAMIC_API"

        # Check default state: denied
        assert CapabilityRegistry.is_capability_allowed(agent_name, target_cap) is False

        # Attempt to register with safe configuration
        ok = CapabilityRegistryUpdater.verify_and_register_tool(
            agent_name=agent_name,
            capability=target_cap,
            package_descriptor={"dependencies": ["numpy"]},
            source_code="def run(): return 'hello'",
            creator="VerifiedOrg",
            past_failures=0,
            has_signature=True,
        )

        assert ok is True
        # Verify it is now dynamically allowed in the CapabilityRegistry!
        assert CapabilityRegistry.is_capability_allowed(agent_name, target_cap) is True

        # Clean up / revoke
        CapabilityRegistry.revoke_agent_capability(agent_name, target_cap)
        assert CapabilityRegistry.is_capability_allowed(agent_name, target_cap) is False
