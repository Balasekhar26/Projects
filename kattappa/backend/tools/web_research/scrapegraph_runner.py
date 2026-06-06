from __future__ import annotations

import importlib.util
from typing import Any


def scrapegraph_status() -> dict[str, Any]:
    installed = importlib.util.find_spec("scrapegraphai") is not None
    return {
        "engine": "scrapegraphai",
        "installed": installed,
        "license": "MIT",
        "network_required_for_websites": True,
        "llm_policy": "local_models_only",
        "install_hint": "pip install scrapegraphai, then configure it to use Ollama/local models only.",
    }


def run_scrapegraph_extract(url: str, prompt: str, local_model: str = "gemma") -> dict[str, Any] | None:
    if importlib.util.find_spec("scrapegraphai") is None:
        return None
    try:
        from scrapegraphai.graphs import SmartScraperGraph

        graph = SmartScraperGraph(
            prompt=prompt,
            source=url,
            config={
                "llm": {
                    "model": f"ollama/{local_model}",
                    "temperature": 0,
                    "format": "json",
                },
                "embeddings": {"model": "ollama/nomic-embed-text"},
                "verbose": False,
            },
        )
        return {
            "engine": "scrapegraphai",
            "url": url,
            "data": graph.run(),
            "llm_policy": "local_models_only",
        }
    except Exception as exc:
        return {
            "engine": "scrapegraphai-error",
            "url": url,
            "error": str(exc),
            "llm_policy": "local_models_only",
        }
