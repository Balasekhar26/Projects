from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from backend.core.config import load_config


@lru_cache(maxsize=1)
def free_tool_catalog() -> dict[str, Any]:
    path = load_config().root / "config" / "free_tools.json"
    if not path.exists():
        return {
            "allowed_core_tools": {},
            "optional_labs": {},
            "blocked_paid_or_restricted": [],
        }
    return json.loads(path.read_text(encoding="utf-8"))


def free_tool_decision_report() -> dict[str, Any]:
    catalog = free_tool_catalog()
    core_tools = catalog.get("allowed_core_tools", {})
    optional_labs = catalog.get("optional_labs", {})
    learning_sources = catalog.get("learning_sources", {})
    architecture_patterns = catalog.get("architecture_patterns_from_pdf", {})
    hardware_topics = catalog.get("hardware_topics", {})
    project_applications = catalog.get("free_project_applications", {})
    replacement_policy = catalog.get("paid_tool_replacement_policy", {})
    allowed_now = [
        key
        for key, value in core_tools.items()
        if isinstance(value, dict) and value.get("status") == "add_now"
    ]
    adapter_candidates = [
        key
        for key, value in core_tools.items()
        if isinstance(value, dict) and value.get("status") in {"adapter_candidate", "optional_adapter"}
    ]
    optional_free_labs = [
        key
        for key, value in optional_labs.items()
        if isinstance(value, dict)
        and value.get("status")
        in {
            "optional_personal_use",
            "optional_research_adapter",
            "optional_workflow_adapter",
            "optional_model_adapter",
            "optional_cluster_adapter",
        }
    ]
    project_unique_tools = sorted(
        {
            tool
            for tools in project_applications.values()
            if isinstance(tools, list)
            for tool in tools
        }
    )
    return {
        "mode": "fully_free_local_first",
        "allowed_now": sorted(allowed_now),
        "adapter_candidates": sorted(adapter_candidates),
        "optional_labs": sorted(optional_labs.keys()),
        "optional_free_labs": sorted(optional_free_labs),
        "blocked": catalog.get("blocked_paid_or_restricted", []),
        "paid_tool_replacement_policy": replacement_policy,
        "rule": "Core tools must be free, open-source, locally usable, and replaceable adapters.",
        "counts": {
            "core_add_now": len(allowed_now),
            "free_adapter_candidates": len(adapter_candidates),
            "optional_free_labs": len(optional_free_labs),
            "learning_sources": len(learning_sources),
            "architecture_patterns": len(architecture_patterns),
            "hardware_topics": len(hardware_topics),
            "project_unique_tools": len(project_unique_tools),
            "project_count": len(project_applications),
        },
        "project_applications": project_applications,
        "project_unique_tools": project_unique_tools,
        "catalog": catalog,
    }
