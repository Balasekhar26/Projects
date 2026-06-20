from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.core.free_tool_catalog import developer_toolbox_audit


PROJECTS_ROOT = Path(__file__).resolve().parents[3]


def load_project_blueprints() -> list[dict[str, Any]]:
    blueprints = []
    if PROJECTS_ROOT.exists() and PROJECTS_ROOT.is_dir():
        for path in PROJECTS_ROOT.iterdir():
            if path.is_dir():
                metadata_file = path / "project_metadata.json"
                if metadata_file.exists():
                    try:
                        with metadata_file.open("r", encoding="utf-8") as f:
                            data = json.load(f)
                            data["path"] = str(path)
                            blueprints.append(data)
                    except Exception:
                        pass
    blueprints.sort(key=lambda x: x.get("rank", 99))
    return blueprints


PROJECT_BLUEPRINTS = load_project_blueprints()


def project_ecosystem() -> dict[str, Any]:
    projects = []
    toolbox_patch = developer_toolbox_audit().get("free_project_applications_patch", {})
    current_blueprints = load_project_blueprints()
    for item in current_blueprints:
        path = Path(item["path"])
        project_item = dict(item)
        project_item["free_tools"] = _merged_free_tools(
            item.get("free_tools", []),
            toolbox_patch.get(item["id"], []),
        )
        projects.append(
            {
                **project_item,
                "exists": path.exists(),
                "status": "present" if path.exists() else "missing",
            }
        )
    return {
        "strategy": "Build Kattappa AI OS first using the PDF ladder: LLM, RAG, agent, tool connections, approvals, automation, then use it as the central assistant for PCB Doctor, Cyber Shield, ULT, Musical Keyboard, safe DEWS, NeuroSeed, and the Spacetime & Matter Control Suite (Kairo, Prism, Tempo, Portal, Mira).",
        "build_first": "Kattappa AI OS v1: local-first chat, memory, Finance Brain, diagnostics, voice, wake-name commands, project-aware free-tool mapping, and cursor-guided desktop assistant.",
        "free_tool_rule": "Everything mapped into the seven projects must be fully free: free/open-source/local-first where practical, with no paid or freemium service dependency in the core project plan. If a named tool is paid, freemium, trial-limited, reward-based, closed, or privacy-risky, first search for a similar fully free replacement and add only the replacement when it improves a project.",
        "projects": projects,
    }


def _merged_free_tools(base: list[str], patch: list[str]) -> list[str]:
    merged = list(base)
    for tool in patch:
        if tool not in merged:
            merged.append(tool)
    return merged
