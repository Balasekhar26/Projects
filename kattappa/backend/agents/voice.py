"""Voice Agent router — thin delegation shim.

This module provides the `voice_node` entry point that the LangGraph state
machine calls.  It delegates immediately to the full hardened Voice Agent V1
implementation in `voice_agent.py`.

The split preserves backward compatibility with any import that references
``backend.agents.voice.voice_node`` while keeping the core implementation in
a single, well-documented module.
"""
from __future__ import annotations

from backend.agents.voice_agent import voice_node  # noqa: F401 — re-exported

__all__ = ["voice_node"]
