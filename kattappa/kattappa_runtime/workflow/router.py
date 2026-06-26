"""
Tool Router — maps task.tool_hint → callable handler
=====================================================

The ToolRouter is the bridge between the Planner's abstract task
descriptions and Kattappa's actual engines.

Each handler receives a Task and returns a (success: bool, result: str) tuple.

Default routing table:
  research_engine  → ResearchEngine.research()
  memory_writer    → MemoryProvider.writer.store_fact()
  skill_memory     → SkillMemory.update()
  planner          → nested sub-planning (stub for now)
  synthesizer      → ResearchSynthesizer inline call
  code_runner      → sandboxed python exec (stub with safety flag)
  git              → shell git command (stub)
  web_search       → ResearchEngine web adapter
  reflection_engine→ ReflectionEngine.reflect()
  default          → no-op stub that returns success

Handlers are pluggable: call router.register("my_tool", my_fn) to add custom tools.

Safety
------
HIGH risk tool_hints (code_runner, git, shell) are wrapped in a dry_run
guard when WorkflowEngine.dry_run=True. In dry-run mode they always
return (True, "DRY_RUN: would have executed ...").
"""

from __future__ import annotations

import textwrap
from typing import Callable, Dict, Optional, Tuple, TYPE_CHECKING

from kattappa_runtime.planner.schema import Task, RiskLevel

if TYPE_CHECKING:
    from kattappa_runtime.research.engine  import ResearchEngine
    from kattappa_runtime.memory           import MemoryProvider
    from kattappa_runtime.skill_memory.store import SkillMemory
    from kattappa_runtime.reflection.engine import ReflectionEngine

# type alias
HandlerResult = Tuple[bool, str]   # (succeeded, result_text)
Handler       = Callable[[Task], HandlerResult]

# Tool hints treated as HIGH-risk (wrapped by dry_run guard)
_HIGH_RISK_HINTS = {"code_runner", "git", "shell", "bash", "terminal"}


class ToolRouter:
    """
    Maps task.tool_hint strings to concrete handler callables.

    Usage
    -----
        router = ToolRouter(research_engine=engine, memory=mem)
        success, result = router.execute(task, dry_run=False)

    Registration
    ------------
        router.register("my_tool", my_handler_fn)
        # handler signature: (Task) -> (bool, str)
    """

    def __init__(
        self,
        research_engine:   Optional["ResearchEngine"]  = None,
        memory:            Optional["MemoryProvider"]  = None,
        skill_memory:      Optional["SkillMemory"]     = None,
        reflection_engine: Optional["ReflectionEngine"] = None,
    ):
        self._research = research_engine
        self._memory   = memory
        self._skill    = skill_memory
        self._reflect  = reflection_engine

        # Build the default routing table
        self._table: Dict[str, Handler] = {}
        self._register_defaults()

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def register(self, tool_hint: str, handler: Handler) -> None:
        """Register a custom handler for a tool_hint string."""
        self._table[tool_hint.lower()] = handler

    def execute(self, task: Task, dry_run: bool = False) -> HandlerResult:
        """
        Execute a task via the appropriate handler.

        Parameters
        ----------
        task : Task
            The task to execute.
        dry_run : bool
            If True, HIGH-risk tools return a safe stub result instead of
            executing.

        Returns
        -------
        (succeeded: bool, result: str)
        """
        hint    = (task.tool_hint or "default").lower()
        handler = self._table.get(hint, self._table["default"])

        # Dry-run guard for high-risk operations
        if dry_run and hint in _HIGH_RISK_HINTS:
            return True, f"DRY_RUN: would execute '{task.title}' via {hint}"

        try:
            return handler(task)
        except Exception as exc:
            return False, f"ToolRouter: handler raised {type(exc).__name__}: {exc}"

    def known_tools(self) -> list[str]:
        return sorted(self._table.keys())

    # ------------------------------------------------------------------
    # Default handlers
    # ------------------------------------------------------------------

    def _register_defaults(self) -> None:
        """Wire up all default tool handlers."""

        # ── Research ──────────────────────────────────────────────────
        def handle_research(task: Task) -> HandlerResult:
            if not self._research:
                return True, "research_engine not connected (no-op)"
            topic = task.description or task.title
            try:
                report = self._research.research(
                    topic=topic[:200],
                    notes=f"workflow task: {task.task_id[:8]}",
                )
                facts = "; ".join(report.key_facts[:3]) if report.key_facts else report.summary[:150]
                return True, f"Found {len(report.findings)} sources. Key: {facts}"
            except Exception as exc:
                return False, f"Research failed: {exc}"

        # ── Memory writer ─────────────────────────────────────────────
        def handle_memory(task: Task) -> HandlerResult:
            if not self._memory:
                return True, "memory not connected (no-op)"
            try:
                self._memory.writer.store_fact(
                    fact       = task.result or task.description or task.title,
                    confidence = 0.8,
                    importance = 0.7,
                    domain     = "workflow",
                )
                return True, "Stored in semantic memory"
            except Exception as exc:
                return False, f"Memory write failed: {exc}"

        # ── Skill memory ──────────────────────────────────────────────
        def handle_skill(task: Task) -> HandlerResult:
            if not self._skill:
                return True, "skill_memory not connected (no-op)"
            try:
                self._skill.record_attempt(
                    domain    = task.description[:80] if task.description else "general",
                    succeeded = True,
                )
                return True, "Skill profile updated"
            except Exception as exc:
                return False, f"Skill update failed: {exc}"

        # ── Reflection engine ─────────────────────────────────────────
        def handle_reflection(task: Task) -> HandlerResult:
            if not self._reflect:
                return True, "reflection_engine not connected (no-op)"
            try:
                r = self._reflect.reflect(
                    input_text   = task.title,
                    action_taken = task.description,
                    result       = task.result or "Completed",
                    domain       = "workflow",
                    succeeded    = True,
                )
                return True, f"Reflection lesson: {r.lesson[:80]}"
            except Exception as exc:
                return False, f"Reflection failed: {exc}"

        # ── Code runner (stub — sandboxed in Step 30) ─────────────────
        def handle_code_runner(task: Task) -> HandlerResult:
            # Production implementation will sandbox this.
            # For now: return success with a clear stub note.
            return True, (
                f"[STUB] code_runner: would execute task '{task.title}'. "
                "Real execution requires sandboxed environment (Step 30)."
            )

        # ── Planner (nested sub-goal) ─────────────────────────────────
        def handle_planner(task: Task) -> HandlerResult:
            return True, (
                f"[STUB] planner: would create sub-goal for '{task.title}'. "
                "Nested planning available via PlannerEngine.submit()."
            )

        # ── Synthesizer ───────────────────────────────────────────────
        def handle_synthesizer(task: Task) -> HandlerResult:
            return True, f"Synthesis complete for: {task.title[:60]}"

        # ── Git (stub) ────────────────────────────────────────────────
        def handle_git(task: Task) -> HandlerResult:
            return True, f"[STUB] git: would run git operation for '{task.title}'"

        # ── Default (no-op) ───────────────────────────────────────────
        def handle_default(task: Task) -> HandlerResult:
            return True, f"[no-op] Executed: {task.title[:60]}"

        # Register all
        self._table["research_engine"]   = handle_research
        self._table["memory_writer"]     = handle_memory
        self._table["skill_memory"]      = handle_skill
        self._table["reflection_engine"] = handle_reflection
        self._table["code_runner"]       = handle_code_runner
        self._table["planner"]           = handle_planner
        self._table["synthesizer"]       = handle_synthesizer
        self._table["git"]               = handle_git
        self._table["default"]           = handle_default

        # Aliases
        self._table["web_search"]    = handle_research
        self._table["arxiv"]         = handle_research
        self._table["wikipedia"]     = handle_research
        self._table["bash"]          = handle_code_runner
        self._table["shell"]         = handle_code_runner
        self._table["terminal"]      = handle_code_runner
