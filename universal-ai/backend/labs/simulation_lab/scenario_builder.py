from __future__ import annotations

from typing import Any


def build_scenario(seed: str, horizon: str = "short") -> dict[str, Any]:
    assumptions = [
        "Use only user-provided seed information.",
        "Treat output as planning support, not prophecy.",
        "Mark unknowns instead of inventing facts.",
    ]
    return {
        "seed": seed.strip(),
        "horizon": horizon,
        "assumptions": assumptions,
        "actors": _actors_from_seed(seed),
        "unknowns": ["External events", "Resource limits", "Human decisions"],
    }


def _actors_from_seed(seed: str) -> list[str]:
    words = [word.strip(".,:;!?()[]{}") for word in seed.split()]
    candidates = [word for word in words if word[:1].isupper() and len(word) > 2]
    return candidates[:8] or ["user", "project", "local AI system"]
