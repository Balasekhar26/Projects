from __future__ import annotations

import platform
from typing import Any

from backend.core.config import load_config

HARDWARE_TIERS: list[dict[str, Any]] = [
    {
        "tier": "minimum",
        "name": "Run the desktop app and basic local chat",
        "cpu": "4-core x64 CPU",
        "ram": "8 GB RAM",
        "gpu": "Integrated GPU is okay",
        "vram": "0 GB dedicated VRAM",
        "storage": "25 GB free SSD space",
        "models": ["phi3:latest or qwen2.5:0.5b"],
        "good_for": [
            "FastAPI backend",
            "Tauri/React desktop shell",
            "small Ollama text chat",
            "SQLite/Chroma memory at small scale",
            "Finance Brain fallback forecaster",
        ],
        "limits": [
            "Large models will be slow or may fail to load.",
            "Vision, voice, OCR, and Kronos should be used one at a time.",
            "Expect CPU-only latency.",
        ],
    },
    {
        "tier": "recommended",
        "name": "Comfortable daily Universal AI use",
        "cpu": "8-core modern x64 CPU",
        "ram": "32 GB RAM",
        "gpu": "NVIDIA RTX-class GPU preferred, or strong CPU-only fallback",
        "vram": "8-12 GB VRAM",
        "storage": "100 GB free NVMe SSD space",
        "models": ["qwen3:4b", "qwen2.5-coder:3b", "mistral:latest", "small Whisper"],
        "good_for": [
            "Reliable local chat",
            "coding assistant routes",
            "browser/screen/OCR workflows",
            "voice transcription with small models",
            "Kronos small experiments",
        ],
        "limits": [
            "30B-class models need quantization and patience.",
            "Full autonomous multi-tool workflows should still be approval-gated.",
        ],
    },
    {
        "tier": "full_potential",
        "name": "Use every configured module strongly",
        "cpu": "12-16 core high-performance CPU",
        "ram": "64 GB RAM",
        "gpu": "NVIDIA RTX 4070 Ti Super / 4080 / 4090 or workstation equivalent",
        "vram": "16-24 GB VRAM",
        "storage": "250 GB free NVMe SSD space",
        "models": [
            "qwen3:30b quantized",
            "gpt-oss:20b quantized",
            "qwen3-vl:8b",
            "Kronos-small",
            "medium Whisper",
        ],
        "good_for": [
            "larger local reasoning models",
            "coder model plus memory plus browser",
            "vision model experiments",
            "voice pipeline",
            "Kronos real model inference",
            "desktop app and backend running together all day",
        ],
        "limits": [
            "Running multiple large models simultaneously still competes for VRAM/RAM.",
            "Training a Kronos-class financial foundation model is not realistic on this tier.",
        ],
    },
    {
        "tier": "maximum",
        "name": "Local lab / workstation ceiling",
        "cpu": "24-32 core workstation CPU",
        "ram": "128-256 GB RAM",
        "gpu": "One or two NVIDIA RTX 4090 / RTX 6000 Ada / pro GPUs",
        "vram": "48 GB+ total VRAM",
        "storage": "1-2 TB NVMe SSD free for models, datasets, logs, and checkpoints",
        "models": [
            "multiple 20B-70B quantized models",
            "larger Whisper",
            "vision models",
            "Kronos fine-tuning experiments",
        ],
        "good_for": [
            "parallel local model serving",
            "large codebase indexing",
            "bigger memory stores",
            "heavier vision/audio workloads",
            "financial model fine-tuning or backtesting experiments",
        ],
        "limits": [
            "Still not enough to train a Kronos-scale foundation model from scratch.",
            "Real trading automation needs separate broker/exchange safety, audit, and legal controls.",
        ],
    },
]

BUYING_GUIDE: list[dict[str, Any]] = [
    {
        "tier": "minimum",
        "laptop": "Used business laptop such as ThinkPad T / Latitude / EliteBook with 16 GB RAM.",
        "desktop": "Used business desktop such as OptiPlex / ThinkCentre with 16-32 GB RAM.",
        "best_for": "Coding, UI work, backend tests, small local models, and basic Universal AI setup.",
        "avoid": "Do not buy this tier expecting fast vision, voice, 30B models, or heavy local AI.",
    },
    {
        "tier": "recommended",
        "laptop": "RTX 5070 Ti / RTX 5080 class laptop with 32 GB RAM.",
        "desktop": "RTX 5070 Ti / RTX 5080 desktop with 64 GB RAM and 2 TB NVMe.",
        "best_for": "Daily Universal AI use, coding agents, OCR/browser workflows, and small-to-medium local models.",
        "avoid": "Avoid thin laptops with weak cooling if local AI is the main workload.",
    },
    {
        "tier": "full_potential",
        "laptop": "RTX 5090 class laptop with 64 GB RAM if portability matters.",
        "desktop": "Custom RTX 5090 desktop with 128 GB RAM, 2-4 TB NVMe, and strong cooling.",
        "best_for": "Universal AI, PCB Doctor, Cyber Shield, Translator experiments, Finance Brain, voice, and vision together.",
        "avoid": "Do not choose laptop-first if maximum sustained AI performance matters more than portability.",
    },
    {
        "tier": "maximum_lab",
        "laptop": "Desktop-replacement workstation laptop only if travel is unavoidable.",
        "desktop": "RTX PRO 6000 Blackwell / RTX 6000 Ada / dual high-end NVIDIA workstation with 128-256 GB RAM.",
        "best_for": "Huge local models, large codebase indexing, heavy multimodal experiments, and lab-style research.",
        "avoid": "This is a research/workstation tier, not the best practical first buy for most builders.",
    },
]


def hardware_requirements() -> dict[str, Any]:
    config = load_config()
    return {
        "system": _current_system_snapshot(),
        "configured_models": config.model_map,
        "tiers": HARDWARE_TIERS,
        "buying_guide": BUYING_GUIDE,
        "recommendation": (
            "For this Universal AI build, the practical sweet spot is a desktop-first setup: "
            "64-128 GB RAM, an NVIDIA GPU with at least 12-24 GB VRAM, and fast NVMe storage. "
            "A high-end laptop is useful for portability, but a desktop/workstation is better for sustained local AI."
        ),
        "notes": [
            "SSD space matters because Ollama models, Whisper models, Chroma memory, screenshots, logs, and Kronos weights accumulate.",
            "CPU-only mode works, but local LLM response time is the first thing that suffers.",
            "More VRAM improves model size and speed; more RAM improves multitasking and larger context workflows.",
            "AirLLM can help fit bigger models on weak VRAM, but it usually trades speed for memory reach.",
        ],
    }


def _current_system_snapshot() -> dict[str, Any]:
    snapshot: dict[str, Any] = {
        "platform": platform.platform(),
        "processor": platform.processor() or "unknown",
        "cpu_count_logical": None,
        "ram_total_gb": None,
    }
    try:
        import psutil

        snapshot["cpu_count_logical"] = psutil.cpu_count(logical=True)
        snapshot["cpu_count_physical"] = psutil.cpu_count(logical=False)
        snapshot["ram_total_gb"] = round(psutil.virtual_memory().total / (1024**3), 1)
    except Exception as exc:
        snapshot["inspection_error"] = str(exc)
    return snapshot
