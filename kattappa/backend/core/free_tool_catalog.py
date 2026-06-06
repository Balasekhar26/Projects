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


@lru_cache(maxsize=1)
def ai_ecosystem_topic_audit() -> dict[str, Any]:
    path = load_config().root / "config" / "ai_ecosystem_topic_audit.json"
    if not path.exists():
        return {"topics": [], "source_evidence": {}}
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def developer_toolbox_audit() -> dict[str, Any]:
    path = load_config().root / "config" / "developer_toolbox_audit.json"
    if not path.exists():
        return {"topics": [], "source_evidence": {}, "free_capabilities": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def free_tool_decision_report() -> dict[str, Any]:
    catalog = free_tool_catalog()
    topic_audit = ai_ecosystem_topic_audit()
    toolbox_audit = developer_toolbox_audit()
    core_tools = {
        **catalog.get("allowed_core_tools", {}),
        **toolbox_audit.get("free_capabilities", {}),
    }
    optional_labs = catalog.get("optional_labs", {})
    learning_sources = catalog.get("learning_sources", {})
    architecture_patterns = catalog.get("architecture_patterns_from_pdf", {})
    hardware_topics = catalog.get("hardware_topics", {})
    project_applications = _merged_project_applications(
        catalog.get("free_project_applications", {}),
        toolbox_audit.get("free_project_applications_patch", {}),
    )
    replacement_policy = catalog.get("paid_tool_replacement_policy", {})
    blocked = sorted(
        {
            *catalog.get("blocked_paid_or_restricted", []),
            *toolbox_audit.get("blocked_or_restricted", []),
        }
    )
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
        "blocked": blocked,
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
            "ecosystem_topics": len(topic_audit.get("topics", [])),
            "developer_toolbox_topics": len(toolbox_audit.get("topics", [])),
        },
        "project_applications": project_applications,
        "project_unique_tools": project_unique_tools,
        "ai_ecosystem_topic_audit": topic_audit,
        "developer_toolbox_audit": toolbox_audit,
        "catalog": catalog,
    }


def _merged_project_applications(
    base: dict[str, Any],
    patch: dict[str, Any],
) -> dict[str, list[str]]:
    merged: dict[str, list[str]] = {
        project: [str(tool) for tool in tools]
        for project, tools in base.items()
        if isinstance(tools, list)
    }
    for project, tools in patch.items():
        if not isinstance(tools, list):
            continue
        existing = merged.setdefault(project, [])
        for tool in tools:
            tool_name = str(tool)
            if tool_name not in existing:
                existing.append(tool_name)
    return merged
