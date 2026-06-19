from __future__ import annotations

import sys
from unittest.mock import MagicMock
sys.modules["optimum.bettertransformer"] = MagicMock()

import importlib.util
from dataclasses import dataclass
from typing import Any

from backend.core.config import load_config


DEFAULT_MAX_NEW_TOKENS = 80
DEFAULT_MODEL_ID = "garage-bAInd/Platypus2-70B-instruct"


@dataclass(frozen=True)
class AirLLMRequest:
    prompt: str
    model_id: str = DEFAULT_MODEL_ID
    max_new_tokens: int = DEFAULT_MAX_NEW_TOKENS
    compression: str | None = "4bit"


def airllm_status() -> dict[str, Any]:
    config = load_config()
    installed = _module_available("airllm")
    torch_available = _module_available("torch")
    bitsandbytes_available = _module_available("bitsandbytes")
    cuda_available = _cuda_available() if torch_available else False
    return {
        "key": "airllm",
        "name": "AirLLM Huge Model Lab",
        "installed": installed,
        "ready": installed and torch_available,
        "runtime": "optional_experimental",
        "default_model": DEFAULT_MODEL_ID,
        "configured_power_model": config.model_map.get("power", ""),
        "imports": {
            "airllm": installed,
            "torch": torch_available,
            "bitsandbytes": bitsandbytes_available,
            "cuda": cuda_available,
        },
        "speed_note": (
            "AirLLM is for fitting huge models on limited VRAM. It usually improves "
            "memory reach, not chat speed, because model layers are streamed through "
            "disk/RAM/GPU. Keep Ollama or smaller quantized models as the default."
        ),
        "setup_hint": "Optional only: pip install airllm torch bitsandbytes, then use /ai-engine/airllm/generate explicitly.",
        "safety_note": "First run can download and split very large Hugging Face models; confirm disk space and model license first.",
    }


def generate_with_airllm(request: AirLLMRequest) -> dict[str, Any]:
    if not request.prompt.strip():
        raise ValueError("prompt is required.")
    if request.max_new_tokens < 1 or request.max_new_tokens > 512:
        raise ValueError("max_new_tokens must be between 1 and 512.")
    if request.compression not in {None, "4bit", "8bit"}:
        raise ValueError("compression must be null, 4bit, or 8bit.")
    if not _module_available("airllm"):
        raise RuntimeError("AirLLM is not installed. Install it only if you want huge-model lab mode.")
    if not _module_available("torch"):
        raise RuntimeError("PyTorch is required for AirLLM generation.")

    from airllm import AutoModel
    import torch

    model_kwargs: dict[str, Any] = {}
    if request.compression:
        model_kwargs["compression"] = request.compression

    model = AutoModel.from_pretrained(request.model_id, **model_kwargs)
    input_tokens = model.tokenizer(
        [request.prompt],
        return_tensors="pt",
        return_attention_mask=False,
        truncation=True,
        max_length=512,
        padding=False,
    )
    input_ids = input_tokens["input_ids"]
    if torch.cuda.is_available():
        input_ids = input_ids.cuda()
    output = model.generate(
        input_ids,
        max_new_tokens=request.max_new_tokens,
        use_cache=True,
        return_dict_in_generate=True,
    )
    text = model.tokenizer.decode(output.sequences[0])
    return {
        "engine": "airllm",
        "model": request.model_id,
        "compression": request.compression,
        "response": text,
        "speed_note": airllm_status()["speed_note"],
    }


def _module_available(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def _cuda_available() -> bool:
    try:
        import torch

        return bool(torch.cuda.is_available())
    except Exception:
        return False

