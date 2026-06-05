from __future__ import annotations

from typing import Any

import httpx

from backend.tools.web_research.scrapegraph_runner import (
    run_scrapegraph_extract,
    scrapegraph_status,
)
from backend.tools.web_research.structured_data_extractor import extract_structured_data


def extract_website(
    url: str,
    goal: str = "Extract the main useful facts as structured data.",
    *,
    use_scrapegraph: bool = False,
    local_model: str = "gemma",
) -> dict[str, Any]:
    if not url.startswith(("http://", "https://")):
        raise ValueError("Only http:// and https:// URLs are supported.")

    status = scrapegraph_status()
    if use_scrapegraph and status["installed"]:
        result = run_scrapegraph_extract(url, goal, local_model)
        if result is not None:
            return result

    response = httpx.get(url, follow_redirects=True, timeout=12)
    response.raise_for_status()
    structured = extract_structured_data(response.text, str(response.url))
    structured.update(
        {
            "engine": "sekhar-local-html-extractor",
            "goal": goal,
            "scrapegraph_status": status,
            "llm_policy": "local_models_only",
        }
    )
    return structured
