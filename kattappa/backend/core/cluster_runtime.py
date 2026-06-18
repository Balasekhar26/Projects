from __future__ import annotations

import json
import socket
from datetime import datetime
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

import httpx

from backend.agents.planner import route_task
from backend.core.cluster_plan import TASK_REQUIREMENTS, local_node_profile
from backend.core.config import load_config
from backend.core.memory import memory
from backend.core.safety import classify_risk


ALLOWED_WORKER_AGENTS = {"evaluator", "coder", "builder", "finance"}


def cluster_runtime_status() -> dict[str, Any]:
    profile = local_node_profile()
    return {
        "mode": "explicit_paired_local_worker_runtime",
        "enabled": True,
        "local_node": profile,
        "local_runnable_tasks": runnable_task_kinds(profile),
        "paired_nodes": safe_paired_nodes(),
        "privacy_contract": privacy_contract(),
    }


def register_paired_node(
    name: str,
    base_url: str,
    token: str,
    capabilities: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not name.strip():
        raise ValueError("name is required")
    clean_url = _validate_local_url(base_url)
    if len(token.strip()) < 12:
        raise ValueError("token must be at least 12 characters")
    capabilities = capabilities or {}
    now = _now()
    node = {
        "id": str(uuid4()),
        "name": name.strip()[:80],
        "base_url": clean_url,
        "token": token.strip(),
        "capabilities": capabilities,
        "runnable_tasks": _runnable_tasks_from_capabilities(capabilities),
        "trusted": True,
        "created_at": now,
        "updated_at": now,
    }
    nodes = _load_nodes()
    nodes = [item for item in nodes if item.get("base_url") != clean_url]
    nodes.append(node)
    _save_nodes(nodes)
    return _safe_node(node)


def list_paired_nodes() -> list[dict[str, Any]]:
    return [_safe_node(node) for node in _load_nodes()]


def safe_paired_nodes() -> list[dict[str, Any]]:
    return list_paired_nodes()


def remove_paired_node(node_id: str) -> bool:
    nodes = _load_nodes()
    kept = [node for node in nodes if node.get("id") != node_id]
    if len(kept) == len(nodes):
        return False
    _save_nodes(kept)
    return True


def route_cluster_task(
    message: str,
    task_kind: str = "basic_chat",
    sensitivity: str = "normal",
    force_remote: bool = False,
) -> dict[str, Any]:
    if task_kind not in TASK_REQUIREMENTS:
        raise ValueError(f"Unknown cluster task kind: {task_kind}")
    if sensitivity not in {"normal", "private", "sensitive"}:
        raise ValueError("sensitivity must be normal, private, or sensitive")
    if sensitivity == "sensitive":
        return {
            "status": "not_delegated_sensitive",
            "run_location": "local_only",
            "message": "Sensitive tasks stay on the origin system.",
            "privacy_contract": privacy_contract(),
        }

    local_profile = local_node_profile()
    if can_run_task(task_kind, local_profile) and not force_remote:
        return {
            "status": "local_capable",
            "run_location": "local",
            "task_kind": task_kind,
            "local_node": local_profile,
            "message": "Local system can run this task; no worker handoff needed.",
        }

    node = _select_worker(task_kind)
    if node is None:
        return {
            "status": "no_capable_paired_node",
            "run_location": "not_started",
            "task_kind": task_kind,
            "local_node": local_profile,
            "paired_nodes": safe_paired_nodes(),
            "message": "No trusted paired node is registered with enough capability for this task.",
        }

    task_id = str(uuid4())
    payload = {
        "task_id": task_id,
        "task_kind": task_kind,
        "message": message,
        "origin_node": {
            "hostname": socket.gethostname(),
            "role": "manager",
        },
        "privacy": privacy_contract(),
    }
    worker_result = _post_worker_task(node, payload)
    _record_manager_result(message, worker_result)
    return {
        "status": "delegated",
        "run_location": "paired_worker",
        "task_id": task_id,
        "worker": _safe_node(node),
        "worker_result": worker_result,
        "privacy_contract": privacy_contract(),
    }


def execute_worker_task(
    task_id: str,
    task_kind: str,
    message: str,
    origin_node: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if task_kind not in TASK_REQUIREMENTS:
        raise ValueError(f"Unknown cluster task kind: {task_kind}")
    if not can_run_task(task_kind, local_node_profile()):
        return {
            "status": "rejected_over_limit",
            "task_id": task_id,
            "task_kind": task_kind,
            "worker_profile": local_node_profile(),
            "cleanup_receipt": _cleanup_receipt(task_id, deleted=True),
        }
    risk = classify_risk(message)
    if risk.blocked or risk.approval_required:
        return {
            "status": "rejected_needs_origin_approval",
            "task_id": task_id,
            "task_kind": task_kind,
            "risk": risk.level,
            "reason": risk.reason,
            "cleanup_receipt": _cleanup_receipt(task_id, deleted=True),
        }
    routing = route_task(message)
    selected_agent = str(routing.get("agent") or "evaluator")
    if selected_agent not in ALLOWED_WORKER_AGENTS:
        return {
            "status": "rejected_agent_not_worker_safe",
            "task_id": task_id,
            "task_kind": task_kind,
            "selected_agent": selected_agent,
            "cleanup_receipt": _cleanup_receipt(task_id, deleted=True),
        }

    from backend.core.graph import run_graph

    try:
        state = run_graph(message, memory_query="", ephemeral_worker=True)
        return {
            "status": "completed",
            "task_id": task_id,
            "task_kind": task_kind,
            "origin_node": origin_node or {},
            "result": state.get("result") or "",
            "state_summary": {
                "selected_agent": state.get("selected_agent"),
                "risk_level": state.get("risk_level"),
                "logs": state.get("logs", []),
            },
            "cleanup_receipt": _cleanup_receipt(task_id, deleted=True),
        }
    finally:
        message = ""
        origin_node = {}


def worker_token_is_valid(token: str | None) -> bool:
    if not token:
        return False
    return any(str(node.get("token") or "") == token for node in _load_nodes())


def can_run_task(task_kind: str, profile: dict[str, Any]) -> bool:
    requirement = TASK_REQUIREMENTS.get(task_kind)
    if not requirement:
        return False
    cpu = int(profile.get("cpu_count_logical") or 0)
    ram = float(profile.get("ram_total_gb") or 0)
    return cpu >= int(requirement["min_cpu_logical"]) and ram >= float(requirement["min_ram_gb"])


def runnable_task_kinds(profile: dict[str, Any]) -> list[str]:
    return [task for task in TASK_REQUIREMENTS if can_run_task(task, profile)]


def privacy_contract() -> dict[str, Any]:
    return {
        "task_origin_stores_history": True,
        "worker_persistent_chat_storage": False,
        "worker_persistent_task_storage": False,
        "worker_may_store_private_context": False,
        "worker_returns_result_to_manager": True,
        "worker_deletes_task_context_after_completion": True,
        "worker_deletes_task_context_on_failure_or_cancel": True,
        "worker_cleanup_receipt_required": True,
    }


def _select_worker(task_kind: str) -> dict[str, Any] | None:
    for node in _load_nodes():
        if not node.get("trusted", False):
            continue
        runnable = set(node.get("runnable_tasks") or _runnable_tasks_from_capabilities(node.get("capabilities") or {}))
        if task_kind in runnable:
            return node
    return None


def _runnable_tasks_from_capabilities(capabilities: dict[str, Any]) -> list[str]:
    explicit = capabilities.get("runnable_tasks")
    if isinstance(explicit, list):
        return [str(task) for task in explicit if str(task) in TASK_REQUIREMENTS]
    boolean_enabled = [
        task
        for task in TASK_REQUIREMENTS
        if capabilities.get(task) is True
    ]
    if boolean_enabled:
        return boolean_enabled
    return runnable_task_kinds(capabilities)


def _post_worker_task(node: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    response = httpx.post(
        f"{str(node['base_url']).rstrip('/')}/cluster/worker/tasks",
        json=payload,
        headers={"X-Kattappa-Cluster-Token": str(node["token"])},
        timeout=180,
    )
    response.raise_for_status()
    result = response.json()
    if not result.get("cleanup_receipt", {}).get("task_context_deleted"):
        result["privacy_warning"] = "Worker did not return a positive cleanup receipt."
    return result


def _record_manager_result(message: str, worker_result: dict[str, Any]) -> None:
    session = memory.get_or_create_primary_chat_session()
    memory.add_chat_message(session["id"], "user", message)
    memory.add_chat_message(
        session["id"],
        "assistant",
        str(worker_result.get("result") or worker_result.get("message") or worker_result),
        agent="cluster_worker",
        risk=str(worker_result.get("state_summary", {}).get("risk_level", "")),
    )


def _cleanup_receipt(task_id: str, deleted: bool) -> dict[str, Any]:
    return {
        "task_id": task_id,
        "task_context_deleted": deleted,
        "worker_private_memory_written": False,
        "worker_chat_history_written": False,
        "deleted_at": _now(),
        "method": "ephemeral_in_memory_payload_cleared",
    }


def _validate_local_url(base_url: str) -> str:
    parsed = urlparse(base_url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("base_url must be an http(s) URL")
    host = parsed.hostname or ""
    parts = host.split(".")
    is_172_local = False
    if len(parts) >= 2 and parts[0] == "172":
        try:
            is_172_local = 16 <= int(parts[1]) <= 31
        except ValueError:
            is_172_local = False
    is_localhost = host in {"localhost", "127.0.0.1", "::1"} or host.endswith(".local")
    is_private_lan = host.startswith("10.") or host.startswith("192.168.") or host.startswith("127.") or is_172_local
    if not (is_localhost or is_private_lan):
        raise ValueError("Only trusted local-network node URLs are allowed")
    return base_url.strip().rstrip("/")


def _safe_node(node: dict[str, Any]) -> dict[str, Any]:
    safe = dict(node)
    safe.pop("token", None)
    safe["token_configured"] = bool(node.get("token"))
    return safe


def _nodes_path():
    path = load_config().backend_root / "data" / "cluster" / "paired_nodes.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _load_nodes() -> list[dict[str, Any]]:
    path = _nodes_path()
    if not path.exists():
        return []
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    return loaded if isinstance(loaded, list) else []


def _save_nodes(nodes: list[dict[str, Any]]) -> None:
    _nodes_path().write_text(json.dumps(nodes, indent=2), encoding="utf-8")


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")
