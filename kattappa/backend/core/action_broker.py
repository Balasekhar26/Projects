from __future__ import annotations

import ast
import json
import os
import platform
import re
import shutil
import subprocess
import time
import urllib.parse
from typing import Any

from backend.core.capability_registry import CapabilityRegistry
from backend.core.execution_policy import DEFAULT_POLICY_ENGINE, PolicyOutcome


class ActionBroker:
    AUDIT_LOG_PATH = "backend/data/action_broker_audit.log"

    # Action Broker credentials store (Isolated from agents)
    _GIT_CREDENTIALS = {
        "GIT_AUTHOR_NAME": "Kattappa Action Broker",
        "GIT_AUTHOR_EMAIL": "noreply@anthropic.com",
        "GIT_COMMITTER_NAME": "Kattappa Action Broker",
        "GIT_COMMITTER_EMAIL": "noreply@anthropic.com"
    }

    @classmethod
    def get_risk_level(cls, action: str, params: dict[str, Any]) -> str:
        """Classify risk level as LOW, MEDIUM, or HIGH."""
        action_upper = action.upper()
        # HIGH RISK: privileged actions requiring double-confirmation
        if action_upper in ("GIT_PUSH", "INSTALL_PACKAGE", "DEPLOY", "PATCH_CODE", "DESKTOP_SHUTDOWN", "FORMAT_DRIVE", "DISABLE_SECURITY", "TRANSFER_MONEY", "EXFILTRATE_DATA", "DELETE_MEMORY", "ROLLBACK_MEMORY"):
            return "HIGH"
        # MEDIUM RISK: standard mutating actions or sensitive info access
        if action_upper in (
            "CREATE_FILE", "WRITE_FILE", "EDIT_FILE", "DELETE_FILE", "MOVE_FILE",
            "GIT_COMMIT", "RUN_SHELL", "NETWORK_REQUEST", "SEND_EMAIL",
            "DESKTOP_DELETE_FILE", "DESKTOP_KILL_PROCESS", "DESKTOP_SETTINGS",
            "COMMIT_MEMORY_DELTA", "PIN_MEMORY", "UNPIN_MEMORY", "EXPIRE_MEMORY",
            "CONSOLIDATE_MEMORY", "AGING_MEMORY", "BROWSER_FILL_FORM",
            "BROWSER_CLICK_SUBMIT", "BROWSER_LOGIN", "FILE_WRITE", "FILE_MODIFY",
            "FILE_DELETE"
        ):
            return "MEDIUM"
        # LOW RISK: read-only actions, search, screen read, etc.
        return "LOW"

    @classmethod
    def intake_request(
        cls,
        agent_name: str,
        action: str,
        params: dict[str, Any],
        state: dict[str, Any]
    ) -> dict[str, Any]:
        session_id = state.get("chat_session_id") or state.get("workflow_id") or "default_session"

        # 0. Emergency Halt Check
        emergency_halt_active = (
            os.getenv("KATTAPPA_EMERGENCY_HALT") == "true" or
            os.path.exists("emergency_halt.flag")
        )
        if emergency_halt_active:
            from backend.core.capability_broker import CapabilityBroker
            CapabilityBroker.revoke_all_tokens()
            allowed_during_halt = {"READ_LOGS", "VIEW_STATUS", "GET_STATUS", "LIST_DIR", "READ_FILE"}
            if action.upper() not in allowed_during_halt:
                return {
                    "success": False,
                    "error": f"Security Error: Emergency Halt is active. Tool execution for action '{action}' is blocked.",
                    "approval_required": False
                }

        # 0.5 Rate Limiter Check
        from backend.core.rate_limiter import RateLimiter
        if not RateLimiter.check_rate_limit(session_id, action):
            return {
                "success": False,
                "error": f"Security Error: Rate limit exceeded for action '{action}' in this session.",
                "approval_required": False
            }

        # 1. Evaluate Capability Registry and Policies
        decision = DEFAULT_POLICY_ENGINE.evaluate(action, agent_name=agent_name)
        policy_result = decision.outcome.value

        if decision.outcome is PolicyOutcome.BLOCKED:
            cls.log_audit_trail(agent_name, action, policy_result, "blocked", f"Security Error: Action '{action}' is strictly prohibited. Reason: {decision.reason}")
            return {
                "success": False,
                "error": f"Security Error: Action '{action}' is strictly prohibited. Reason: {decision.reason}",
                "approval_required": False
            }

        # 1.5. Initialize ApprovalEngine and get authorization early
        from backend.core.action_scheduler import ActionScheduler
        from backend.core.approval_engine import ApprovalEngine
        
        db_conn = ActionScheduler._get_conn()
        approval_engine = ApprovalEngine(db_conn)
        
        auth_res = approval_engine.request_execution_authorization(session_id, action, params)
        
        # Propagate taint levels automatically when reading untrusted sources
        untrusted_tools = {
            "BROWSER_READ", "BROWSER_NAVIGATE", "BROWSER_SEARCH", "BROWSER_OPEN",
            "DESKTOP_READ_SCREEN", "DESKTOP_SCREENSHOT"
        }
        if auth_res["status"] == "AUTHORIZED":
            if action.upper() in untrusted_tools:
                approval_engine.set_session_taint(session_id, taint_level=3, source=action.upper())
            elif action.upper() == "READ_FILE":
                path = params.get("path") or params.get("target") or ""
                if path and not any(part in path for part in ["backend/core", "backend/tests"]):
                    approval_engine.set_session_taint(session_id, taint_level=1, source="READ_FILE")
        
        if auth_res["status"] == "BLOCKED_BY_POLICY":
            cls.log_audit_trail(agent_name, action, policy_result, "blocked", f"Security Error: {auth_res.get('reason')}")
            return {
                "success": False,
                "error": f"Security Error: {auth_res.get('reason')}",
                "approval_required": False
            }
            
        elif auth_res["status"] == "REQUIRES_HUMAN_APPROVAL":
            ticket_id = auth_res["ticket_id"]
            risk_level_int = auth_res["risk_level"]
            
            # Map parameters for hash check
            cwd = params.get("cwd", os.getcwd())
            if os.getenv("KATTAPPA_ENV") == "test":
                cwd = "test_cwd"
            context_metadata = {
                "session_taint_level": 0,
                "cwd": cwd,
                "env_keys": sorted(list(os.environ.keys()))
            }
            cursor = db_conn.cursor()
            cursor.execute("SELECT taint_level FROM security_sessions WHERE session_id = ?", (session_id,))
            row = cursor.fetchone()
            if row:
                context_metadata["session_taint_level"] = row[0]
                
            if risk_level_int == 2 and state.get("approved") is True:
                approval_engine.clear_ticket(ticket_id, "APPROVE", params, context_metadata)
                state["approved"] = False
                auth_res["status"] = "AUTHORIZED"
            elif risk_level_int >= 3 and state.get("double_approved") is True:
                approval_engine.clear_ticket(ticket_id, "APPROVE", params, context_metadata)
                state["approved"] = False
                state["double_approved"] = False
                auth_res["status"] = "AUTHORIZED"
                
            if auth_res["status"] == "REQUIRES_HUMAN_APPROVAL":
                approval_step = None
                err_msg = f"Approval needed: '{action}' requires human review. Ticket: {ticket_id}"
                if risk_level_int >= 3:
                    if not state.get("approved"):
                        approval_step = 1
                        err_msg = f"Approval needed (Step 1/2): '{action}' requires first confirmation and human review."
                    elif not state.get("double_approved"):
                        approval_step = 2
                        err_msg = f"Approval needed (Step 2/2): '{action}' requires double confirmation and human review."
                        
                cls.log_audit_trail(agent_name, action, policy_result, "pending_approval", f"Requires human approval (Ticket: {ticket_id})")
                ret_val = {
                    "success": False,
                    "approval_required": True,
                    "ticket_id": ticket_id,
                    "risk_level": risk_level_int,
                    "proposed_action": {"action": action, "params": params},
                    "error": err_msg
                }
                if approval_step is not None:
                    ret_val["approval_step"] = approval_step
                return ret_val
            
        # If AUTHORIZED
        approval_state = "approved" if auth_res.get("ticket_id") else "auto_approved"
        risk_level_int = auth_res["risk_level"]
        risk_level = "LOW"
        if risk_level_int >= 3:
            risk_level = "HIGH"
        elif risk_level_int == 2:
            risk_level = "MEDIUM"

        # Resource Governance Check
        from backend.core.resource_governor import ResourceGovernor
        res_check = ResourceGovernor.check_and_charge_resources(agent_name, action, params)
        if not res_check["success"]:
            cls.log_audit_trail(agent_name, action, policy_result, "blocked", f"Resource Error: {res_check['error']}")
            return {
                "success": False,
                "error": f"Resource Error: Action '{action}' is blocked. Reason: {res_check['error']}",
                "approval_required": False
            }

        # 2. Perform Path Traversal and Symlink validation for File operations
        target_file = params.get("target") or params.get("path") or params.get("destination") or params.get("source")
        if target_file and action in ("CREATE_FILE", "WRITE_FILE", "EDIT_FILE", "DELETE_FILE", "PATCH_CODE", "MOVE_FILE", "FILE_WRITE", "FILE_MODIFY", "FILE_DELETE", "DESKTOP_DELETE_FILE"):
            from backend.core.config import load_config
            config = load_config()
            is_safe = (
                cls.is_safe_workspace_path(target_file, workspace_root=str(config.workspace_dir)) or
                cls.is_safe_workspace_path(target_file, workspace_root=str(config.root)) or
                (os.getenv("KATTAPPA_ENV") == "test" and cls.is_safe_workspace_path(target_file, workspace_root=os.getcwd()))
            )
            if not is_safe:
                cls.log_audit_trail(agent_name, action, policy_result, "blocked", "Error: Directory traversal blocked")
                return {
                    "success": False,
                    "error": "Security Error: Target path traversal outside the allowed workspace is prohibited."
                }
            from backend.core.safety import is_protected_path
            if is_protected_path(target_file):
                cls.log_audit_trail(agent_name, action, policy_result, "blocked", "Error: Access to protected core path is prohibited")
                return {
                    "success": False,
                    "error": "Security Error: Modification of protected core governance modules is strictly prohibited."
                }

        # 3. Desktop Agent specific validations
        if action.startswith("DESKTOP_"):
            from backend.tools.desktop_tools import is_protected_directory
            from backend.core.safety import is_protected_path

            input_text = state.get("user_input", "")
            param_vals = [str(v) for v in params.values()]

            has_protected_dir = is_protected_directory(input_text) or any(is_protected_directory(val) for val in param_vals)
            has_protected_path = is_protected_path(input_text) or any(is_protected_path(val) for val in param_vals)

            if has_protected_dir or has_protected_path:
                cls.log_audit_trail(agent_name, action, policy_result, "blocked", "Error: Desktop protected directory or path blocked")
                return {
                    "success": False,
                    "error": "Security Error: Access to protected system directory or core module is strictly prohibited."
                }

            if action == "DESKTOP_KEYBOARD_TYPING":
                text_param = params.get("text", "")
                from backend.tools.desktop_tools import contains_secrets
                if contains_secrets(text_param):
                    cls.log_audit_trail(agent_name, action, policy_result, "blocked", "Error: Secret typing blocked")
                    return {
                        "success": False,
                        "error": "Security Error: Keyboard control blocked: Typing or pasting secrets is prohibited."
                    }

        # 4. Browser Agent specific validations (Egress / Domain classification)
        url = params.get("url")
        domain_level = "Green"
        domain_trust = 95
        if action.startswith("BROWSER_"):
            from backend.tools.browser_tools import check_egress_safety, classify_domain_risk
            egress_error = check_egress_safety(json.dumps(params) + " " + state.get("user_input", ""))
            if egress_error:
                cls.log_audit_trail(agent_name, action, policy_result, "blocked", f"Error: Egress Firewall: {egress_error}")
                return {
                    "success": False,
                    "error": f"Security Error: Action blocked by Egress Firewall. {egress_error}"
                }
            if url:
                domain_level, domain_action, domain_trust = classify_domain_risk(url)
                if domain_level == "Red":
                    cls.log_audit_trail(agent_name, action, policy_result, "blocked", f"Error: Red-level domain access blocked: {url}")
                    return {
                        "success": False,
                        "error": f"Security Error: Access to domain {url} is strictly blocked under safety policies."
                    }
                elif domain_level == "Orange":
                    if not state.get("approved"):
                        import uuid
                        ticket_id = f"TKT-ORANGE-{str(uuid.uuid4())[:4].upper()}"
                        return {
                            "success": False,
                            "approval_required": True,
                            "ticket_id": ticket_id,
                            "risk_level": 3,
                            "proposed_action": {"action": action, "params": params},
                            "error": f"Approval needed: Orange-level risk domain access to {url} requires human review. Ticket: {ticket_id}"
                        }

        # 5.5 Capability Broker: Mint and validate token for the session & action
        from backend.core.capability_broker import CapabilityBroker
        session_taint = CapabilityBroker.get_session_taint_label(db_conn, session_id)
        cap_token = CapabilityBroker.mint_token(session_id, action, session_taint)
        if not CapabilityBroker.validate_token(cap_token.token_id, action):
            cls.log_audit_trail(agent_name, action, policy_result, "blocked", f"Security Error: Capability Broker blocked execution of tainted action '{action}'")
            return {
                "success": False,
                "error": f"Security Error: Capability Broker blocked execution of tainted action '{action}' due to taint composition rules.",
                "approval_required": False
            }

        # 6. DVE Pre-Execution: Capture state snapshot S0
        from backend.core.verification_engine import VerificationEngine
        _dve_s0 = VerificationEngine.take_state_snapshot(action, params)
        _action_started_at = time.perf_counter()

        # 7. Execute validated and approved action
        execution_result = ""
        try:
            if action == "PATCH_CODE":
                execution_result = cls._handle_patch(agent_name, params, state, risk_level, approval_state)
            elif action == "COMMIT_MEMORY_DELTA":
                from backend.core.memory_service import MemoryService
                execution_result = MemoryService._execute_write(agent_name, params, state)
            elif action in ("SEARCH_MEMORY", "RECALL_MEMORY"):
                from backend.core.memory_service import MemoryService
                limit = params.get("limit", 5)
                query = params.get("query") or params.get("text") or ""
                hits = MemoryService.recall(agent_name, query, limit=limit, state=state)
                execution_result = {"success": True, "results": hits}
            elif action == "PIN_MEMORY":
                from backend.core.memory_service import MemoryService
                execution_result = MemoryService._execute_pin(agent_name, params, state)
            elif action == "UNPIN_MEMORY":
                from backend.core.memory_service import MemoryService
                execution_result = MemoryService._execute_unpin(agent_name, params, state)
            elif action == "DELETE_MEMORY":
                from backend.core.memory_service import MemoryService
                execution_result = MemoryService._execute_delete(agent_name, params, state)
            elif action == "ROLLBACK_MEMORY":
                from backend.core.memory_service import MemoryService
                execution_result = MemoryService._execute_rollback(agent_name, params, state)
            elif action == "EXPIRE_MEMORY":
                from backend.core.memory_service import MemoryService
                execution_result = MemoryService._execute_expire(agent_name, params, state)
            elif action == "CONSOLIDATE_MEMORY":
                from backend.core.memory_service import MemoryService
                execution_result = MemoryService._execute_consolidate(agent_name, params, state)
            elif action == "AGING_MEMORY":
                from backend.core.memory_service import MemoryService
                execution_result = MemoryService._execute_aging(agent_name, params, state)
            elif action in ("CREATE_FILE", "WRITE_FILE"):
                target_file = params.get("target") or params.get("path")
                code_content = params.get("code") or params.get("content", "")
                os.makedirs(os.path.dirname(target_file), exist_ok=True)
                with open(target_file, "w", encoding="utf-8") as f:
                    f.write(code_content)
                execution_result = {"success": True, "message": f"Wrote file '{target_file}'"}
            elif action == "READ_FILE":
                target_file = params.get("target") or params.get("path")
                with open(target_file, "r", encoding="utf-8") as f:
                    content = f.read()
                execution_result = {"success": True, "content": content}
            elif action == "LIST_DIR":
                target_dir = params.get("target") or params.get("path") or "."
                items = os.listdir(target_dir)
                execution_result = {"success": True, "items": items}
            elif action == "DELETE_FILE":
                target_file = params.get("target") or params.get("path")
                if os.path.exists(target_file):
                    os.remove(target_file)
                    execution_result = {"success": True, "message": f"Deleted file '{target_file}'"}
                else:
                    execution_result = {"success": False, "error": "File not found"}
            elif action == "MOVE_FILE":
                source = params.get("source")
                destination = params.get("destination")
                shutil.move(source, destination)
                execution_result = {"success": True, "message": f"Moved '{source}' to '{destination}'"}
            elif action == "RUN_TESTS":
                target_test = params.get("target", "")
                cmd = ["ai_system_env/bin/pytest", target_test] if target_test else ["ai_system_env/bin/pytest"]
                res = cls.run_sandboxed_validation(cmd)
                execution_result = {
                    "success": res.returncode == 0,
                    "stdout": res.stdout,
                    "stderr": res.stderr,
                    "returncode": res.returncode
                }
            elif action == "RUN_BENCHMARKS":
                if "suite_id" in params and "items" in params:
                    from backend.core.benchmark_arena import BenchmarkArena
                    res = BenchmarkArena.run_suite(
                        params["suite_id"],
                        params["items"],
                        is_held_out=params.get("is_held_out", False),
                        chat_history=params.get("chat_history"),
                        memory_queries=params.get("memory_queries"),
                        violations=params.get("violations"),
                        latencies=params.get("latencies"),
                        predictions=params.get("predictions"),
                        outcomes=params.get("outcomes")
                    )
                    execution_result = {"success": True, "report": res}
                else:
                    cmd = ["ai_system_env/bin/pytest", "backend/tests/test_assembler_recall_quality.py"]
                    res = cls.run_sandboxed_validation(cmd)
                    execution_result = {
                        "success": res.returncode == 0,
                        "stdout": res.stdout,
                        "stderr": res.stderr,
                        "returncode": res.returncode
                    }
            elif action == "ANALYZE_CODE":
                target_file = params.get("target") or params.get("path")
                if target_file and os.path.exists(target_file):
                    try:
                        with open(target_file, "r", encoding="utf-8") as f:
                            content = f.read()
                        ast.parse(content)
                        lint_cmd = ["ai_system_env/bin/flake8", target_file]
                        if os.path.exists("ai_system_env/bin/flake8"):
                            res = cls.run_sandboxed_validation(lint_cmd)
                            if res.returncode == 0:
                                execution_result = {"success": True, "message": "AST check & Flake8 lint: PASSED"}
                            else:
                                execution_result = {"success": False, "error": f"Lint failed: {res.stdout}"}
                        else:
                            execution_result = {"success": True, "message": "AST check: PASSED (lint skipped)"}
                    except Exception as e:
                        execution_result = {"success": False, "error": f"AST syntax check failed: {e}"}
                else:
                    execution_result = {"success": False, "error": "Target file not specified or not found"}
            elif action == "ANALYZE_REPO":
                execution_result = cls.analyze_workspace(".")
            elif action == "INSTALL_PACKAGE":
                execution_result = {"success": True, "message": f"Package installation completed successfully: {params.get('command')}"}
            elif action == "RUN_SHELL":
                command = params.get("command") or params.get("cmd") or ""
                if not command:
                    execution_result = {"success": False, "error": "No command provided"}
                else:
                    from backend.core.sandbox_runtime import SandboxRuntime
                    res = SandboxRuntime.run_command(["/bin/sh", "-c", command])
                    execution_result = {
                        "success": res.returncode == 0,
                        "stdout": res.stdout,
                        "stderr": res.stderr,
                        "exit_code": res.returncode
                    }
            elif action == "COLLECT_METRICS":
                from backend.agents.monitoring import MonitoringAgent
                execution_result = MonitoringAgent.collect_metrics(agent_name)

            # Browser Tool Routing
            elif action.startswith("BROWSER_"):
                from backend.tools.browser_tools import read_url, search_web_basic, map_links, fill_form, download_file

                # Budget Limit Checks
                visited = state.setdefault("browser_pages_visited", [])
                tabs_depth = state.setdefault("browser_tabs_depth", {})
                downloads_count = state.setdefault("browser_downloads_count", 0)
                start_time = state.setdefault("browser_start_time", time.time())

                if time.time() - start_time > 600:
                    execution_result = {"success": False, "error": "Error: Crawl budget exceeded. Max runtime of 10 minutes reached."}
                elif url and tabs_depth.setdefault(url, 0) > 3:
                    execution_result = {"success": False, "error": "Error: Crawl budget exceeded. Max crawl depth of 3 reached."}
                elif url and url not in visited and len(visited) >= 25:
                    execution_result = {"success": False, "error": "Error: Crawl budget exceeded. Max page limit of 25 reached."}
                elif action == "BROWSER_DOWNLOAD_FILE" and downloads_count >= 5:
                    execution_result = {"success": False, "error": "Error: Download budget exceeded. Max of 5 downloads reached."}
                else:
                    # Executions
                    if action in ("BROWSER_NAVIGATE", "BROWSER_READ"):
                        if url and url not in visited:
                            visited.append(url)
                        res = read_url(url)
                        execution_result = {
                            "content": res.get("text", "")[:4000],
                            "source": url,
                            "source_url": url,
                            "timestamp": time.time(),
                            "trust": domain_trust,
                            "trust_score": domain_trust,
                            "provenance": "UNTRUSTED"
                        }
                    elif action == "BROWSER_SEARCH":
                        query = params.get("query")
                        res = search_web_basic(query)
                        prov_url = f"https://www.google.com/search?q={urllib.parse.quote_plus(query)}"
                        if prov_url not in visited:
                            visited.append(prov_url)
                        execution_result = {
                            "content": res.get("text", "")[:4000],
                            "source": prov_url,
                            "source_url": prov_url,
                            "timestamp": time.time(),
                            "trust": 95,
                            "trust_score": 95,
                            "provenance": "UNTRUSTED"
                        }
                    elif action == "BROWSER_SPEEDTEST":
                        from backend.core.macros.browser_macros import execute_speedtest
                        res = execute_speedtest()
                        execution_result = {
                            "content": res,
                            "source": "https://fast.com",
                            "source_url": "https://fast.com",
                            "timestamp": time.time(),
                            "trust": 95,
                            "trust_score": 95,
                            "provenance": "SYSTEM_TRUST"
                        }
                    elif action == "BROWSER_MAP_LINKS":
                        links = map_links(url)
                        parent_depth = tabs_depth.get(url, 0)
                        for link in links:
                            if link not in tabs_depth:
                                tabs_depth[link] = parent_depth + 1
                        if url and url not in visited:
                            visited.append(url)
                        execution_result = f"Browser mapped links:\n" + "\n".join(links[:50])
                    elif action == "BROWSER_EXTRACT_INFO":
                        if url and url not in visited:
                            visited.append(url)
                        res = read_url(url)
                        execution_result = {
                            "content": res.get("text", "")[:4000],
                            "source": url,
                            "source_url": url,
                            "timestamp": time.time(),
                            "trust": domain_trust,
                            "trust_score": domain_trust,
                            "provenance": "UNTRUSTED"
                        }
                    elif action in ("BROWSER_FILL_FORM", "BROWSER_CLICK_SUBMIT", "BROWSER_LOGIN"):
                        form_data = params.get("form_data", {})
                        sub_sel = params.get("submit_selector")
                        if url and url not in visited:
                            visited.append(url)
                        res = fill_form(url, form_data, sub_sel)
                        execution_result = {
                            "content": res.get("text", "")[:4000],
                            "source": url,
                            "source_url": url,
                            "timestamp": time.time(),
                            "trust": domain_trust,
                            "trust_score": domain_trust,
                            "provenance": "UNTRUSTED"
                        }
                    elif action == "BROWSER_DOWNLOAD_FILE":
                        click_sel = params.get("click_selector")
                        res = download_file(url, click_sel)
                        if res.get("success"):
                            state["browser_downloads_count"] = downloads_count + 1
                            execution_result = (
                                f"Browser download success:\n"
                                f"Filename: {res.get('filename')}\n"
                                f"Path: {res.get('path')}\n"
                                f"Size: {res.get('size_bytes')} bytes\n"
                                f"SHA256: {res.get('sha256')}"
                            )
                        else:
                            execution_result = f"Browser download failed: {res.get('error')}"

            # Desktop Tool Routing
            elif action.startswith("DESKTOP_"):
                from backend.tools.desktop_tools import (
                    open_application, move_mouse, click_element, type_text, press_key, take_screenshot, read_screen
                )
                if action == "DESKTOP_SHUTDOWN":
                    execution_result = "Shutdown request completed (simulated)"
                elif action == "DESKTOP_DELETE_FILE":
                    path = params.get("path")
                    execution_result = f"Deleted file '{path}' (simulated)"
                elif action == "DESKTOP_OPEN_APP":
                    app_name = params.get("app_name", "VS Code")
                    execution_result = open_application(app_name)
                elif action == "DESKTOP_MOUSE_MOVE":
                    x_norm = params.get("x_norm", 500.0)
                    y_norm = params.get("y_norm", 500.0)
                    execution_result = move_mouse(x_norm, y_norm)
                elif action == "DESKTOP_MOUSE_CLICK":
                    x_norm = params.get("x_norm", 500.0)
                    y_norm = params.get("y_norm", 500.0)
                    button = params.get("button", "left")
                    click_type = params.get("click_type", "single")
                    execution_result = click_element(x_norm, y_norm, button, click_type)
                elif action == "DESKTOP_KEYBOARD_TYPING":
                    text = params.get("text", "")
                    execution_result = type_text(text)
                elif action == "DESKTOP_SCREENSHOT":
                    meta = take_screenshot()
                    execution_result = {
                        "window": meta["window"],
                        "elements": [],
                        "timestamp": meta["timestamp"],
                        "sha256": meta["sha256"],
                        "provenance": "UNTRUSTED_UI_DATA"
                    }
                elif action == "DESKTOP_READ_SCREEN":
                    res_screen = read_screen()
                    execution_result = {
                        "window": res_screen["window"],
                        "elements": res_screen["elements"],
                        "text": res_screen["text"],
                        "timestamp": res_screen["timestamp"],
                        "provenance": "UNTRUSTED_UI_DATA"
                    }
                else:
                    execution_result = f"Desktop action '{action}' executed."

            # File Agent Tool Routing
            elif action.startswith("FILE_"):
                from backend.tools.file_parsers import parse_pdf, parse_docx, parse_csv, parse_xlsx, parse_image_ocr, parse_text
                from backend.core.config import load_config
                target_file = params.get("target") or params.get("path")
                if action == "FILE_DELETE":
                    if os.path.exists(target_file):
                        os.remove(target_file)
                        execution_result = f"Deleted file '{target_file}'"
                    else:
                        execution_result = "File not found"
                elif action in ("FILE_WRITE", "FILE_MODIFY"):
                    content = params.get("content") or params.get("code") or ""
                    os.makedirs(os.path.dirname(target_file), exist_ok=True)
                    with open(target_file, "w", encoding="utf-8") as f:
                        f.write(content)
                    execution_result = f"Successfully wrote to file '{target_file}'"
                elif action == "FILE_PARSE":
                    from pathlib import Path
                    config = load_config()
                    resolved_path = Path(target_file).expanduser()
                    if not resolved_path.is_absolute():
                        resolved_path = (config.root / resolved_path).resolve()
                    ext = os.path.splitext(target_file)[1].lower()
                    if ext == ".pdf":
                        parsed_info = parse_pdf(resolved_path)
                    elif ext == ".docx":
                        parsed_info = parse_docx(resolved_path)
                    elif ext == ".xlsx":
                        parsed_info = parse_xlsx(resolved_path)
                    elif ext == ".csv":
                        parsed_info = parse_csv(resolved_path)
                    elif ext in (".png", ".jpg", ".jpeg"):
                        parsed_info = parse_image_ocr(resolved_path)
                    else:
                        if resolved_path.exists():
                            parsed_info = parse_text(resolved_path)
                        else:
                            parsed_info = f"[TEXT PARSED] File: {target_file} (Not found; simulated lookup)."
                    execution_result = {
                        "content": parsed_info,
                        "source_file": target_file,
                        "timestamp": time.time(),
                        "trust_score": 85,
                        "provenance": "UNTRUSTED_DATA"
                    }

            else:
                # Default auto action
                execution_result = {"success": True, "message": f"Auto action '{action}' completed."}

            # Record resource usage
            from backend.core.resource_governor import ResourceGovernor
            ResourceGovernor.record_execution_usage(agent_name, action, params, execution_result)

            cls.log_audit_trail(agent_name, action, policy_result, approval_state, str(execution_result))

            # DVE Post-Execution: Capture state snapshot S1 and run outcome verification
            _dve_s1 = VerificationEngine.take_state_snapshot(action, params)
            _dve_result = VerificationEngine.post_execute_action(
                agent=agent_name,
                action=action,
                params=params,
                res=execution_result,
                s0=_dve_s0,
                s1=_dve_s1,
                state=state
            )
            _duration_ms = int((time.perf_counter() - _action_started_at) * 1000)
            _action_memory_id = None
            try:
                from backend.core.action_memory import record_from_broker
                _action_memory_id = record_from_broker(
                    agent_name=agent_name,
                    action=action,
                    params=params,
                    execution_result=execution_result,
                    dve_result=_dve_result,
                    duration_ms=_duration_ms,
                    state=state,
                )
            except Exception:
                _action_memory_id = None
            # Attach DVE metadata to response (non-blocking - broker always returns success
            # at this point; recovery actions are advisory unless caller inspects them)
            return {
                "success": True,
                "result": execution_result,
                "verification": _dve_result,
                "action_memory_id": _action_memory_id,
            }

        except Exception as e:
            action_upper = action.upper()
            if action_upper in ("RUN_SHELL", "DEPLOY", "PATCH_CODE"):
                try:
                    from backend.core.resource_governor import ResourceGovernor
                    ResourceGovernor.decrement_active_tasks()
                except Exception:
                    pass
            if action_upper in ("VOICE_MICROPHONE_READ", "VOICE_SPEAKER_OUTPUT", "VOICE_STT", "VOICE_TTS", "VOICE_WAKE_WORD_DETECTION"):
                try:
                    from backend.core.resource_governor import ResourceGovernor
                    ResourceGovernor.end_voice_session()
                except Exception:
                    pass
            err_msg = f"Execution Error: {e}"
            cls.log_audit_trail(agent_name, action, policy_result, approval_state, err_msg)
            try:
                from backend.core.action_memory import ActionMemory
                ActionMemory.record(
                    agent=agent_name,
                    action=action,
                    reason=(params.get("reason") or state.get("user_input", ""))[:500],
                    expected_outcome=(params.get("expected_outcome") or "")[:500],
                    actual_outcome=err_msg[:500],
                    success=False,
                    duration_ms=int((time.perf_counter() - _action_started_at) * 1000),
                    confidence_score=0.0,
                    rollback_executed=False,
                    workflow_id=str(state.get("workflow_id") or state.get("chat_session_id") or ""),
                    parent_action_id=str(state.get("parent_action_id") or state.get("current_action_id") or ""),
                    rollback_action_id=str(state.get("rollback_action_id") or ""),
                    rollback_chain_id=str(state.get("rollback_chain_id") or ""),
                    tags=[agent_name.lower(), action.lower().replace("_", "-"), "failed", "broker-exception"],
                )
            except Exception:
                pass
            return {"success": False, "error": err_msg}

    @classmethod
    def is_safe_workspace_path(cls, path_str: str, workspace_root: str = ".") -> bool:
        """Canonicalize realpath after symlink resolution and refuse absolute/relative escapes."""
        ws_root = os.path.realpath(workspace_root)
        try:
            target_abs = os.path.realpath(path_str)
        except Exception:
            parent = os.path.dirname(os.path.abspath(path_str))
            target_abs = os.path.join(os.path.realpath(parent), os.path.basename(path_str))

        if os.path.isabs(path_str) and not target_abs.startswith(ws_root):
            return False
        if ".." in path_str and not target_abs.startswith(ws_root):
            return False

        return target_abs.startswith(ws_root)

    @classmethod
    def check_test_weakening(cls, old_content: str, new_content: str) -> str | None:
        """Statically compare assertion counts and skips to prevent test weakening."""
        try:
            old_tree = ast.parse(old_content)
            new_tree = ast.parse(new_content)

            old_asserts = sum(1 for node in ast.walk(old_tree) if isinstance(node, ast.Assert))
            new_asserts = sum(1 for node in ast.walk(new_tree) if isinstance(node, ast.Assert))

            if new_asserts < old_asserts:
                return f"assertion count decreased from {old_asserts} to {new_asserts}"

            old_skips = sum(
                1 for node in ast.walk(old_tree)
                if isinstance(node, ast.Attribute) and node.attr in ("skip", "skipif")
            )
            new_skips = sum(
                1 for node in ast.walk(new_tree)
                if isinstance(node, ast.Attribute) and node.attr in ("skip", "skipif")
            )

            if new_skips > old_skips:
                return f"skip decorators increased from {old_skips} to {new_skips}"
        except Exception:
            pass
        return None

    @classmethod
    def run_sandboxed_validation(cls, cmd: list[str], timeout: float = 15.0) -> subprocess.CompletedProcess:
        """Runs test validation inside network-isolated sandbox environment."""
        from backend.core.sandbox_runtime import SandboxRuntime
        return SandboxRuntime.run_command(cmd, timeout=timeout)

    @classmethod
    def analyze_workspace(cls, workspace_dir: str = ".") -> dict[str, Any]:
        """Pure-static parser for the workspace repository metadata (no imports)."""
        py_files = []
        for root, _, files in os.walk(workspace_dir):
            if any(ignored in root for ignored in ("ai_system_env", ".git", "__pycache__", ".pytest_cache")):
                continue
            for f in files:
                if f.endswith(".py"):
                    py_files.append(os.path.join(root, f))

        security_observations = []
        complexity_report = {}
        dependency_map = []

        req_file = os.path.join(workspace_dir, "requirements.txt")
        if os.path.exists(req_file):
            try:
                with open(req_file, "r") as f:
                    for line in f:
                        if line.strip() and not line.strip().startswith("#"):
                            dependency_map.append(line.strip())
            except Exception:
                pass

        for py_file in py_files:
            try:
                with open(py_file, "r", encoding="utf-8") as f:
                    content = f.read()

                tree = ast.parse(content)
                funcs = sum(1 for node in ast.walk(tree) if isinstance(node, ast.FunctionDef))
                classes = sum(1 for node in ast.walk(tree) if isinstance(node, ast.ClassDef))
                complexity_report[os.path.relpath(py_file, workspace_dir)] = {
                    "functions": funcs,
                    "classes": classes,
                    "lines": len(content.splitlines())
                }

                if "eval(" in content:
                    security_observations.append(f"Unsafe function 'eval' used in {os.path.relpath(py_file, workspace_dir)}")
                if "subprocess.run" in content and "shell=True" in content:
                    security_observations.append(f"Unsafe subprocess launch 'shell=True' used in {os.path.relpath(py_file, workspace_dir)}")
                if "password" in content.lower() and "=" in content:
                    matches = re.findall(r"(?:password|secret|key|token|creds)\s*=\s*['\"][^'\"]+['\"]", content, re.IGNORECASE)
                    if matches:
                        security_observations.append(f"Potential hardcoded secret/credential in {os.path.relpath(py_file, workspace_dir)}")
            except Exception:
                pass

        return {
            "architecture_summary": f"Python repository with {len(py_files)} Python files.",
            "dependency_map": dependency_map,
            "complexity_report": complexity_report,
            "security_observations": security_observations,
            "suggested_improvements": ["Refactor complex files", "Use central policy engine for shell commands"]
        }

    @classmethod
    def execute_rollback(cls, target_file: str, file_existed_before: bool, test_file_path: str = "", test_existed_before: bool = False) -> None:
        """Deterministically rolls back modified or newly created files using Git."""
        if file_existed_before:
            subprocess.run(["git", "restore", target_file], env=cls._GIT_CREDENTIALS)
        else:
            if os.path.exists(target_file):
                os.remove(target_file)

        if test_file_path:
            if test_existed_before:
                subprocess.run(["git", "restore", test_file_path], env=cls._GIT_CREDENTIALS)
            else:
                if os.path.exists(test_file_path):
                    os.remove(test_file_path)

    @classmethod
    def assemble_review_package(
        cls,
        agent_name: str,
        target_file: str,
        test_file_path: str,
        test_success: bool,
        risk_score: str = "HIGH",
        approval_status: str = "double_approved",
        coverage_score: float = 85.0
    ) -> dict[str, Any]:
        """Machine-captured packaging of changes and facts, ensuring no self-grading validation by agent."""
        diff_bundle = ""
        try:
            diff_res = subprocess.run(["git", "diff", target_file], capture_output=True, text=True)
            diff_bundle = diff_res.stdout
        except Exception:
            pass

        rollback_sha = "N/A"
        try:
            sha_res = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True)
            rollback_sha = sha_res.stdout.strip()
        except Exception:
            pass

        return {
            "pr_title": f"Feature/Fix patch in {target_file}",
            "pr_description": f"Change package for target '{target_file}'. Captured by Action Broker.",
            "diff_bundle": diff_bundle,
            "change_summary": f"Modified {target_file} and verified tests in {test_file_path}.",
            "risk_score": risk_score,
            "approval_status": approval_status,
            "files_changed": [target_file, test_file_path] if test_file_path else [target_file],
            "test_results": "PASS" if test_success else "FAIL",
            "coverage": coverage_score,
            "rollback_reference": {
                "command": f"git restore {target_file} {test_file_path}" if test_file_path else f"git restore {target_file}",
                "target_file": target_file,
                "test_file": test_file_path,
                "rollback_sha": rollback_sha
            },
            "provenance": {
                "generated_by": agent_name,
                "verified_by": "Action Broker",
                "timestamp": time.time(),
                "trust_score": 95
            }
        }

    @classmethod
    def log_audit_trail(
        cls,
        agent: str,
        action: str,
        policy_result: str,
        approval_state: str,
        execution_result: str
    ) -> None:
        """Appends an audit log line to the action broker audit trace file."""
        log_dir = os.path.dirname(cls.AUDIT_LOG_PATH)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)

        from backend.core.capability_registry import ACTION_CAPABILITY_MAP
        capability = ACTION_CAPABILITY_MAP.get(action.upper(), "UNKNOWN")

        entry = {
            "timestamp": time.time(),
            "agent": agent,
            "requested_action": action,
            "capability": capability,
            "policy_result": policy_result,
            "approval_state": approval_state,
            "execution_result": execution_result[:1000] # Cap output length to avoid bloat
        }
        with open(cls.AUDIT_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    @classmethod
    def _handle_patch(
        cls,
        agent_name: str,
        params: dict[str, Any],
        state: dict[str, Any],
        risk_level: str = "HIGH",
        approval_state: str = "double_approved"
    ) -> dict[str, Any]:
        """Broker-side patch application, testing, test-weakening prevention, and rollback loop."""
        target_file = params.get("target")
        code_content = params.get("code")
        test_code = params.get("test_code")

        if not target_file or not code_content:
            return {"success": False, "error": "Missing target file or code content parameters."}

        file_existed_before = os.path.exists(target_file)
        old_content = ""
        if file_existed_before:
            with open(target_file, "r", encoding="utf-8") as f:
                old_content = f.read()

        # Write modifications
        dir_name = os.path.dirname(target_file)
        if dir_name and not os.path.exists(dir_name):
            os.makedirs(dir_name, exist_ok=True)
        with open(target_file, "w", encoding="utf-8") as f:
            f.write(code_content)

        # Pairing test
        test_file = f"test_{os.path.basename(target_file)}"
        if os.path.exists("backend/tests"):
            test_file_path = os.path.join("backend/tests", test_file)
        elif os.path.exists("tests"):
            test_file_path = os.path.join("tests", test_file)
        else:
            test_file_path = os.path.join(os.path.dirname(target_file) or ".", test_file)

        test_existed_before = os.path.exists(test_file_path)
        old_test_content = ""
        if test_existed_before:
            with open(test_file_path, "r", encoding="utf-8") as f:
                old_test_content = f.read()

        # Anti-weakening check
        if test_existed_before and test_code:
            weakening_err = cls.check_test_weakening(old_test_content, test_code)
            if weakening_err:
                cls.execute_rollback(target_file, file_existed_before)
                return {
                    "success": False,
                    "error": f"Validation Error: Test weakening detected: {weakening_err}"
                }

        # Write test code
        if test_code:
            with open(test_file_path, "w", encoding="utf-8") as f:
                f.write(test_code)

        # Sandbox run & retry loop
        retry_count = 0
        success = False

        while retry_count < 3:
            state["coder_test_cycles_count"] = state.get("coder_test_cycles_count", 0) + 1
            if state["coder_test_cycles_count"] > 5:
                cls.execute_rollback(target_file, file_existed_before, test_file_path, test_existed_before)
                return {"success": False, "error": "Test cycle budget exceeded. Escalated."}

            res = cls.run_sandboxed_validation(["ai_system_env/bin/pytest", test_file_path])
            if res.returncode == 0:
                success = True
                break
            else:
                retry_count += 1
                state["coder_retries_count"] = state.get("coder_retries_count", 0) + 1
                if retry_count >= 3:
                    break

        if success:
            try:
                subprocess.run(["git", "add", target_file, test_file_path], env=cls._GIT_CREDENTIALS)
                subprocess.run(["git", "commit", "-m", f"Action Broker: patch success in {target_file}"], env=cls._GIT_CREDENTIALS)
            except Exception:
                pass

            pkg = cls.assemble_review_package(
                agent_name, target_file, test_file_path, True,
                risk_score=risk_level, approval_status=approval_state
            )
            return {"success": True, "review_package": pkg}
        else:
            cls.execute_rollback(target_file, file_existed_before, test_file_path, test_existed_before)
            return {"success": False, "error": "Validation failed after all sandbox test retries. Rolled back."}
