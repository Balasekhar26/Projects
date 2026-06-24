from __future__ import annotations

import ast
import os
import re
import json
from typing import Any
from backend.core.local_answers import built_in_answer
from backend.core.model_router import ask_model
from backend.tools.code_tools import git_status
from backend.core.safety import is_protected_path
from backend.core.action_broker import ActionBroker


EXPLANATION_WORDS = (
    "explain",
    "tell me",
    "what is",
    "what are",
    "simple words",
    "deep explanation",
    "about",
)

CODE_ACTION_WORDS = (
    "build",
    "fix",
    "change",
    "edit",
    "implement",
    "debug",
    "error",
    "test",
    "code",
    "file",
    "delete",
    "remove",
    "erase",
)


def classify_coder_action(user_input: str) -> tuple[str, dict[str, Any]]:
    lower = user_input.lower()
    
    # 1. Dependency protection: Block installer engines
    if any(cmd in lower for cmd in ("pip install", "npm install", "cargo add", "brew install", "apt install")):
        return "INSTALL_PACKAGE", {"command": user_input}
        
    # 2. Analyze Repo
    if "analyze" in lower and any(term in lower for term in ("repo", "repository", "workspace", "codebase")):
        return "ANALYZE_REPO", {}
        
    # 3. Create Proposal
    if "proposal" in lower or "propose" in lower:
        return "CREATE_PROPOSAL", {}
        
    # 4. Run tests
    if "run test" in lower or "pytest" in lower:
        target_test = ""
        for word in user_input.split():
            if "test_" in word or "tests/" in word:
                target_test = word.strip(".,;:\"'")
                break
        return "RUN_TESTS", {"target": target_test}
        
    # 5. Benchmarks
    if "benchmark" in lower:
        return "RUN_BENCHMARKS", {}
        
    # 6. AST/Syntax analyze
    if "analyze" in lower or "syntax" in lower or "ast" in lower or "lint" in lower:
        return "ANALYZE_CODE", {}
        
    # 7. Delete file
    if "delete" in lower or "remove" in lower or "erase" in lower:
        return "DELETE_FILE", {}
        
    # 8. Patch Generation
    if any(kw in lower for kw in ("patch", "modify", "edit", "change", "write", "implement", "fix", "update")):
        if "create" in lower or "new file" in lower:
            return "CREATE_FILE", {}
        return "PATCH_CODE", {}

    if "create" in lower or "new" in lower:
        return "CREATE_FILE", {}

    if "write" in lower:
        return "WRITE_FILE", {}
        
    if any(cmd in lower for cmd in ("run command", "execute command", "shell", "bash", "sh", "python")):
        return "RUN_SHELL", {}

    return "READ_FILE", {}


def coder_node(state: dict[str, Any]) -> dict[str, Any]:
    user_input = state["user_input"]
    lower_input = user_input.lower()
    logs = state.setdefault("logs", [])
    
    # Initialize trackers
    state.setdefault("coder_patches_count", 0)
    state.setdefault("coder_retries_count", 0)
    state.setdefault("coder_test_cycles_count", 0)
    state["approval_required"] = False
    
    # 0.5 Budget Gating
    if state.get("coder_patches_count", 0) >= 5 or state.get("coder_retries_count", 0) >= 3 or state.get("coder_test_cycles_count", 0) >= 5:
        state["result"] = "Error: budget exceeded"
        logs.append("coder: blocked because budget exceeded")
        return state

    # 0.6 Download Quarantine Protection
    if "downloaded.py" in lower_input or "downloads/" in lower_input:
        state["result"] = "Error: Execution of untrusted downloaded files is strictly prohibited."
        logs.append("coder: blocked execution of downloaded/untrusted file")
        return state
    
    # 1. Safety Check: Protected Files
    if is_protected_path(user_input) or (state.get("plan") and is_protected_path(str(state.get("plan")))):
        state["result"] = "Error: Modification of protected core governance modules is strictly prohibited."
        logs.append("coder: blocked attempt to access or modify protected core file")
        return state

    # Block direct git push / remote access
    if any(cmd in lower_input for cmd in ("git push", "push to origin", "write direct", "overwrite directly", "push")):
        state["result"] = "Error: Direct push/write to main/production repository is prohibited. Please submit a change proposal instead."
        logs.append("coder: blocked direct git push or write attempt")
        return state

    # 2. Classify action
    action, params = classify_coder_action(user_input)
    logs.append(f"coder: classified action as {action} with params {params}")

    # 3. Handle specific action delegation to the Action Broker
    try:
        # Mode 1: Analyze Repository
        if action == "ANALYZE_REPO":
            broker_res = ActionBroker.intake_request("coder", action, params, state)
            if not broker_res.get("success"):
                state["result"] = broker_res.get("error")
                return state
                
            # Perform cognitive analysis
            report = ActionBroker.analyze_workspace(".")
            state["result"] = (
                f"Repository Analysis Report:\n"
                f"- Architecture: {report['architecture_summary']}\n"
                f"- Dependencies: {', '.join(report['dependency_map']) if report['dependency_map'] else 'None'}\n"
                f"- Safety Scan: {', '.join(report['security_observations']) if report['security_observations'] else 'No security issues found'}"
            )
            logs.append("coder: generated codebase analysis report")
            
        # Mode 2: Create Proposals
        elif action == "CREATE_PROPOSAL":
            broker_res = ActionBroker.intake_request("coder", action, params, state)
            if not broker_res.get("success"):
                state["result"] = broker_res.get("error")
                return state
                
            proposal_prompt = (
                f"Create a code proposal for the following request: '{user_input}'. "
                f"Provide: 1. Change Plan, 2. Affected Files, 3. Estimated Risk (LOW/MEDIUM/HIGH), "
                f"4. Test Strategy, 5. Rollback Strategy. Return in structured plain text."
            )
            state["result"] = ask_model(proposal_prompt, role="coder")
            logs.append("coder: proposal generated")

        # Mode 3: Generate Patches & Sandbox Validation
        elif action in ("PATCH_CODE", "CREATE_FILE", "WRITE_FILE"):
            state["coder_patches_count"] = state.get("coder_patches_count", 0) + 1
            
            # Identify target file
            target_file = None
            for word in user_input.split():
                if "." in word or "/" in word or "\\" in word:
                    cleaned = word.strip(".,;:\"'")
                    if cleaned.endswith(".py") or cleaned.endswith(".txt") or cleaned.endswith(".js") or cleaned.endswith(".sh"):
                        target_file = cleaned
                        break
            
            if not target_file:
                status = git_status()
                state["result"] = ask_model(
                    f"Act as Bala's technical assistant.\nRequest: {user_input}\nPlan: {state.get('plan')}\nGit status: {status}\n"
                    "If the user asks for code, always provide a clean, complete, formatted code block using markdown syntax (e.g. ```python ... ```). "
                    "Do not write to files directly.",
                    role="coder",
                )
                logs.append("coder: responded with code generation fallback")
                return state
                
            # Extract or generate code
            code_content = ""
            code_blocks = re.findall(r"```(?:python|js|sh)?\n(.*?)\n```", user_input, re.DOTALL)
            if code_blocks:
                code_content = code_blocks[0]
            else:
                quoted = re.findall(r"['\"](.*?)['\"]", user_input)
                if quoted:
                    code_content = quoted[0]
                else:
                    logs.append(f"coder: generating patch content for '{target_file}' using LLM...")
                    gen_prompt = f"Write Python code for a file named '{target_file}' to satisfy this request: '{user_input}'. Return ONLY the raw code, no markdown formatting, no explanations."
                    code_content = ask_model(gen_prompt, role="coder")
            
            # Generate test pairing
            test_file = f"test_{os.path.basename(target_file)}"
            logs.append(f"coder: generating tests for '{target_file}'...")
            test_prompt = f"Write a python pytest test file for the following code located in '{target_file}':\n\n{code_content}\n\nReturn ONLY the raw python test code, no markdown, no explanations."
            test_code = ask_model(test_prompt, role="coder")
            
            # Delegate patch application, validation, testing, and review packaging to the Action Broker
            broker_params = {
                "target": target_file,
                "code": code_content,
                "test_code": test_code
            }
            
            broker_res = ActionBroker.intake_request("coder", "PATCH_CODE", broker_params, state)
            
            if broker_res.get("approval_required"):
                state["approval_required"] = True
                state["proposed_action"] = broker_res.get("proposed_action")
                state["result"] = broker_res.get("error")
                return state
                
            if not broker_res.get("success"):
                state["result"] = broker_res.get("error")
                return state
                
            broker_result_details = broker_res.get("result", {})
            if not broker_result_details.get("success"):
                state["result"] = broker_result_details.get("error", "Validation failed")
                return state
                
            # Successful validation, capture broker-packaged results
            review_pkg = broker_result_details["review_package"]
            state["result"] = json.dumps(review_pkg, indent=2)
            logs.append("coder: received review package from Action Broker")
            
        # Mode 4: Run Tests
        elif action == "RUN_TESTS":
            broker_res = ActionBroker.intake_request("coder", action, params, state)
            
            if broker_res.get("approval_required"):
                state["approval_required"] = True
                state["proposed_action"] = broker_res.get("proposed_action")
                state["result"] = broker_res.get("error")
                return state
                
            if not broker_res.get("success"):
                state["result"] = broker_res.get("error")
                return state
                
            test_res = broker_res["result"]
            state["result"] = f"Test Execution Result:\n{test_res['stdout'][-2000:]}"
            logs.append(f"coder: ran tests via Action Broker for {params.get('target') or 'all'}")
            
        # Delete file
        elif action == "DELETE_FILE":
            target_file = None
            for word in user_input.split():
                if "." in word or "/" in word or "\\" in word:
                    target_file = word.strip(".,;:\"'")
                    break
            broker_params = {"target": target_file}
            broker_res = ActionBroker.intake_request("coder", action, broker_params, state)
            
            if broker_res.get("approval_required"):
                state["approval_required"] = True
                state["proposed_action"] = broker_res.get("proposed_action")
                state["result"] = broker_res.get("error")
                return state
                
            if not broker_res.get("success"):
                state["result"] = broker_res.get("error")
                return state
                
            state["result"] = broker_res["result"]["message"]
            logs.append(f"coder: deleted file '{target_file}' via Action Broker")
            
        # Install package
        elif action == "INSTALL_PACKAGE":
            broker_res = ActionBroker.intake_request("coder", action, params, state)
            
            if broker_res.get("approval_required"):
                state["approval_required"] = True
                state["proposed_action"] = broker_res.get("proposed_action")
                state["result"] = broker_res.get("error")
                return state
                
            if not broker_res.get("success"):
                state["result"] = broker_res.get("error")
                return state
                
            state["result"] = broker_res["result"]["message"]
            logs.append(f"coder: ran package installation via Action Broker: {user_input}")
            
        # Mode 6: AST/Syntax analyze
        elif action == "ANALYZE_CODE":
            # Extract target file
            target_file = None
            for word in user_input.split():
                if "." in word or "/" in word or "\\" in word:
                    target_file = word.strip(".,;:\"'")
                    break
            
            if not target_file or not os.path.exists(target_file):
                state["result"] = "Error: File not found or not specified."
                return state
                
            try:
                with open(target_file, "r", encoding="utf-8") as f:
                    content = f.read()
                ast.parse(content)
                state["result"] = "AST Check: PASSED"
                logs.append(f"coder: validated syntax for {target_file}")
            except Exception as e:
                state["result"] = f"AST Check: FAILED. SyntaxError: {e}"
                logs.append(f"coder: validated syntax failed for {target_file}")
            
        # Fallback explanation or read-only commands
        else:
            status = git_status()
            explanation_only = any(word in lower_input for word in EXPLANATION_WORDS) and not any(
                word in lower_input for word in CODE_ACTION_WORDS
            )
            if explanation_only:
                local_answer = built_in_answer(user_input)
                if local_answer:
                    state["result"] = local_answer
                    logs.append("coder: answered from built-in local knowledge")
                    return state
                    
            state["result"] = ask_model(
                f"Act as Bala's technical assistant.\nRequest: {user_input}\nPlan: {state.get('plan')}\nGit status: {status}\n"
                "If the user asks for an explanation, explain clearly and deeply in simple words. "
                "If the user asks for code, always provide a clean, complete, formatted code block using markdown syntax (e.g. ```python ... ```). "
                "Do not write to files directly.",
                role="fast" if explanation_only else "coder",
            )
            logs.append("coder: responded")
            
    except Exception as e:
        state["result"] = f"Error during coder execution: {e}"
        logs.append(f"coder execution error: {e}")
        
    return state
