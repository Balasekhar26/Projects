"""Curated Tool Exploration and Registration (Program 38.0).

Dynamically searches manifests, checks library dependencies, verifies source code safety,
scores developer trust indices, and updates the CapabilityRegistry on verified tools.
"""
from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Tuple

from backend.core.capability_registry import CapabilityRegistry


class ToolRegistryExplorer:
    """Explores manifests of third-party plugins and APIs."""

    @classmethod
    def search_tool_registry(
        cls,
        manifests: List[Dict[str, Any]],
        query: str,
    ) -> List[Dict[str, Any]]:
        """Filter manifests matching query text."""
        q = query.lower()
        results = []
        for m in manifests:
            name = m.get("name", "").lower()
            desc = m.get("description", "").lower()
            caps = [c.lower() for c in m.get("capabilities", [])]
            if q in name or q in desc or any(q in cap for cap in caps):
                results.append(m)
        return results


class DependencyAnalyzer:
    """Analyzes packaging manifests for unsafe package dependencies."""

    FORBIDDEN_DEPENDENCIES = {"subprocess", "sh", "os", "sys", "pexpect"}

    @classmethod
    def analyze_dependencies(cls, package_descriptor: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Checks dependencies list for unauthorized system packages."""
        deps = package_descriptor.get("dependencies", [])
        unsafe = []
        for dep in deps:
            dep_clean = dep.split("==")[0].strip().lower()
            if dep_clean in cls.FORBIDDEN_DEPENDENCIES:
                unsafe.append(dep)
        
        is_safe = len(unsafe) == 0
        return is_safe, unsafe


class SafetySandboxVerifier:
    """Analyzes plugin python source code for forbidden execution statements."""

    # Search for builtins that bypass import blocks or execute code strings
    FORBIDDEN_PATTERNS = [
        r"\beval\s*\(",
        r"\bexec\s*\(",
        r"\b__import__\s*\(",
        r"\bcompile\s*\(",
        r"\bos\s*\.\s*system\s*\(",
        r"\bsubprocess\s*\.\s*Popen\s*\(",
    ]

    @classmethod
    def verify_source_code(cls, source_code: str) -> Tuple[bool, str]:
        """Scans plugin code for forbidden execution calls."""
        for pattern in cls.FORBIDDEN_PATTERNS:
            if re.search(pattern, source_code):
                return False, f"Forbidden pattern match: {pattern}"
        return True, "Code passed safety scanning."


class PluginIsolationRuntime:
    """Executes plugin tasks inside a sandbox recovery container wrapper."""

    @classmethod
    def simulate_plugin_run(cls, plugin_fn: Callable[[], Any]) -> Dict[str, Any]:
        """Runs the plugin action inside isolated try/catch boundaries."""
        try:
            res = plugin_fn()
            return {"status": "success", "result": res}
        except Exception as e:
            return {"status": "failed", "error": str(e)}


class TrustScoringEngine:
    """Computes trust metrics for developers and execution profiles."""

    @classmethod
    def compute_trust_score(
        cls,
        creator: str,
        past_failures: int,
        has_signature: bool,
    ) -> float:
        """Derives a trust rating between 0.0 and 1.0."""
        score = 1.0
        
        # Deduct for past failures
        score -= 0.1 * past_failures
        
        # Deduct heavily for unsigned plugins
        if not has_signature:
            score -= 0.3
            
        # Deduct for untrusted creators
        if creator.lower().strip() in ("unverified", "anonymous", "unknown"):
            score -= 0.2

        return max(0.0, min(1.0, round(score, 2)))


class CapabilityRegistryUpdater:
    """Orchestrates validation pipelines and updates the active CapabilityRegistry."""

    @classmethod
    def verify_and_register_tool(
        cls,
        agent_name: str,
        capability: str,
        package_descriptor: Dict[str, Any],
        source_code: str,
        creator: str,
        past_failures: int,
        has_signature: bool,
    ) -> bool:
        """Verifies tool dependency, safety code, and trust scoring. Registers on success."""
        # 1. Check dependencies
        dep_safe, unsafe_deps = DependencyAnalyzer.analyze_dependencies(package_descriptor)
        if not dep_safe:
            return False

        # 2. Verify source code safety
        code_safe, _ = SafetySandboxVerifier.verify_source_code(source_code)
        if not code_safe:
            return False

        # 3. Score trust
        trust = TrustScoringEngine.compute_trust_score(creator, past_failures, has_signature)
        if trust < 0.70:
            return False

        # 4. Success -> Register capability
        CapabilityRegistry.register_agent_capability(agent_name, capability)
        return True
