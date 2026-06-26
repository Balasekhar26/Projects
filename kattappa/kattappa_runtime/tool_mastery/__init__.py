"""
Tool Mastery Engine — Step 26
==============================
Tracks Kattappa's mastery of every tool it uses.

A "tool" is any discrete capability with an invocable interface:
  - Shell commands (git, python, bash)
  - Web search
  - Code runner
  - MCP server tools
  - APIs (Wikipedia, Arxiv, etc.)
  - Internal engines (ResearchEngine, ReflectionEngine, etc.)

Per-tool tracking:
  ToolProfile
    ├── name            : str       (unique tool identifier)
    ├── category        : ToolCategory
    ├── confidence      : float     [0.0 – 1.0]
    ├── attempts        : int
    ├── successes       : int
    ├── success_rate    : float     (computed)
    ├── avg_latency_ms  : float     (EMA of response time)
    ├── last_used       : str       (ISO-8601)
    ├── common_failures : List[str] (deduped error patterns)
    ├── mastery_score   : float     (composite, [0.0 – 1.0])
    └── notes           : str

mastery_score formula:
    0.50 * confidence
  + 0.30 * success_rate
  + 0.20 * (1 - latency_penalty)   # lower latency = better

Public API
----------
    from kattappa_runtime.tool_mastery import ToolMastery

    tm = ToolMastery()
    tm.record_use("git", succeeded=True, latency_ms=45.0)
    tm.record_use("web_search", succeeded=False, latency_ms=3200.0,
                  failure_note="timeout on first attempt")

    print(tm.summary_table())
    print(tm.weakest_tools(n=3))
"""

from kattappa_runtime.tool_mastery.store import ToolMastery, ToolProfile, ToolCategory

__all__ = ["ToolMastery", "ToolProfile", "ToolCategory"]
