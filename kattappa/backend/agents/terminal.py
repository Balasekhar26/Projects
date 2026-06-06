from __future__ import annotations

from backend.tools.terminal_tools import run_command


def terminal_node(state):
    command = state["user_input"].removeprefix("run ").strip()
    state["result"] = str(run_command(command))
    state["logs"].append("terminal: command evaluated")
    return state
