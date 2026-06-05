from __future__ import annotations

from typing import Any

from backend.ai_engine.providers.deepseek_profile import deepseek_profile
from backend.ai_engine.providers.gemma_profile import gemma_profile
from backend.ai_engine.providers.qwen_profile import qwen_profile
from backend.core.model_router import available_models
from backend.labs.airllm_lab.adapter import airllm_status


def local_model_profiles() -> dict[str, Any]:
    installed = available_models()
    profiles = [gemma_profile(installed), qwen_profile(installed), deepseek_profile(installed)]
    return {
        "runtime": "ollama_or_local_runtime",
        "local_only": True,
        "profiles": profiles,
        "optional_labs": {
            "airllm": airllm_status(),
        },
        "routing_hint": {
            "simple": "gemma",
            "coding": "qwen_or_deepseek",
            "reasoning": "gemma_or_deepseek",
            "writing": "harper_plus_gemma",
            "web_extraction": "scrapegraphai_plus_gemma_or_qwen",
            "huge_model_low_vram": "airllm_optional_lab_only",
        },
    }
