"""Inference Request and Response Schemas (Program 10).

Standardizes provider-agnostic input and output interfaces.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class InferenceRequest:
    """Canonical model for LLM query executions."""
    prompt: str
    required_capabilities: List[str] = field(default_factory=list)
    max_cost: float = 0.5  # Max cost in USD
    max_latency: float = 30.0  # Max latency in seconds
    system_instruction: str = ""
    temperature: float = 0.7
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class InferenceResponse:
    """Canonical provider-agnostic response payload."""
    text_content: str
    model_used: str
    cost: float = 0.0
    latency: float = 0.0
    token_usage: Dict[str, int] = field(default_factory=dict)  # "input", "output"
    metadata: Dict[str, Any] = field(default_factory=dict)
