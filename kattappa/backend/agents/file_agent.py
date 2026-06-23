from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from backend.core.config import load_config, runtime_data_root
from backend.core.safety import is_protected_path
from backend.core.execution_policy import DEFAULT_POLICY_ENGINE, ActionPolicy, PolicyOutcome
from backend.tools.file_parsers import (
    parse_pdf,
    parse_docx,
    parse_csv,
    parse_xlsx,
    parse_image_ocr,
    parse_text
)

# Register File Agent policies in the central Execution Policy Engine
DEFAULT_POLICY_ENGINE.register(
    ActionPolicy("FILE_PARSE", auto_execute=True, require_human=False, description="Read and parse workspace document")
)
DEFAULT_POLICY_ENGINE.register(
    ActionPolicy("FILE_WRITE", auto_execute=False, require_human=True, description="Human approved file creation or overwrite")
)
DEFAULT_POLICY_ENGINE.register(
    ActionPolicy("FILE_MODIFY", auto_execute=False, require_human=True, description="Human approved file modification")
)
DEFAULT_POLICY_ENGINE.register(
    ActionPolicy("FILE_DELETE", auto_execute=False, require_human=True, description="Human approved file deletion")
)


def is_safe_file_path(path_str: str) -> bool:
    try:
        config = load_config()
        path = Path(path_str).expanduser()
        if not path.is_absolute():
            path = (config.root / path).resolve()
        else:
            path = path.resolve()
            
        # Sandbox boundary: must stay within config.root or runtime_data_root
        root_str = str(config.root.resolve())
        runtime_root_str = str(runtime_data_root().resolve())
        path_str_resolved = str(path)
        
        starts_with_root = path_str_resolved.startswith(root_str)
        starts_with_runtime = path_str_resolved.startswith(runtime_root_str)
        
        if not (starts_with_root or starts_with_runtime):
            return False
            
        # Safety boundary: block access to core governance/protected files
        if is_protected_path(path_str_resolved):
            return False
            
        return True
    except Exception:
        return False


def file_node(state: dict[str, Any]) -> dict[str, Any]:
    user_input = state["user_input"]
    lower_input = user_input.lower()
    logs = state.setdefault("logs", [])
    
    # 1. Action Classification
    action = "FILE_PARSE"
    if any(word in lower_input for word in ("delete", "remove", "erase")):
        action = "FILE_DELETE"
    elif any(word in lower_input for word in ("write", "edit", "change", "modify", "save", "patch")):
        action = "FILE_MODIFY"
        
    logs.append(f"file: classified action as {action}")
    
    # Check for target files in the request
    target_file = None
    for word in user_input.split():
        cleaned_word = word.strip(".,;:\"'")
        if "/" in cleaned_word or "\\" in cleaned_word or any(cleaned_word.endswith(ext) for ext in (".pdf", ".docx", ".xlsx", ".pptx", ".png", ".jpg", ".jpeg", ".txt", ".md", ".csv")):
            target_file = cleaned_word
            break

    if target_file and not is_safe_file_path(target_file):
        logs.append(f"file: blocked access to unsafe path {target_file}")
        state["result"] = f"Access to {target_file} is strictly prohibited under safety policies."
        state["approval_required"] = False
        return state

    if not target_file and _delete_without_target(user_input):
        state["result"] = "I need the exact delete target first: file, folder, chat item, or memory item."
        logs.append("file: delete target missing")
        return state

    if target_file:
        broker_params = {"target": target_file}
        if action in ("FILE_MODIFY", "FILE_WRITE"):
            broker_params["content"] = "test content"
            
        # Delegate to Action Broker
        from backend.core.action_broker import ActionBroker
        broker_res = ActionBroker.intake_request("file", action, broker_params, state)
        
        if broker_res.get("approval_required"):
            state["approval_required"] = True
            state["proposed_action"] = broker_res.get("proposed_action")
            state["result"] = broker_res.get("error")
            return state
            
        if not broker_res.get("success"):
            state["approval_required"] = False
            state["result"] = broker_res.get("error")
            return state
            
        # Success
        state["approval_required"] = False
        res = broker_res.get("result")
        if isinstance(res, dict) and "provenance" in res:
            state["provenance_data"] = res
            state["result"] = json.dumps(res, indent=2)
        else:
            state["result"] = str(res)
        return state

    # Fallback plan
    state["result"] = (
        "File Agent plan: No target file detected. Please specify a file with extension "
        "(e.g., .pdf, .csv, .txt) to parse, or state a file action."
    )
    logs.append("file: finished with general recommendation")
    return state


def _delete_without_target(text: str) -> bool:
    lower = text.lower().strip()
    if not any(word in lower for word in ("delete", "remove", "erase")):
        return False
    target_markers = (
        "/",
        "\\",
        ".txt",
        ".md",
        ".py",
        ".ts",
        ".tsx",
        ".json",
        ".yaml",
        ".yml",
        " file ",
        " folder ",
        " directory ",
        " memory ",
        " chat ",
        " message ",
    )
    return not any(marker in lower for marker in target_markers)
