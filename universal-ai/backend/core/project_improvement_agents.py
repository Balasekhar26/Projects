from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.core.config import load_config
from backend.core.memory import memory


def project_improvement_agents() -> dict[str, Any]:
    path = load_config().root / "config" / "project_improvement_agents.json"
    if not path.exists():
        return {
            "mode": "missing_registry",
            "shared_registry": "docs/SHARED_IMPROVEMENTS.md",
            "projects": {},
        }
    return json.loads(path.read_text(encoding="utf-8"))


def observe_project_improvement_agents(run_status: bool = False) -> dict[str, Any]:
    registry = project_improvement_agents()
    config = load_config()
    projects_root = config.root.parent
    observations: list[dict[str, Any]] = []
    created: list[dict[str, str]] = []
    existing_titles = {
        item["title"]
        for item in memory.list_improvements(limit=500)
        if item["status"] in {"pending", "approved", "done"}
    }

    for project_id, project in registry.get("projects", {}).items():
        rel_path = "07-NeuroSeed" if project_id == "neuroseed" else project_id
        project_root = projects_root / rel_path
        checks = _project_checks(project_root, project, run_status=run_status)
        observations.append(
            {
                "project": project_id,
                "name": project.get("name", project_id),
                "path": str(project_root),
                "healthy": not checks["issues"],
                "checks": checks,
            }
        )
        title = f"{project.get('name', project_id)} improvement agent observation"
        if title in existing_titles:
            continue
        proposal = _proposal_for_project(project_id, project, checks)
        improvement_id = memory.create_improvement(
            title=title,
            motive=proposal["motive"],
            proposal=proposal["proposal"],
            risk=proposal["risk"],
        )
        created.append({"project": project_id, "improvement_id": improvement_id, "title": title})
        existing_titles.add(title)

    return {
        "mode": registry.get("mode", "approval_gated_git_synced_improvement_agents"),
        "observed_projects": len(observations),
        "created_pending_proposals": created,
        "observations": observations,
        "approval_required_before_apply": True,
        "auto_apply": False,
        "publish_after_approval": "docs/SHARED_IMPROVEMENTS.md",
    }


def publish_approved_improvement(item: dict[str, str]) -> dict[str, Any]:
    if item.get("status") != "approved":
        return {"published": False, "reason": "improvement_not_approved"}
    config = load_config()
    registry_path = config.root / "docs" / "SHARED_IMPROVEMENTS.md"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    text = registry_path.read_text(encoding="utf-8") if registry_path.exists() else "# Shared Kattappa AI OS Improvements\n"
    marker = f"improvement:{item['id']}"
    if marker in text:
        return {"published": False, "reason": "already_published", "path": str(registry_path)}
    entry = _shared_registry_entry(item, marker)
    registry_path.write_text(text.rstrip() + "\n\n" + entry + "\n", encoding="utf-8")
    return {"published": True, "path": str(registry_path), "marker": marker}


def check_git_shared_improvements() -> dict[str, Any]:
    config = load_config()
    registry_path = config.root / "docs" / "SHARED_IMPROVEMENTS.md"
    text, source, remote_status = _read_shared_registry_text(registry_path)
    if not text:
        return {
            "checked": False,
            "reason": "shared_registry_missing",
            "created_pending_proposals": [],
            "remote_status": remote_status,
        }
    entries = _parse_shared_entries(text)
    existing_items = memory.list_improvements(limit=500)
    existing_titles = {item["title"] for item in existing_items}
    existing_ids = {item["id"] for item in existing_items}
    created: list[dict[str, str]] = []
    for entry in entries:
        source_id = entry["marker"].removeprefix("improvement:")
        if source_id in existing_ids:
            continue
        title = f"Adopt shared improvement {entry['marker']}"
        if title in existing_titles:
            continue
        improvement_id = memory.create_improvement(
            title=title,
            motive="A sanitized improvement was found in the Git-backed shared registry.",
            proposal=(
                "Review the shared improvement below. Verify source, free-tool policy, local compatibility, "
                "tests, and rollback. Adopt only after local approval.\n\n"
                + entry["body"][:1500]
            ),
            risk="medium",
        )
        created.append({"improvement_id": improvement_id, "title": title, "marker": entry["marker"]})
        existing_titles.add(title)
    return {
        "checked": True,
        "source": source,
        "remote_status": remote_status,
        "shared_entries": len(entries),
        "created_pending_proposals": created,
        "auto_apply": False,
        "approval_required_before_adoption": True,
    }


def _project_checks(project_root: Path, project: dict[str, Any], run_status: bool) -> dict[str, Any]:
    setup = project_root / "setup.bat"
    runner = project_root / "run.exe"
    policy_doc = project_root.parent / str(project.get("policy_doc", ""))
    issues: list[str] = []
    if not project_root.exists():
        issues.append("project folder missing")
    if not setup.exists():
        issues.append("setup.bat missing")
    if not runner.exists():
        issues.append("run.exe missing")
    if not policy_doc.exists():
        issues.append("self-improvement policy doc missing")
    status: dict[str, Any] = {"checked": False}
    if run_status and runner.exists():
        try:
            result = subprocess.run(
                [str(runner), "status"],
                cwd=project_root,
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )
            status = {
                "checked": True,
                "exit_code": result.returncode,
                "summary": "\n".join((result.stdout + result.stderr).splitlines()[:8]),
            }
            if result.returncode != 0:
                issues.append("run.exe status failed")
        except Exception as exc:
            status = {"checked": True, "error": str(exc)}
            issues.append("run.exe status could not run")
    return {
        "setup_bat": setup.exists(),
        "run_exe": runner.exists(),
        "policy_doc": policy_doc.exists(),
        "configured_checks": project.get("checks", []),
        "run_status": status,
        "issues": issues,
    }


def _proposal_for_project(project_id: str, project: dict[str, Any], checks: dict[str, Any]) -> dict[str, str]:
    name = str(project.get("name", project_id))
    if checks["issues"]:
        return {
            "motive": f"Keep {name} production-ready by repairing failed improvement-agent checks.",
            "proposal": (
                f"Observed issues for {name}: {', '.join(checks['issues'])}.\n"
                "Before applying changes, inspect the project, produce a small patch, run setup/status/build checks, "
                "and ask approval before writing, installing, deleting, or publishing."
            ),
            "risk": "medium",
        }
    return {
        "motive": f"Keep {name} improving from healthy baseline observations.",
        "proposal": (
            f"{name} passed the current improvement-agent readiness checks. Next approved improvement should be small, "
            "testable, free/local-only, and based on observed setup, run, build, UI, or workflow friction. "
            "Do not apply automatically; create a focused patch only after approval."
        ),
        "risk": "low",
    }


def _shared_registry_entry(item: dict[str, str], marker: str) -> str:
    now = datetime.now().isoformat(timespec="seconds")
    title = _sanitize(item.get("title", "Untitled improvement"))
    motive = _sanitize(item.get("motive", ""))
    proposal = _sanitize(item.get("proposal", ""))
    risk = _sanitize(item.get("risk", "medium"))
    return (
        f"## Approved Improvement {item['id']}\n\n"
        f"<!-- {marker} -->\n\n"
        f"- Published: {now}\n"
        f"- Title: {title}\n"
        f"- Risk: {risk}\n"
        f"- Approval status: approved\n"
        f"- Motive: {motive}\n\n"
        "Proposal:\n\n"
        f"{proposal}\n\n"
        "Receiving systems must verify policy, compatibility, tests, and rollback, then ask local approval before adopting."
    )


def _parse_shared_entries(text: str) -> list[dict[str, str]]:
    pattern = re.compile(r"<!--\s*(improvement:[^>]+)\s*-->", re.IGNORECASE)
    matches = list(pattern.finditer(text))
    entries: list[dict[str, str]] = []
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        entries.append({"marker": match.group(1).strip(), "body": text[start:end].strip()})
    return entries


def _read_shared_registry_text(registry_path: Path) -> tuple[str, str, dict[str, Any]]:
    repo_root = load_config().root.parent
    remote_ref = "origin/main:universal-ai/docs/SHARED_IMPROVEMENTS.md"
    remote_status: dict[str, Any] = {"checked": False}
    try:
        fetch = subprocess.run(
            ["git", "fetch", "--quiet", "origin"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        show = subprocess.run(
            ["git", "show", remote_ref],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        remote_status = {
            "checked": True,
            "fetch_exit_code": fetch.returncode,
            "show_exit_code": show.returncode,
        }
        if fetch.returncode == 0 and show.returncode == 0 and show.stdout.strip():
            local_text = registry_path.read_text(encoding="utf-8") if registry_path.exists() else ""
            if local_text.strip() and local_text != show.stdout:
                return show.stdout + "\n\n" + local_text, f"{remote_ref} + {registry_path}", remote_status
            return show.stdout, remote_ref, remote_status
    except Exception as exc:
        remote_status = {"checked": True, "error": str(exc)}
    if registry_path.exists():
        return registry_path.read_text(encoding="utf-8"), str(registry_path), remote_status
    return "", str(registry_path), remote_status


def _sanitize(value: str) -> str:
    blocked = ["password", "secret", "token", "api_key", "apikey", "credential"]
    cleaned = value.replace("\r", "").strip()
    for word in blocked:
        cleaned = re.sub(word, "[redacted]", cleaned, flags=re.IGNORECASE)
    return cleaned[:2000]
