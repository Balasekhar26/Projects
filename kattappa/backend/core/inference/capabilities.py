"""Model Capabilities Registry (Program 10).

Stores metadata detailing model parameters, costs, limits, and capabilities.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class ModelCapabilities:
    model_name: str
    supports_tools: bool = True
    supports_json: bool = True
    context_window: int = 128000
    cost_per_1k_input: float = 0.005  # USD
    cost_per_1k_output: float = 0.015  # USD
    speed_rank: int = 2  # 1 to 5
    accuracy_rank: int = 2  # 1 to 5
    additional_flags: List[str] = field(default_factory=list)


class CapabilitiesRegistry:
    """Central store matching model identifiers to capability metadata metrics."""

    _instance: Optional[CapabilitiesRegistry] = None

    def __init__(self) -> None:
        self._models: Dict[str, ModelCapabilities] = {
            "gpt-4o": ModelCapabilities(
                model_name="gpt-4o",
                supports_tools=True,
                supports_json=True,
                context_window=128000,
                cost_per_1k_input=0.005,
                cost_per_1k_output=0.015,
                speed_rank=1,
                accuracy_rank=1,
            ),
            "claude-3-5-sonnet": ModelCapabilities(
                model_name="claude-3-5-sonnet",
                supports_tools=True,
                supports_json=True,
                context_window=200000,
                cost_per_1k_input=0.003,
                cost_per_1k_output=0.015,
                speed_rank=2,
                accuracy_rank=1,
            ),
            "gemini-1.5-pro": ModelCapabilities(
                model_name="gemini-1.5-pro",
                supports_tools=True,
                supports_json=True,
                context_window=1000000,
                cost_per_1k_input=0.00125,
                cost_per_1k_output=0.005,
                speed_rank=3,
                accuracy_rank=2,
            ),
            "ollama-llama-3": ModelCapabilities(
                model_name="ollama-llama-3",
                supports_tools=False,
                supports_json=False,
                context_window=8000,
                cost_per_1k_input=0.0,
                cost_per_1k_output=0.0,
                speed_rank=1,
                accuracy_rank=4,
                additional_flags=["local"],
            ),
        }

    @classmethod
    def get_instance(cls) -> CapabilitiesRegistry:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def get_capabilities(self, model_name: str) -> Optional[ModelCapabilities]:
        return self._models.get(model_name)

    def list_models(self) -> List[str]:
        return list(self._models.keys())
