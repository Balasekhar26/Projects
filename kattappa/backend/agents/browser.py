from __future__ import annotations

import re
from typing import Any

from backend.tools.browser_tools import (
    read_url,
    search_web_basic,
    map_links,
    fill_form,
    download_file
)
from backend.core.execution_policy import DEFAULT_POLICY_ENGINE, ActionPolicy, PolicyOutcome

# Register browser agent policies in the central Execution Policy Engine
DEFAULT_POLICY_ENGINE.register(
    ActionPolicy("BROWSER_SEARCH", auto_execute=True, require_human=False, description="Search the web")
)
DEFAULT_POLICY_ENGINE.register(
    ActionPolicy("BROWSER_READ", auto_execute=True, require_human=False, description="Read a website URL")
)
DEFAULT_POLICY_ENGINE.register(
    ActionPolicy("BROWSER_NAVIGATE", auto_execute=True, require_human=False, description="Navigate to a URL")
)
DEFAULT_POLICY_ENGINE.register(
    ActionPolicy("BROWSER_MAP_LINKS", auto_execute=True, require_human=False, description="Extract links from a page")
)
DEFAULT_POLICY_ENGINE.register(
    ActionPolicy("BROWSER_EXTRACT_INFO", auto_execute=True, require_human=False, description="Scrape content or data")
)
DEFAULT_POLICY_ENGINE.register(
    ActionPolicy("BROWSER_DOWNLOAD_FILE", auto_execute=True, require_human=False, description="Download a file via browser")
)
DEFAULT_POLICY_ENGINE.register(
    ActionPolicy("BROWSER_SPEEDTEST", auto_execute=True, require_human=False, description="Run internet speed test")
)

DEFAULT_POLICY_ENGINE.register(
    ActionPolicy("BROWSER_FILL_FORM", auto_execute=False, require_human=True, description="Fill inputs on a page")
)
DEFAULT_POLICY_ENGINE.register(
    ActionPolicy("BROWSER_CLICK_SUBMIT", auto_execute=False, require_human=True, description="Click a submit button")
)
DEFAULT_POLICY_ENGINE.register(
    ActionPolicy("BROWSER_LOGIN", auto_execute=False, require_human=True, description="Fill credentials and authenticate")
)

DEFAULT_POLICY_ENGINE.register(
    ActionPolicy("BROWSER_PAYMENT", blocked=True, require_human=True, description="Blocked payment actions")
)
DEFAULT_POLICY_ENGINE.register(
    ActionPolicy("BROWSER_DELETE", blocked=True, require_human=True, description="Blocked deletion actions")
)


def classify_browser_action(user_input: str) -> tuple[str, dict[str, Any]]:
    lower_input = user_input.lower()
    
    # 1. Blocked Actions (Rule 9 / Matrix)
    payment_triggers = ("pay", "purchase", "buy", "checkout", "card", "transaction")
    delete_triggers = ("delete", "remove account", "erase data", "uninstall", "delete domain")
    
    if any(trigger in lower_input for trigger in payment_triggers):
        return "BROWSER_PAYMENT", {}
    if any(trigger in lower_input for trigger in delete_triggers):
        return "BROWSER_DELETE", {}

    # Check for speedtest first before generic URL/Search
    if any(q in lower_input for q in ("speedtest", "speed test", "internet speed")):
        return "BROWSER_SPEEDTEST", {}
        
    # 2. Extract URL
    url_match = re.search(r"https?://[^\s/$.?#].[^\s]*", user_input)
    url = url_match.group(0) if url_match else None
    
    # 3. Write Actions (Form submission, fill, login)
    write_triggers = ("submit", "post", "fill", "click button", "send form", "click submit", "type text", "login")
    if any(trigger in lower_input for trigger in write_triggers):
        form_data = {}
        kv_pairs = re.findall(r"(\w+)\s*=\s*([^\s,]+)", user_input)
        if kv_pairs:
            form_data = {k: v for k, v in kv_pairs}
        else:
            form_data = {"input": "test_input"}
            
        submit_sel = None
        sel_match = re.search(r"(?:selector|button|click)\s+(\S+)", lower_input)
        if sel_match:
            submit_sel = sel_match.group(1)
            
        action = "BROWSER_CLICK_SUBMIT" if ("click" in lower_input or "submit" in lower_input) else "BROWSER_FILL_FORM"
        if "login" in lower_input:
            action = "BROWSER_LOGIN"
            
        return action, {"url": url or "https://google.com", "form_data": form_data, "submit_selector": submit_sel}
        
    # 4. Download file (Rule 5)
    if "download" in lower_input or "save file" in lower_input:
        click_sel = None
        sel_match = re.search(r"(?:selector|button|click)\s+(\S+)", lower_input)
        if sel_match:
            click_sel = sel_match.group(1)
        return "BROWSER_DOWNLOAD_FILE", {"url": url or "https://example.com/file", "click_selector": click_sel}
        
    # 5. Map links
    if "map links" in lower_input or "get links" in lower_input or "find links" in lower_input:
        return "BROWSER_MAP_LINKS", {"url": url or "https://google.com"}
        
    # 6. Extract info
    if "extract" in lower_input or "scrape" in lower_input:
        return "BROWSER_EXTRACT_INFO", {"url": url or "https://google.com"}
        
    # 7. Search
    if url is None:
        return "BROWSER_SEARCH", {"query": user_input}
        
    # 8. Navigate / Read (default for URLs)
    return "BROWSER_NAVIGATE", {"url": url}


def browser_node(state: dict[str, Any]) -> dict[str, Any]:
    import json
    from backend.core.action_broker import ActionBroker
    
    user_input = state["user_input"]
    logs = state.setdefault("logs", [])
    
    # Classify action
    action, params = classify_browser_action(user_input)
    logs.append(f"browser: classified action as {action} with params {params}")
    
    # Update browser_tabs depth/list for navigation
    url = params.get("url")
    if url:
        tabs = state.setdefault("browser_tabs", ["https://google.com"])
        if url not in tabs:
            tabs.append(url)
            
    # Delegate to Action Broker
    broker_res = ActionBroker.intake_request("browser", action, params, state)
    
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
