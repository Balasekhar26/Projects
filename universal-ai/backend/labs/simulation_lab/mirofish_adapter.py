from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.core.config import load_config
from backend.labs.simulation_lab.scenario_builder import build_scenario


def simulation_status() -> dict[str, Any]:
    root = _mirofish_root()
    return {
        "tool": "mirofish",
        "installed": root.exists(),
        "path": str(root),
        "license": "AGPL-3.0",
        "status": "optional_personal_use" if root.exists() else "optional_missing",
        "boundary": "Keep as an optional external lab; do not copy AGPL code into closed-source core.",
    }


def run_simulation(seed: str, horizon: str = "short") -> dict[str, Any]:
    scenario = build_scenario(seed, horizon)
    installed = simulation_status()["installed"]
    return {
        "engine": "mirofish-adapter" if installed else "sekhar-local-simulation-fallback",
        "scenario": scenario,
        "predictions": [
            {
                "outcome": "Best case",
                "signal": "Plan is clear, tools stay local, and user approval catches risky steps.",
                "confidence": "low-medium",
            },
            {
                "outcome": "Likely case",
                "signal": "Progress depends on small verified integrations and avoiding paid service drift.",
                "confidence": "low",
            },
            {
                "outcome": "Risk case",
                "signal": "Licensing, model size, or hardware constraints slow the integration.",
                "confidence": "low",
            },
        ],
        "warning": "Simulation output is a planning aid, not a factual forecast.",
    }


def _mirofish_root() -> Path:
    projects_root = load_config().root.parent
    return projects_root / "external-projects" / "MiroFish"
