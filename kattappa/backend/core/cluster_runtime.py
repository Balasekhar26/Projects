from __future__ import annotations

import json
import secrets
import socket
from datetime import datetime, timedelta
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
PUBLIC_WORKER_TASKS = {
    "basic_chat",
    "repo_indexing",
    "voice_transcription",
    "small_local_model",
    "large_local_model",
    "simulation",
}
DELEGABLE_AGENT_TASKS = {
    "coder": "repo_indexing",
    "builder": "repo_indexing",
    "researcher": "basic_chat",
    "finance": "simulation",
    "voice": "voice_transcription",
    "evaluator": "basic_chat",
    "memory": "project_memory",
    "self_improver": "project_memory",
}
NON_DELEGABLE_AGENT_TASKS = {
    "desktop": "screen_ocr",
    "vision": "screen_ocr",
    "browser": "desktop_ui",
    "terminal": "desktop_ui",
    "file": "desktop_ui",
}


def cluster_runtime_status() -> dict[str, Any]:
    profile = local_node_profile()
    return {
        "mode": "explicit_paired_local_worker_runtime",
        "enabled": True,
        "local_node": profile,
        "local_runnable_tasks": runnable_task_kinds(profile),
        "paired_nodes": safe_paired_nodes(),
        "discovery_targets": list_discovery_targets(),
        "public_worker": public_worker_status(),
        "broker": {
            "mode": "capability_bid_then_best_worker",
            "broadcast_scope": "paired_and_unpaired_open_kattappa_nodes",
            "transport": "trusted_http_or_https_nodes_with_one_time_public_task_tokens",
            "internet_ready": True,
        },
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


def register_discovery_target(name: str, base_url: str) -> dict[str, Any]:
    if not name.strip():
        raise ValueError("name is required")
    clean_url = _validate_discovery_url(base_url)
    now = _now()
    target = {
        "id": str(uuid4()),
        "name": name.strip()[:80],
        "base_url": clean_url,
        "trusted": False,
        "token_required": False,
        "created_at": now,
        "updated_at": now,
    }
    targets = _load_discovery_targets()
    targets = [item for item in targets if item.get("base_url") != clean_url]
    targets.append(target)
    _save_discovery_targets(targets)
    return _safe_discovery_target(target)


def list_discovery_targets() -> list[dict[str, Any]]:
    return [_safe_discovery_target(target) for target in _load_discovery_targets()]


def remove_discovery_target(target_id: str) -> bool:
    targets = _load_discovery_targets()
    kept = [target for target in targets if target.get("id") != target_id]
    if len(kept) == len(targets):
        return False
    _save_discovery_targets(kept)
    return True


def route_cluster_task(
    message: str,
    task_kind: str = "basic_chat",
    sensitivity: str = "normal",
    force_remote: bool = False,
    record_result: bool = True,
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
    if not TASK_REQUIREMENTS[task_kind].get("delegable", False):
        return {
            "status": "not_delegated_non_delegable",
            "run_location": "local_only",
            "task_kind": task_kind,
            "message": "This task requires the origin system, screen, files, terminal, browser, or desktop context.",
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

    bid_round = collect_worker_bids(message, task_kind, include_assignment_secrets=True)
    selected_bid = select_best_bid(bid_round["bids"])
    if selected_bid is None:
        hub_url = os.getenv("KATTAPPA_INTERNET_HUB_URL") or "http://127.0.0.1:8000"
        if hub_url:
            return route_internet_hub_task(message, task_kind, hub_url)
        return {
            "status": "no_capable_paired_node",
            "run_location": "not_started",
            "task_kind": task_kind,
            "local_node": local_profile,
            "paired_nodes": safe_paired_nodes(),
            "discovery_targets": list_discovery_targets(),
            "bid_round": _safe_bid_round(bid_round),
            "message": "No opened Kattappa worker replied with enough capability for this task.",
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
    worker_kind = str(selected_bid.get("worker_kind") or "paired_worker")
    if worker_kind == "unpaired_public_worker":
        worker_result = _post_public_worker_task(selected_bid, payload)
        worker = _safe_public_worker_from_bid(selected_bid)
        run_location = "unpaired_public_worker"
    else:
        node = _node_by_id(str(selected_bid["node_id"]))
        if node is None:
            return {
                "status": "selected_node_missing",
                "run_location": "not_started",
                "task_kind": task_kind,
                "bid_round": _safe_bid_round(bid_round),
                "message": "The selected worker disappeared before assignment.",
            }
        worker_result = _post_worker_task(node, payload)
        worker = _safe_node(node)
        run_location = "paired_worker"
    if record_result:
        _record_manager_result(message, worker_result)
    return {
        "status": "delegated",
        "run_location": run_location,
        "task_id": task_id,
        "worker": worker,
        "selected_bid": _safe_bid(selected_bid),
        "bid_round": _safe_bid_round(bid_round),
        "worker_result": worker_result,
        "privacy_contract": privacy_contract(),
    }


def auto_delegate_if_local_unable(message: str) -> dict[str, Any] | None:
    task_kind = infer_cluster_task_kind(message)
    if task_kind is None:
        return None
    if not TASK_REQUIREMENTS[task_kind].get("delegable", False):
        return None
    if can_run_task(task_kind, local_node_profile()):
        return None
    return route_cluster_task(
        message,
        task_kind=task_kind,
        sensitivity="normal",
        record_result=False,
    )


def infer_cluster_task_kind(message: str) -> str | None:
    lower = message.lower()
    if any(term in lower for term in ("large model", "70b", "30b", "heavy model", "high spec model")):
        return "large_local_model"
    if any(term in lower for term in ("transcribe", "voice", "audio", "microphone", "speech to text")):
        return "voice_transcription"
    if any(term in lower for term in ("simulation", "simulate", "forecast", "kronos")):
        return "simulation"
    routing = route_task(message)
    agent = str(routing.get("agent") or "evaluator")
    if agent in NON_DELEGABLE_AGENT_TASKS:
        return None
    return DELEGABLE_AGENT_TASKS.get(agent, "basic_chat")


def collect_worker_bids(
    message: str,
    task_kind: str,
    include_assignment_secrets: bool = False,
) -> dict[str, Any]:
    if task_kind not in TASK_REQUIREMENTS:
        raise ValueError(f"Unknown cluster task kind: {task_kind}")
    bid_id = str(uuid4())
    bids: list[dict[str, Any]] = []
    unavailable: list[dict[str, Any]] = []
    for node in _load_nodes():
        if not node.get("trusted", False):
            continue
        try:
            bid = _post_worker_bid(
                node,
                {
                    "bid_id": bid_id,
                    "task_kind": task_kind,
                    "message": message,
                    "origin_node": {
                        "hostname": socket.gethostname(),
                        "role": "manager",
                    },
                    "privacy": privacy_contract(),
                },
            )
            bid["node_id"] = node["id"]
            bid["node_name"] = node["name"]
            bid["node_url"] = node["base_url"]
            bid["worker_kind"] = "paired_worker"
            if bid.get("can_run"):
                bids.append(bid)
            else:
                unavailable.append(_safe_bid_failure(node, bid.get("reason", "worker_declined")))
        except Exception as exc:
            unavailable.append(_safe_bid_failure(node, str(exc)))
    for target in _load_discovery_targets():
        try:
            bid = _post_public_worker_bid(
                target,
                {
                    "bid_id": bid_id,
                    "task_kind": task_kind,
                    "capability_hint": _task_capability_hint(task_kind),
                    "origin_node": {
                        "hostname": socket.gethostname(),
                        "role": "manager",
                    },
                    "privacy": privacy_contract(),
                },
            )
            bid["node_id"] = f"public:{target['id']}"
            bid["node_name"] = target["name"]
            bid["node_url"] = target["base_url"]
            bid["worker_kind"] = "unpaired_public_worker"
            if bid.get("can_run"):
                bids.append(bid)
            else:
                unavailable.append(_safe_discovery_failure(target, bid.get("reason", "worker_declined")))
        except Exception as exc:
            unavailable.append(_safe_discovery_failure(target, str(exc)))
    bids.sort(key=lambda item: int(item.get("score") or 0), reverse=True)
    result = {
        "bid_id": bid_id,
        "task_kind": task_kind,
        "broadcast_scope": "paired_and_unpaired_open_kattappa_nodes",
        "bids": bids,
        "unavailable": unavailable,
        "privacy_contract": privacy_contract(),
    }
    return result if include_assignment_secrets else _safe_bid_round(result)


def select_best_bid(bids: list[dict[str, Any]]) -> dict[str, Any] | None:
    return bids[0] if bids else None


def worker_capability_bid(
    bid_id: str,
    task_kind: str,
    message: str,
    origin_node: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if task_kind not in TASK_REQUIREMENTS:
        return {
            "bid_id": bid_id,
            "can_run": False,
            "reason": f"unknown_task_kind:{task_kind}",
            "score": 0,
            "worker_profile": local_node_profile(),
            "cleanup_policy": privacy_contract(),
        }
    profile = local_node_profile()
    if not can_run_task(task_kind, profile):
        return {
            "bid_id": bid_id,
            "can_run": False,
            "reason": "worker_over_limit",
            "score": 0,
            "worker_profile": profile,
            "cleanup_policy": privacy_contract(),
        }
    risk = classify_risk(message)
    if risk.blocked or risk.approval_required:
        return {
            "bid_id": bid_id,
            "can_run": False,
            "reason": "worker_requires_origin_approval",
            "risk": risk.level,
            "score": 0,
            "worker_profile": profile,
            "cleanup_policy": privacy_contract(),
        }
    selected_agent = str(route_task(message).get("agent") or "evaluator")
    if selected_agent not in ALLOWED_WORKER_AGENTS:
        return {
            "bid_id": bid_id,
            "can_run": False,
            "reason": "agent_not_worker_safe",
            "selected_agent": selected_agent,
            "score": 0,
            "worker_profile": profile,
            "cleanup_policy": privacy_contract(),
        }
    return {
        "bid_id": bid_id,
        "can_run": True,
        "reason": "capable",
        "selected_agent": selected_agent,
        "task_kind": task_kind,
        "score": _capability_score(task_kind, profile),
        "worker_profile": profile,
        "origin_node_seen": origin_node or {},
        "cleanup_policy": privacy_contract(),
    }


def public_worker_status() -> dict[str, Any]:
    profile = local_node_profile()
    return {
        "enabled": True,
        "mode": "unpaired_public_bid_with_one_time_task_token",
        "accepts_task_content_in_bid": False,
        "runnable_public_tasks": [
            task for task in PUBLIC_WORKER_TASKS if can_run_task(task, profile)
        ],
        "profile": profile,
        "cleanup_policy": privacy_contract(),
    }


def public_worker_capability_bid(
    bid_id: str,
    task_kind: str,
    capability_hint: dict[str, Any] | None = None,
    origin_node: dict[str, Any] | None = None,
) -> dict[str, Any]:
    profile = local_node_profile()
    if task_kind not in TASK_REQUIREMENTS:
        return {
            "bid_id": bid_id,
            "can_run": False,
            "reason": f"unknown_task_kind:{task_kind}",
            "score": 0,
            "worker_profile": profile,
            "cleanup_policy": privacy_contract(),
        }
    if task_kind not in PUBLIC_WORKER_TASKS:
        return {
            "bid_id": bid_id,
            "can_run": False,
            "reason": "task_kind_not_allowed_for_unpaired_worker",
            "score": 0,
            "worker_profile": profile,
            "cleanup_policy": privacy_contract(),
        }
    if not TASK_REQUIREMENTS[task_kind].get("delegable", False):
        return {
            "bid_id": bid_id,
            "can_run": False,
            "reason": "task_kind_requires_origin_system",
            "score": 0,
            "worker_profile": profile,
            "cleanup_policy": privacy_contract(),
        }
    if not can_run_task(task_kind, profile):
        return {
            "bid_id": bid_id,
            "can_run": False,
            "reason": "worker_over_limit",
            "score": 0,
            "worker_profile": profile,
            "cleanup_policy": privacy_contract(),
        }
    assignment_token = _mint_public_task_token(bid_id, task_kind)
    return {
        "bid_id": bid_id,
        "can_run": True,
        "reason": "capable_without_pairing",
        "selected_agent": "worker_after_assignment",
        "task_kind": task_kind,
        "score": _capability_score(task_kind, profile),
        "worker_kind": "unpaired_public_worker",
        "worker_profile": profile,
        "capability_hint_seen": capability_hint or {},
        "origin_node_seen": origin_node or {},
        "assignment_url": "/cluster/public/tasks",
        "assignment_token": assignment_token,
        "cleanup_policy": privacy_contract(),
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


def execute_public_worker_task(
    task_id: str,
    task_kind: str,
    message: str,
    assignment_token: str | None,
    origin_node: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not _consume_public_task_token(assignment_token, task_kind):
        return {
            "status": "rejected_invalid_public_task_token",
            "task_id": task_id,
            "task_kind": task_kind,
            "cleanup_receipt": _cleanup_receipt(task_id, deleted=True),
        }
    return execute_worker_task(
        task_id,
        task_kind,
        message,
        origin_node=origin_node,
    )


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
        "worker_bid_contains_no_private_result": True,
        "unpaired_worker_bid_receives_task_message": False,
        "unpaired_worker_task_requires_one_time_token": True,
        "worker_task_payload_is_memory_only": True,
    }


def _select_worker(task_kind: str) -> dict[str, Any] | None:
    for node in _load_nodes():
        if not node.get("trusted", False):
            continue
        runnable = set(node.get("runnable_tasks") or _runnable_tasks_from_capabilities(node.get("capabilities") or {}))
        if task_kind in runnable:
            return node
    return None


def _node_by_id(node_id: str) -> dict[str, Any] | None:
    for node in _load_nodes():
        if str(node.get("id")) == node_id:
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


def _post_worker_bid(node: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    response = httpx.post(
        f"{str(node['base_url']).rstrip('/')}/cluster/worker/bid",
        json=payload,
        headers={"X-Kattappa-Cluster-Token": str(node["token"])},
        timeout=12,
    )
    response.raise_for_status()
    return response.json()


def _post_public_worker_bid(target: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    payload = dict(payload)
    payload.pop("message", None)
    response = httpx.post(
        f"{str(target['base_url']).rstrip('/')}/cluster/public/bid",
        json=payload,
        timeout=12,
    )
    response.raise_for_status()
    result = response.json()
    assignment_url = str(result.get("assignment_url") or "/cluster/public/tasks")
    if assignment_url.startswith("/"):
        result["assignment_url"] = f"{str(target['base_url']).rstrip()}{assignment_url}"
    return result


def _post_public_worker_task(selected_bid: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    assignment_url = str(selected_bid.get("assignment_url") or "")
    assignment_token = str(selected_bid.get("assignment_token") or "")
    if not assignment_url or not assignment_token:
        raise ValueError("Selected unpaired worker did not return an assignment token")
    response = httpx.post(
        assignment_url,
        json=payload,
        headers={"X-Kattappa-Public-Task-Token": assignment_token},
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
        "deleted_payload_fields": ["message", "origin_node", "memory_context", "related_messages"],
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
    if not (is_localhost or is_private_lan or parsed.scheme == "https"):
        raise ValueError("Public internet nodes must use HTTPS and an explicit pairing token")
    return base_url.strip().rstrip("/")


def _validate_discovery_url(base_url: str) -> str:
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
    if not (is_localhost or is_private_lan or parsed.scheme == "https"):
        raise ValueError("Public unpaired discovery targets must use HTTPS")
    return base_url.strip().rstrip("/")


def _capability_score(task_kind: str, profile: dict[str, Any]) -> int:
    requirement = TASK_REQUIREMENTS[task_kind]
    cpu = int(profile.get("cpu_count_logical") or 0)
    ram = float(profile.get("ram_total_gb") or 0)
    cpu_score = min(45, round((cpu / max(int(requirement["min_cpu_logical"]), 1)) * 20))
    ram_score = min(45, round((ram / max(float(requirement["min_ram_gb"]), 1.0)) * 20))
    tier_bonus = 10 if str(profile.get("capability_tier", "")).lower() not in {"controller_only", "minimum"} else 0
    return min(100, cpu_score + ram_score + tier_bonus)


def _safe_bid_failure(node: dict[str, Any], reason: str) -> dict[str, Any]:
    return {
        "node": _safe_node(node),
        "can_run": False,
        "reason": reason,
    }


def _safe_discovery_failure(target: dict[str, Any], reason: str) -> dict[str, Any]:
    return {
        "node": _safe_discovery_target(target),
        "can_run": False,
        "reason": reason,
    }


def _safe_bid(bid: dict[str, Any]) -> dict[str, Any]:
    safe = dict(bid)
    safe.pop("assignment_token", None)
    return safe


def _safe_bid_round(bid_round: dict[str, Any]) -> dict[str, Any]:
    safe = dict(bid_round)
    safe["bids"] = [_safe_bid(bid) for bid in bid_round.get("bids", [])]
    return safe


def _safe_public_worker_from_bid(bid: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(bid.get("node_id") or ""),
        "name": str(bid.get("node_name") or "Unpaired Kattappa worker"),
        "base_url": str(bid.get("node_url") or ""),
        "trusted": False,
        "paired": False,
        "worker_kind": "unpaired_public_worker",
        "token_configured": False,
    }


def _safe_node(node: dict[str, Any]) -> dict[str, Any]:
    safe = dict(node)
    safe.pop("token", None)
    safe["token_configured"] = bool(node.get("token"))
    return safe


def _safe_discovery_target(target: dict[str, Any]) -> dict[str, Any]:
    safe = dict(target)
    safe["token_required"] = False
    safe["trusted"] = False
    return safe


def _task_capability_hint(task_kind: str) -> dict[str, Any]:
    requirement = TASK_REQUIREMENTS.get(task_kind, {})
    return {
        "task_kind": task_kind,
        "min_cpu_logical": requirement.get("min_cpu_logical"),
        "min_ram_gb": requirement.get("min_ram_gb"),
        "delegable": requirement.get("delegable", False),
        "message_included": False,
    }


def _mint_public_task_token(bid_id: str, task_kind: str) -> str:
    token = secrets.token_urlsafe(32)
    tokens = _load_public_task_tokens()
    now = datetime.now()
    tokens = [
        item
        for item in tokens
        if not item.get("used")
        and _parse_time(str(item.get("expires_at") or "")) > now
    ]
    tokens.append(
        {
            "token": token,
            "bid_id": bid_id,
            "task_kind": task_kind,
            "created_at": _now(),
            "expires_at": (now + timedelta(minutes=5)).isoformat(timespec="seconds"),
            "used": False,
        }
    )
    _save_public_task_tokens(tokens)
    return token


def _consume_public_task_token(token: str | None, task_kind: str) -> bool:
    if not token:
        return False
    tokens = _load_public_task_tokens()
    now = datetime.now()
    matched = False
    for item in tokens:
        if item.get("token") != token:
            continue
        if item.get("used") or item.get("task_kind") != task_kind:
            continue
        if _parse_time(str(item.get("expires_at") or "")) <= now:
            continue
        item["used"] = True
        item["used_at"] = _now()
        matched = True
        break
    _save_public_task_tokens(tokens)
    return matched


def _parse_time(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return datetime.min


def _nodes_path():
    path = load_config().backend_root / "data" / "cluster" / "paired_nodes.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _discovery_targets_path():
    path = load_config().backend_root / "data" / "cluster" / "discovery_targets.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _public_task_tokens_path():
    path = load_config().backend_root / "data" / "cluster" / "public_task_tokens.json"
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


def _load_discovery_targets() -> list[dict[str, Any]]:
    path = _discovery_targets_path()
    if not path.exists():
        return []
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    return loaded if isinstance(loaded, list) else []


def _load_public_task_tokens() -> list[dict[str, Any]]:
    path = _public_task_tokens_path()
    if not path.exists():
        return []
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    return loaded if isinstance(loaded, list) else []


def _save_nodes(nodes: list[dict[str, Any]]) -> None:
    _nodes_path().write_text(json.dumps(nodes, indent=2), encoding="utf-8")


def _save_discovery_targets(targets: list[dict[str, Any]]) -> None:
    _discovery_targets_path().write_text(json.dumps(targets, indent=2), encoding="utf-8")


def _save_public_task_tokens(tokens: list[dict[str, Any]]) -> None:
    _public_task_tokens_path().write_text(json.dumps(tokens, indent=2), encoding="utf-8")


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


# --- Internet Hub Task Handoff Protocol ---
import os
import time

_local_worker_id = str(uuid4())
_hub_tasks: dict[str, dict[str, Any]] = {}


def hub_post_task(task_id: str, task_kind: str, min_cpu: int, min_ram: float) -> dict[str, Any]:
    _hub_tasks[task_id] = {
        "task_id": task_id,
        "task_kind": task_kind,
        "min_cpu": min_cpu,
        "min_ram": min_ram,
        "status": "pending",
        "bids": {},
        "selected_worker_id": None,
        "payload": None,
        "result": None,
        "error": None,
        "created_at": datetime.now().isoformat()
    }
    return _hub_tasks[task_id]


def hub_get_pending_tasks() -> list[dict[str, Any]]:
    return [
        {
            "task_id": t["task_id"],
            "task_kind": t["task_kind"],
            "min_cpu": t["min_cpu"],
            "min_ram": t["min_ram"]
        }
        for t in _hub_tasks.values()
        if t["status"] == "pending"
    ]


def hub_bid_task(task_id: str, worker_id: str, hostname: str, cpu: int, ram: float) -> bool:
    if task_id not in _hub_tasks:
        return False
    t = _hub_tasks[task_id]
    if t["status"] != "pending":
        return False
    t["bids"][worker_id] = {
        "worker_id": worker_id,
        "hostname": hostname,
        "cpu_count": cpu,
        "ram_total_gb": ram,
        "timestamp": datetime.now().isoformat()
    }
    return True


def hub_get_bids(task_id: str) -> list[dict[str, Any]]:
    if task_id not in _hub_tasks:
        return []
    return list(_hub_tasks[task_id]["bids"].values())


def hub_delegate_task(task_id: str, worker_id: str, message: str) -> bool:
    if task_id not in _hub_tasks:
        return False
    t = _hub_tasks[task_id]
    if t["status"] != "pending":
        return False
    t["selected_worker_id"] = worker_id
    t["payload"] = message
    t["status"] = "delegated"
    return True


def hub_get_payload(task_id: str, worker_id: str) -> dict[str, Any] | None:
    if task_id not in _hub_tasks:
        return None
    t = _hub_tasks[task_id]
    if t["status"] != "delegated" or t["selected_worker_id"] != worker_id:
        return None
    return {
        "task_id": task_id,
        "message": t["payload"]
    }


def hub_submit_result(task_id: str, worker_id: str, result: str, error: str | None = None) -> bool:
    if task_id not in _hub_tasks:
        return False
    t = _hub_tasks[task_id]
    if t["status"] != "delegated" or t["selected_worker_id"] != worker_id:
        return False
    t["result"] = result
    t["error"] = error
    t["status"] = "completed"
    return True


def hub_get_result(task_id: str) -> dict[str, Any] | None:
    if task_id not in _hub_tasks:
        return None
    t = _hub_tasks[task_id]
    return {
        "status": t["status"],
        "result": t["result"],
        "error": t["error"]
    }


def route_internet_hub_task(message: str, task_kind: str, hub_url: str) -> dict[str, Any]:
    task_id = str(uuid4())
    req = TASK_REQUIREMENTS.get(task_kind, {"min_cpu_logical": 2, "min_ram_gb": 4.0})
    min_cpu = int(req.get("min_cpu_logical", 2))
    min_ram = float(req.get("min_ram_gb", 4.0))

    try:
        # 1. Post task to Coordinator Hub
        with httpx.Client() as client:
            res = client.post(
                f"{hub_url.rstrip('/')}/cluster/hub/post-task",
                json={
                    "task_id": task_id,
                    "task_kind": task_kind,
                    "min_cpu": min_cpu,
                    "min_ram": min_ram
                },
                timeout=10
            )
            res.raise_for_status()

            # 2. Poll for bids
            bids = []
            for _ in range(30):
                time.sleep(0.5)
                bids_res = client.get(f"{hub_url.rstrip('/')}/cluster/hub/tasks/{task_id}/bids", timeout=5)
                bids_res.raise_for_status()
                bids = bids_res.json().get("bids", [])
                if bids:
                    break

            if not bids:
                return {
                    "status": "no_internet_bidders",
                    "task_id": task_id,
                    "message": "No internet worker bid for the task within the timeout.",
                }

            # 3. Select most capable bidder
            bids.sort(key=lambda b: (b.get("ram_total_gb", 0), b.get("cpu_count", 0)), reverse=True)
            selected_bidder = bids[0]
            worker_id = selected_bidder["worker_id"]

            # 4. Delegate payload to chosen bidder
            del_res = client.post(
                f"{hub_url.rstrip('/')}/cluster/hub/tasks/{task_id}/delegate",
                json={
                    "worker_id": worker_id,
                    "message": message
                },
                timeout=10
            )
            del_res.raise_for_status()

            # 5. Poll for completion output
            for _ in range(240):
                time.sleep(0.5)
                res_check = client.get(f"{hub_url.rstrip('/')}/cluster/hub/tasks/{task_id}/result", timeout=5)
                res_check.raise_for_status()
                result_data = res_check.json()
                if result_data.get("status") == "completed":
                    _record_manager_result(message, {
                        "result": result_data.get("result"),
                        "state_summary": {"risk_level": "low"},
                    })
                    return {
                        "status": "delegated_internet",
                        "run_location": "internet_hub_worker",
                        "task_id": task_id,
                        "worker": selected_bidder,
                        "result": result_data.get("result"),
                    }
                elif result_data.get("status") == "failed":
                    return {
                        "status": "internet_execution_failed",
                        "task_id": task_id,
                        "error": result_data.get("error"),
                    }

            return {
                "status": "internet_timeout",
                "task_id": task_id,
                "message": "Internet execution timed out.",
            }

    except Exception as exc:
        return {
            "status": "internet_hub_error",
            "task_id": task_id,
            "error": str(exc),
        }


def internet_hub_worker_poll_loop() -> None:
    hub_url = os.getenv("KATTAPPA_INTERNET_HUB_URL") or "http://127.0.0.1:8000"
    if not hub_url:
        return

    profile = local_node_profile()
    cpu = int(profile.get("cpu_count_logical") or 0)
    ram = float(profile.get("ram_total_gb") or 0)
    hostname = socket.gethostname()
    bid_tasks = set()

    while True:
        try:
            with httpx.Client() as client:
                # 1. Fetch pending tasks
                res = client.get(f"{hub_url.rstrip('/')}/cluster/hub/pending-tasks", timeout=10)
                if res.status_code == 200:
                    tasks = res.json().get("tasks", [])
                    for t in tasks:
                        task_id = t["task_id"]
                        if task_id in bid_tasks:
                            continue

                        req_cpu = int(t.get("min_cpu", 2))
                        req_ram = float(t.get("min_ram", 4.0))
                        if cpu >= req_cpu and ram >= req_ram:
                            bid_res = client.post(
                                f"{hub_url.rstrip('/')}/cluster/hub/bid-task",
                                json={
                                    "task_id": task_id,
                                    "worker_id": _local_worker_id,
                                    "hostname": hostname,
                                    "cpu_count": cpu,
                                    "ram_total_gb": ram
                                },
                                timeout=10
                            )
                            if bid_res.status_code == 200:
                                bid_tasks.add(task_id)

                # 2. Check if we won delegation
                for task_id in list(bid_tasks):
                    pay_res = client.get(
                        f"{hub_url.rstrip('/')}/cluster/hub/tasks/{task_id}/payload",
                        params={"worker_id": _local_worker_id},
                        timeout=10
                    )
                    if pay_res.status_code == 200:
                        payload = pay_res.json()
                        if payload and "message" in payload:
                            message = payload["message"]
                            from backend.core.graph import run_graph
                            result_str = ""
                            err_str = None
                            try:
                                state = run_graph(message, memory_query="", ephemeral_worker=True)
                                result_str = str(state.get("result") or "")
                            except Exception as e:
                                err_str = str(e)
                                result_str = f"Error: {err_str}"

                            client.post(
                                f"{hub_url.rstrip('/')}/cluster/hub/tasks/{task_id}/submit-result",
                                json={
                                    "worker_id": _local_worker_id,
                                    "result": result_str,
                                    "error": err_str
                                },
                                timeout=10
                            )

                            # PRIVACY CLEANUP: delete task related context variables
                            message = None
                            result_str = None
                            state = None
                            bid_tasks.discard(task_id)

        except Exception:
            pass
        time.sleep(1.0)

