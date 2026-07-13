import re
from backend.tools.terminal_tools import run_command


def terminal_node(state):
    command_raw = state["user_input"].strip()
    if command_raw.lower().startswith("run "):
        command_raw = command_raw[4:].strip()
        
    lower = command_raw.lower()
    if "git status" in lower:
        command = "git status"
    elif "pytest" in lower:
        command = "pytest"
    else:
        command = command_raw
        for sep in (" and ", " then ", " & ", " && "):
            if sep in f" {command.lower()} ":
                parts = re.split(rf"(?i){re.escape(sep)}", command)
                command = parts[0].strip()
                break
                
    state["result"] = str(run_command(command))
    state["logs"].append(f"terminal: command evaluated: {command}")
    return state
