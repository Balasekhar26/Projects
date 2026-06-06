from __future__ import annotations

from backend.core.free_stack import free_stack_report
from backend.tools.voice_tools import voice_profile


def voice_node(state):
    report = free_stack_report()
    profile = voice_profile()
    voice_items = [
        item
        for item in report["capabilities"]
        if item["key"] in {"faster_whisper", "piper", "openwakeword"}
    ]
    lines = [
        "Voice agent free/local readiness:",
        f"Assistant voice: {profile['name']} ({profile['style']}).",
        f"Voice boundary: {profile['policy']}",
    ]
    for item in voice_items:
        marker = "ready" if item["installed"] else "missing"
        lines.append(f"- {item['name']}: {marker} ({item['role']})")
    lines.append("Use push-to-talk now; wake-word mode activates when openWakeWord is installed.")
    state["result"] = "\n".join(lines)
    state["logs"].append("voice: ready")
    return state
