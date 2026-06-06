from __future__ import annotations

from datetime import datetime
from typing import Any

from backend.core.memory import build_memory_context, memory
from backend.core.project_indexer import search_project_index


def resume_long_task(task_id: str) -> dict[str, Any] | None:
    task = memory.get_long_task(task_id)
    if task is None:
        return None
    query = f"{task['title']} {task['goal']} {task['next_step']}"
    project_hits = search_project_index(query, limit=8)["items"]
    memory_context = build_memory_context(query)
    next_steps = _next_steps_for(task, project_hits)
    now = datetime.now().isoformat(timespec="seconds")
    progress = task["progress"].strip()
    resume_note = f"Resumed at {now}; prepared {len(next_steps)} local next steps."
    if resume_note not in progress:
        progress = f"{progress}\n{resume_note}".strip()
    updated = memory.update_long_task(
        task_id,
        status="active",
        progress=progress,
        next_step=next_steps[0] if next_steps else "Ask Bala what approved step to do next.",
    )
    return {
        "task": updated,
        "next_steps": next_steps,
        "project_hits": project_hits,
        "memory_context": memory_context,
        "resume_prompt": _resume_prompt(updated or task, next_steps),
    }


def _next_steps_for(task: dict[str, str], project_hits: list[dict[str, Any]]) -> list[str]:
    goal = f"{task['title']} {task['goal']} {task['next_step']}".lower()
    steps: list[str] = []
    if "test" in goal or "bug" in goal or "fix" in goal:
        steps.extend(
            [
                "Run the focused backend tests and desktop build to find the current failure.",
                "Inspect only the files connected to the failing test/build output.",
                "Patch the smallest local change, then rerun the same verification.",
            ]
        )
    elif "memory" in goal or "chat" in goal or "task" in goal:
        steps.extend(
            [
                "Verify chat history and long-task context are included in /memory/context.",
                "Open the desktop Tasks tab and continue the saved task into Chat.",
                "Run backend tests plus desktop build after any change.",
            ]
        )
    elif "installer" in goal or "msi" in goal or "build" in goal:
        steps.extend(
            [
                "Run the packaging command and capture the exact failing tool output.",
                "Fix the packaging script or config without reusing stale artifacts.",
                "Confirm the generated installer exists and has a fresh timestamp.",
            ]
        )
    else:
        steps.extend(
            [
                "Read the relevant local project files from the project index.",
                "Make a short plan with approval checkpoints for risky actions.",
                "Execute one focused step, verify it, then update this long task.",
            ]
        )
    if project_hits:
        steps.append("Relevant files: " + ", ".join(item["path"] for item in project_hits[:4]))
    return steps


def _resume_prompt(task: dict[str, str], next_steps: list[str]) -> str:
    return (
        f"Continue long task: {task['title']}\n"
        f"Goal: {task['goal']}\n"
        f"Current progress: {task['progress'] or 'not recorded yet'}\n"
        f"Next step: {task['next_step'] or (next_steps[0] if next_steps else 'decide the next safe step')}\n"
        "Use local/free tools only, keep approval gates for risky actions, and update the task after progress."
    )
