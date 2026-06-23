from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any

from backend.core.memory import memory
from backend.core.config import runtime_data_root
from backend.core.execution_policy import DEFAULT_POLICY_ENGINE, ActionPolicy, PolicyOutcome
from backend.tools.desktop_tools import (
    open_application,
    move_mouse,
    click_element,
    type_text,
    press_key,
    hotkey,
    take_screenshot,
    read_screen,
    get_active_window,
    list_open_windows,
    is_protected_directory,
    contains_secrets,
    is_ui_protected,
    _log_desktop_audit
)
from backend.tools.screen_tools import read_screen_snapshot


def classify_desktop_action(user_input: str) -> tuple[str, dict[str, Any]]:
    lower = user_input.lower()
    
    # 1. Destructive/Shutdown checks
    if "shutdown" in lower:
        return "DESKTOP_SHUTDOWN", {}
    if "delete" in lower or "remove file" in lower:
        path = None
        for word in user_input.split():
            if "." in word or "/" in word or "\\" in word:
                path = word.strip(".,;:\"'")
                break
        return "DESKTOP_DELETE_FILE", {"path": path or "unknown"}
    if "settings" in lower or "system preferences" in lower:
        return "DESKTOP_SETTINGS", {}
    if "kill" in lower:
        return "DESKTOP_KILL_PROCESS", {}
    if "close" in lower:
        return "DESKTOP_CLOSE_APP", {}
        
    # 2. Basic capabilities
    if "open" in lower:
        app_name = "VS Code"
        if "chrome" in lower:
            app_name = "Chrome"
        elif "terminal" in lower:
            app_name = "Terminal"
        elif "docker" in lower:
            app_name = "Docker Desktop"
        elif "keychain" in lower:
            app_name = "Keychain"
        else:
            words = user_input.split()
            try:
                open_idx = words.index(next(w for w in words if w.lower() == "open"))
                if open_idx + 1 < len(words):
                    app_name = " ".join(words[open_idx + 1:])
            except Exception:
                pass
        return "DESKTOP_OPEN_APP", {"app_name": app_name}
        
    if "move" in lower and "mouse" in lower:
        x_norm, y_norm = 500.0, 500.0
        coords = [float(s) for s in re.findall(r"\d+", user_input)]
        if len(coords) >= 2:
            x_norm, y_norm = coords[0], coords[1]
        return "DESKTOP_MOUSE_MOVE", {"x_norm": x_norm, "y_norm": y_norm}
        
    if "click" in lower:
        x_norm, y_norm = 500.0, 500.0
        coords = [float(s) for s in re.findall(r"\d+", user_input)]
        if len(coords) >= 2:
            x_norm, y_norm = coords[0], coords[1]
        click_type = "double" if "double" in lower else "single"
        button = "right" if "right" in lower else "left"
        return "DESKTOP_MOUSE_CLICK", {"x_norm": x_norm, "y_norm": y_norm, "button": button, "click_type": click_type}
        
    if "type" in lower:
        text = "test_input"
        quoted = re.findall(r"['\"](.*?)['\"]", user_input)
        if quoted:
            text = quoted[0]
        else:
            words = user_input.split()
            try:
                type_idx = words.index(next(w for w in words if w.lower() == "type"))
                if type_idx + 1 < len(words):
                    text = " ".join(words[type_idx + 1:])
            except Exception:
                pass
        return "DESKTOP_KEYBOARD_TYPING", {"text": text}
        
    if "screenshot" in lower:
        return "DESKTOP_SCREENSHOT", {}
        
    return "DESKTOP_READ_SCREEN", {}


def desktop_node(state: dict[str, Any]) -> dict[str, Any]:
    user_input = state["user_input"]
    logs = state.setdefault("logs", [])
    
    # Guidance / teach mode / observation path
    from backend.core.operator import detect_execution_path, build_operator_plan
    
    exec_path = detect_execution_path(user_input)
    is_explicit_screenshot = "take screenshot" in user_input.lower() or "capture" in user_input.lower() or user_input.lower().strip() == "screenshot"
    if exec_path in ("human_guided_step", "screen_observation") and not is_explicit_screenshot:
        screen_snapshot = read_screen_snapshot()
        screen_text = str(screen_snapshot.get("text", ""))
        if "OCR failed" in screen_text or screen_snapshot.get("error"):
            screen_text = ""
            
        operator_plan = build_operator_plan(
            user_input,
            state.get("selected_agent"),
            state.get("memory_context"),
            screen_text=screen_text,
            screen_snapshot=screen_snapshot,
        )
        state["operator_plan"] = operator_plan
        
        guidance = operator_plan.get("visual_guidance", {})
        guidance_text = ""
        if guidance.get("enabled"):
            guidance_text = (
                "\n\nVisual one-step guidance:\n"
                f"{guidance.get('instruction')}\n"
                f"{guidance.get('safety_note')}"
            )
            
        state["result"] = (
            f"Desktop {operator_plan['mode']} mode. I will guide you without controlling the mouse or keyboard.\n\n"
            "Current screen text:\n\n"
            + screen_text
            + guidance_text
        )
        state["approval_required"] = False
        logs.append("desktop: guide generated")
        return state

    
    # 1. Classify desktop action
    action, params = classify_desktop_action(user_input)
    logs.append(f"desktop: classified action as {action} with params {params}")
    
    # Delegate to Action Broker
    from backend.core.action_broker import ActionBroker
    broker_res = ActionBroker.intake_request("desktop", action, params, state)
    
    if broker_res.get("approval_required"):
        state["approval_required"] = True
        state["proposed_action"] = broker_res.get("proposed_action")
        state["result"] = broker_res.get("error")
        return state
        
    if not broker_res.get("success"):
        state["approval_required"] = False
        state["result"] = broker_res.get("error")
        error_str = str(broker_res.get("error")).lower()
        if "security" in error_str or "blocked" in error_str:
            logs.append(f"desktop: blocked action {action} due to safety boundary")
        return state
        
    # Success
    state["approval_required"] = False
    res = broker_res.get("result")
    if isinstance(res, dict) and "provenance" in res:
        state["provenance_data"] = res
        state["result"] = json.dumps(res, indent=2)
    else:
        state["result"] = str(res)
        
    # Simulated execution check for test environment
    if (os.environ.get("KATTAPPA_ENV") == "test" 
            and action in ("DESKTOP_OPEN_APP", "DESKTOP_MOUSE_MOVE", "DESKTOP_MOUSE_CLICK", "DESKTOP_KEYBOARD_TYPING", "DESKTOP_DELETE_FILE", "DESKTOP_SHUTDOWN")
            and not state["result"].startswith("Error") 
            and not state["result"].startswith("Failed")):
        state["result"] = f"Simulated desktop action successfully executed: {state['result']}"
        logs.append("desktop: simulated action executed successfully")
        
    return state

