from __future__ import annotations

from typing import Any


SOURCE_FIRST_RULES = [
    "The manager worker may search the internet for better fully free/open-source/local-first tools when a user task needs a new capability.",
    "The tool scout must prefer tools that can run locally, have inspectable source, and do not require paid accounts or cloud quotas.",
    "External tools may be local-run or cloud-run only if they are fully free for the intended use, optional, transparent about data flow, and wrapped as replaceable adapters.",
    "Prefer Kattappa AI OS built-in code for agents, routing, memory, approvals, desktop modes, and task handling.",
    "Before installing a free/open-source tool, show what it is, why it is needed, where the source/project lives, and what command will run.",
    "Treat external packages as replaceable adapters, not as the core brain of the system.",
    "Do not add paid APIs, cloud-only services, telemetry-first services, or closed black-box agents as required dependencies.",
    "When a package is small enough to replace safely, prefer implementing the needed feature locally instead of adding another dependency.",
    "When a package/model is too large to rebuild, keep it behind a local adapter so it can be swapped or removed later.",
    "After meaningful tasks, run a background free-tool scout that looks for better free/local tools and converts useful ideas into approval-gated build-own proposals.",
    "Never copy code from a project unless its license is inspected and compatible; prefer rebuilding the behavior in Kattappa AI OS style.",
]


REBUILD_BOUNDARIES = [
    {
        "kind": "Agents and workflows",
        "decision": "Build in Kattappa AI OS code.",
        "reason": "Planner, memory, safety, approval, self-improvement, task ledger, and routing are core identity.",
    },
    {
        "kind": "APIs",
        "decision": "Use local FastAPI endpoints owned by this project.",
        "reason": "The app should work without paid cloud APIs or hidden remote services.",
    },
    {
        "kind": "Small utilities",
        "decision": "Rebuild locally when the feature is simple and stable.",
        "reason": "Small code is easier to audit and customize than another dependency.",
    },
    {
        "kind": "Large open-source libraries",
        "decision": "Inspect, pin, approval-gate, and wrap as adapters.",
        "reason": "Rebuilding frameworks like Playwright, ChromaDB, or LangGraph from scratch would slow the project without improving the user motive.",
    },
    {
        "kind": "AI model weights",
        "decision": "Use free/local model files through Ollama or local runtimes.",
        "reason": "A model is not normal source code; recreating weights requires massive training data, GPUs, and time. Keep them local and swappable.",
    },
]


INSPECTION_FIELDS = {
    "python_package": "Inspect package metadata, license, installed files, and import surface after approval/install.",
    "ollama_model": "Record model name, local-only use, size/source information when available, and keep a removable model profile.",
    "manual_tool": "Show official source/download instructions and require Bala to install manually.",
}


def source_first_policy() -> dict[str, Any]:
    return {
        "mode": "source_first_free_local",
        "summary": (
            "Kattappa AI OS should build its own core agents and APIs. It may search the internet for better "
            "fully free/open-source/local-first tools, including external tools that run locally or in the cloud, "
            "but they are allowed only as inspected, approval-gated, replaceable adapters."
        ),
        "rules": SOURCE_FIRST_RULES,
        "rebuild_boundaries": REBUILD_BOUNDARIES,
        "inspection_fields": INSPECTION_FIELDS,
        "hard_no": [
            "No paid API dependency.",
            "No closed black-box agent as the main brain.",
            "No required cloud-run dependency for core assistant behavior.",
            "No silent installs.",
            "No automatic permanent self-modification without Bala approval.",
            "No license-blind copying from the internet.",
        ],
    }
