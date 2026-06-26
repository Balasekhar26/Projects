"""
Goal Decomposer — turns a Goal description into a Plan with Tasks.

The decomposer uses a rule-based template system by default.
An LLM hook can replace it for richer decomposition.

Decomposition strategy:
  1. Parse the goal title for action verbs and domain keywords
  2. Match against domain-specific templates
  3. Generate an ordered task list with dependencies and cost estimates
  4. Produce multiple Plan alternatives (fast/thorough variants)

Template structure
------------------
Each template is keyed by a list of trigger keywords.
If any keyword appears in the goal title (case-insensitive), the
template is selected.

Templates produce N tasks. The "fast" plan takes the first 3 tasks.
The "thorough" plan uses all tasks.
"""

from __future__ import annotations

import re
from typing import Callable, List, Optional

from kattappa_runtime.planner.schema import (
    Goal, Plan, Task, RiskLevel
)

# ------------------------------------------------------------------
# Domain task templates
# ------------------------------------------------------------------
# Each entry: (triggers, task_specs)
# task_spec: (title, description, tool_hint, cost, risk)
# Dependencies are added as linear chain by default (task N depends on N-1)

_TEMPLATES: list[tuple[list[str], list[tuple[str, str, str, float, RiskLevel]]]] = [
    # Research tasks
    (["research", "study", "learn", "understand", "investigate"],
     [
         ("Search Wikipedia for overview",
          "Use research engine to retrieve a Wikipedia summary on the topic.",
          "research_engine", 1.0, RiskLevel.LOW),
         ("Search Arxiv for technical papers",
          "Use research engine to retrieve relevant Arxiv abstracts.",
          "research_engine", 1.5, RiskLevel.LOW),
         ("Search local corpus for prior knowledge",
          "Check if the topic already appears in Kattappa's training corpus.",
          "research_engine", 0.5, RiskLevel.LOW),
         ("Synthesise findings into key facts",
          "Combine findings from all sources into a structured summary.",
          "synthesizer", 1.0, RiskLevel.LOW),
         ("Store findings in semantic memory",
          "Promote key facts to long-term semantic memory.",
          "memory_writer", 0.5, RiskLevel.LOW),
         ("Update skill profile for domain",
          "Record research session in Skill Memory for domain.",
          "skill_memory", 0.5, RiskLevel.LOW),
     ]),

    # Build / create / implement tasks
    (["build", "create", "implement", "develop", "write", "generate", "make"],
     [
         ("Research the target domain",
          "Gather background knowledge before implementing.",
          "research_engine", 1.0, RiskLevel.LOW),
         ("Plan implementation approach",
          "Decompose the implementation into sub-components.",
          "planner", 1.0, RiskLevel.LOW),
         ("Write initial code",
          "Generate the primary implementation code.",
          "code_runner", 3.0, RiskLevel.MEDIUM),
         ("Write unit tests",
          "Create tests that verify the implementation's correctness.",
          "code_runner", 2.0, RiskLevel.LOW),
         ("Run tests and fix failures",
          "Execute test suite and iterate on failures.",
          "code_runner", 2.0, RiskLevel.MEDIUM),
         ("Refactor and document",
          "Clean up code, add docstrings, ensure quality.",
          "code_runner", 1.0, RiskLevel.LOW),
     ]),

    # Debug / fix / troubleshoot
    (["debug", "fix", "repair", "troubleshoot", "diagnose", "solve"],
     [
         ("Reproduce the problem",
          "Create a minimal reproducible case for the issue.",
          "code_runner", 1.0, RiskLevel.LOW),
         ("Analyse the failure",
          "Read error messages and trace the root cause.",
          "code_runner", 1.5, RiskLevel.LOW),
         ("Research potential solutions",
          "Search for known fixes or similar issues.",
          "research_engine", 1.0, RiskLevel.LOW),
         ("Apply the fix",
          "Implement the chosen solution.",
          "code_runner", 2.0, RiskLevel.MEDIUM),
         ("Verify fix with tests",
          "Run tests to confirm the issue is resolved.",
          "code_runner", 1.0, RiskLevel.LOW),
         ("Document root cause and fix",
          "Record the mistake and lesson in MistakeLog.",
          "reflection_engine", 0.5, RiskLevel.LOW),
     ]),

    # Analyse / evaluate / assess
    (["analyse", "analyze", "evaluate", "assess", "review", "audit", "measure"],
     [
         ("Define evaluation criteria",
          "Specify what success looks like for this analysis.",
          "planner", 0.5, RiskLevel.LOW),
         ("Gather raw data",
          "Collect all relevant data points and evidence.",
          "research_engine", 1.0, RiskLevel.LOW),
         ("Apply analysis framework",
          "Run analysis logic on collected data.",
          "code_runner", 2.0, RiskLevel.LOW),
         ("Identify patterns and anomalies",
          "Highlight key findings from the analysis.",
          "code_runner", 1.0, RiskLevel.LOW),
         ("Generate report",
          "Summarise findings in a structured report.",
          "code_runner", 1.0, RiskLevel.LOW),
         ("Store analysis in memory",
          "Preserve findings in episodic and semantic memory.",
          "memory_writer", 0.5, RiskLevel.LOW),
     ]),

    # Translate / convert
    (["translate", "convert", "transform", "reformat"],
     [
         ("Identify source format and target format",
          "Understand what is being translated and what the output should be.",
          "planner", 0.5, RiskLevel.LOW),
         ("Research translation rules for this domain",
          "Look up relevant grammar/format rules.",
          "research_engine", 1.0, RiskLevel.LOW),
         ("Perform translation",
          "Execute the translation or conversion.",
          "code_runner", 2.0, RiskLevel.MEDIUM),
         ("Validate output quality",
          "Check the translated output against quality criteria.",
          "code_runner", 1.0, RiskLevel.LOW),
         ("Store translation pair in memory",
          "Add to episodic memory for future reference.",
          "memory_writer", 0.5, RiskLevel.LOW),
     ]),
]

# Generic fallback template
_GENERIC_TEMPLATE: list[tuple[str, str, str, float, RiskLevel]] = [
    ("Research the topic",
     "Gather background knowledge needed for this goal.",
     "research_engine", 1.0, RiskLevel.LOW),
    ("Formulate an approach",
     "Define the strategy for achieving the goal.",
     "planner", 1.0, RiskLevel.LOW),
    ("Execute the primary action",
     "Carry out the main work required by the goal.",
     "code_runner", 3.0, RiskLevel.MEDIUM),
    ("Verify the outcome",
     "Check that the goal has been achieved.",
     "code_runner", 1.0, RiskLevel.LOW),
    ("Record results in memory",
     "Store what was learned or accomplished.",
     "memory_writer", 0.5, RiskLevel.LOW),
]


class GoalDecomposer:
    """
    Breaks a Goal into one or more Plan alternatives.

    Parameters
    ----------
    llm_decomposer : callable | None
        LLM hook: receives (goal_title, goal_description) and returns
        List[dict] each with keys: title, description, tool_hint,
        estimated_cost, risk_level (string), dependencies (list of indices).
        If provided and succeeds, overrides rule-based decomposition.
    """

    def __init__(self, llm_decomposer: Optional[Callable] = None):
        self._llm = llm_decomposer

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def decompose(self, goal: Goal) -> Goal:
        """
        Generate plans for this goal and attach them.
        Returns the same goal object (mutated in place).

        Produces two plans:
          1. "Fast plan"      — first 3 tasks (low cost, lower coverage)
          2. "Thorough plan"  — all tasks (higher cost, full coverage)
        """
        task_specs = self._get_task_specs(goal)

        # Build the thorough plan (all tasks, linear dependency chain)
        thorough_tasks = self._build_tasks(task_specs)
        thorough_plan  = Plan(
            goal_id = goal.goal_id,
            title   = "Thorough — full task sequence",
            tasks   = thorough_tasks,
            notes   = "Complete step-by-step plan. Higher cost, better coverage.",
        )

        # Build the fast plan (first 3 tasks only, no long-chain deps)
        fast_specs = task_specs[:3]
        fast_tasks = self._build_tasks(fast_specs)
        fast_plan  = Plan(
            goal_id = goal.goal_id,
            title   = "Fast — minimal viable approach",
            tasks   = fast_tasks,
            notes   = "Rapid execution with fewer steps. Lower cost, less thorough.",
        )

        goal.plans = [fast_plan, thorough_plan]

        # Auto-select the best plan (lowest plan_score)
        best = goal.best_plan()
        if best:
            goal.selected_plan_id = best.plan_id

        return goal

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _get_task_specs(self, goal: Goal) -> list:
        """Try LLM decomposer first, fall back to rules."""
        if self._llm:
            try:
                raw = self._llm(goal.title, goal.description)
                if isinstance(raw, list) and raw:
                    return self._parse_llm_output(raw)
            except Exception:
                pass
        return self._rule_based_specs(goal.title)

    def _rule_based_specs(self, title: str) -> list:
        """Match title against templates and return task specs."""
        title_lower = title.lower()
        for triggers, specs in _TEMPLATES:
            if any(kw in title_lower for kw in triggers):
                return list(specs)
        return list(_GENERIC_TEMPLATE)

    @staticmethod
    def _build_tasks(specs: list) -> list[Task]:
        """
        Build Task objects from specs with linear dependency chaining.
        Each task depends on the previous one.
        """
        tasks: list[Task] = []
        for i, spec in enumerate(specs):
            title, description, tool_hint, cost, risk = spec
            task = Task(
                title          = title,
                description    = description,
                tool_hint      = tool_hint,
                estimated_cost = cost,
                risk_level     = risk,
                dependencies   = [tasks[i-1].task_id] if i > 0 else [],
            )
            tasks.append(task)
        return tasks

    @staticmethod
    def _parse_llm_output(raw: list) -> list:
        """
        Convert LLM output (list of dicts) to internal spec tuples.
        Validates each dict and falls back gracefully.
        """
        specs = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            try:
                risk = RiskLevel(item.get("risk_level", "low"))
            except ValueError:
                risk = RiskLevel.MEDIUM
            specs.append((
                str(item.get("title", "Task")),
                str(item.get("description", "")),
                str(item.get("tool_hint", "")),
                float(item.get("estimated_cost", 1.0)),
                risk,
            ))
        return specs if specs else list(_GENERIC_TEMPLATE)
