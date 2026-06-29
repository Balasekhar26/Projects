"""Unit and integration tests for Program 10: Inference Platform.
"""
from __future__ import annotations

import time
import pytest

from backend.core.inference.models import InferenceRequest, InferenceResponse
from backend.core.inference.provider import MockProvider
from backend.core.inference.capabilities import CapabilitiesRegistry
from backend.core.inference.routing import RoutingEngine
from backend.core.inference.validator import ResponseValidator
from backend.core.inference.fallback import FallbackEngine
from backend.core.inference.cost import CostManager
from backend.core.inference.response_cache import ResponseCache
from backend.core.inference.inference_engine import InferenceEngine


def test_capabilities_based_routing():
    """Verifies that RoutingEngine selects correct models based on capability constraints."""
    router = RoutingEngine()

    # Local model request
    req_local = InferenceRequest("Test", required_capabilities=["local"])
    assert router.route(req_local) == "ollama-llama-3"

    # High capability request (should select cheapest that meets criteria: sonnet)
    req_tools = InferenceRequest("Test", required_capabilities=["supports_tools", "supports_json"])
    assert router.route(req_tools) in {"claude-3-5-sonnet", "gpt-4o", "gemini-1.5-pro"}


def test_response_validator_conformity():
    """Verifies that ResponseValidator checks json structures and empty checks."""
    # JSON Schema
    valid_json = '{"status": "ok", "data": "value"}'
    invalid_json = '{"status": "ok"}'  # missing "data"
    schema = {"required": ["status", "data"]}

    assert ResponseValidator.validate_json(valid_json, schema) is True
    assert ResponseValidator.validate_json(invalid_json, schema) is False
    assert ResponseValidator.validate_json("not-json") is False

    # Non-empty
    assert ResponseValidator.validate_non_empty("   ") is False
    assert ResponseValidator.validate_non_empty("content") is True


def test_fallback_chain_failovers():
    """Verifies that FallbackEngine catches primary model errors and successfully recovers using backup models."""
    p_fail = MockProvider("gpt-fail")
    p_fail.throw_error = True
    p_ok = MockProvider("gpt-backup")

    providers = {"gpt-fail": p_fail, "gpt-backup": p_ok}
    fallback_mgr = FallbackEngine(providers)

    req = InferenceRequest("Translate hello")
    response = fallback_mgr.execute_with_fallback(req, ["gpt-fail", "gpt-backup"])

    assert response.model_used == "gpt-backup"
    assert "Translate hello" in response.text_content


def test_cost_manager_audits():
    """Checks that CostManager increments calls and accumulates token usages/cost in USD."""
    mgr = CostManager.get_instance()
    mgr.reset()

    mgr.record_usage(cost=0.005, input_tokens=100, output_tokens=200)
    mgr.record_usage(cost=0.010, input_tokens=200, output_tokens=300)

    summary = mgr.get_summary()
    assert summary["total_cost_usd"] == 0.015
    assert summary["total_input_tokens"] == 300
    assert summary["total_output_tokens"] == 500
    assert summary["total_calls"] == 2


def test_response_cache_expiration():
    """Verifies response caching matches inputs and expires on TTL timings."""
    cache = ResponseCache(ttl_seconds=0.1)
    response = InferenceResponse("cached text", "gpt-4o")

    cache.put("Hello", "SystemPrompt", response)
    assert cache.get("Hello", "SystemPrompt") == response

    # Sleep past TTL
    time.sleep(0.15)
    assert cache.get("Hello", "SystemPrompt") is None


def test_e2e_inference_engine_pipeline():
    """Integration test: runs complete inference flow and records outputs."""
    engine = InferenceEngine.get_instance()
    req = InferenceRequest("Run test pipeline", required_capabilities=["local"])

    response = engine.execute_inference(req, bypass_cache=True)
    assert response.model_used == "ollama-llama-3"
    assert "Run test pipeline" in response.text_content
