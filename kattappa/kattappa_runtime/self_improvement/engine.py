"""
Self-Improvement Engine — Step 25 Core
=======================================

The engine that closes the loop: analyses accumulated mistakes,
detects domain weaknesses, generates ImprovementGoals with concrete
action plans, and optionally triggers targeted research.

Full cognitive pipeline position:

    MistakeLog (Step 21) ─────────────────────────────┐
    LearningStore (Step 22) ─ SKILL_GAP records ──────│
    SkillMemory (Step 23) ─ attempts/success rates ───│
    ResearchStore (Step 24) ─ prior research topics ──┘
                            ↓
                    PatternMiner
                            ↓
                    DomainWeakness[]
                            ↓
                SelfImprovementEngine
                            ↓
                    ImprovementGoal[]
                            ↓
             ┌──────────────┴──────────────┐
             │                             │
         GoalStore                  ResearchEngine   ← optional trigger
             │                       (targeted study)
         Priority Queue

Public API
----------
    from kattappa_runtime.self_improvement import SelfImprovementEngine

    engine = SelfImprovementEngine(
        mistake_log=mistake_log,
        learning_store=learning_store,
        skill_memory=skill_memory,
        research_engine=research_engine,  # optional
    )
    goals = engine.analyse()
    print(engine.weakness_report())
"""

from __future__ import annotations

from typing import List, Optional, TYPE_CHECKING

from kattappa_runtime.reflection.mistake_log         import MistakeLog
from kattappa_runtime.learning.store                 import LearningStore
from kattappa_runtime.learning.schema                import RecordType
from kattappa_runtime.self_improvement.schema        import (
    ImprovementGoal, DomainWeakness, ImprovementPriority, GoalStatus
)
from kattappa_runtime.self_improvement.pattern_miner import PatternMiner
from kattappa_runtime.self_improvement.store         import GoalStore

if TYPE_CHECKING:
    from kattappa_runtime.skill_memory.store   import SkillMemory
    from kattappa_runtime.research.engine      import ResearchEngine

# Weakness score thresholds → priority mapping
_PRIORITY_THRESHOLDS = [
    (0.75, ImprovementPriority.CRITICAL),
    (0.55, ImprovementPriority.HIGH),
    (0.35, ImprovementPriority.MEDIUM),
    (0.00, ImprovementPriority.LOW),
]

# Action templates per domain category (rule-based; LLM hook can replace)
_ACTION_TEMPLATES = {
    "default": [
        "Study core fundamentals of {domain}",
        "Review recent failure cases in {domain}",
        "Create 3 synthetic practice exercises for {domain}",
        "Research: {top_gap}",
        "Apply knowledge in a controlled test task",
    ],
    "translation": [
        "Review tokenization failures for {domain}",
        "Analyse low-fertility sentences",
        "Generate bilingual synthetic pairs for: {top_gap}",
        "Run translation eval on test set",
    ],
    "code": [
        "Review failing code patterns in {domain}",
        "Study: {top_gap}",
        "Write unit tests for the failing scenario",
        "Refactor and re-test",
    ],
    "rf_systems": [
        "Study Smith Chart and impedance matching fundamentals",
        "Research: {top_gap}",
        "Work through a real RF circuit calculation problem",
        "Review antenna gain and RSSI formulas",
    ],
    "reasoning": [
        "Analyse logical failure patterns in {domain}",
        "Study chain-of-thought decomposition techniques",
        "Research: {top_gap}",
        "Practice step-by-step problem breakdown on 5 examples",
    ],
}


class SelfImprovementEngine:
    """
    Analyses accumulated mistakes and generates prioritised improvement plans.

    Parameters
    ----------
    mistake_log : MistakeLog
        Source of all failure/partial reflections (Step 21).
    learning_store : LearningStore
        Source of SKILL_GAP records (Step 22).
    skill_memory : SkillMemory | None
        For authoritative attempt/success_rate data (Step 23).
    research_engine : ResearchEngine | None
        If provided, HIGH/CRITICAL goals trigger targeted research (Step 24).
    goal_store : GoalStore | None
        Custom store for testing.
    action_generator : callable | None
        LLM hook: receives DomainWeakness, returns List[str] of actions.
    """

    def __init__(
        self,
        mistake_log:       MistakeLog,
        learning_store:    LearningStore,
        skill_memory:      Optional["SkillMemory"]   = None,
        research_engine:   Optional["ResearchEngine"] = None,
        goal_store:        Optional[GoalStore]        = None,
        action_generator:  Optional[callable]         = None,
    ):
        self.mistakes        = mistake_log
        self.learning        = learning_store
        self.skill_mem       = skill_memory
        self.research        = research_engine
        self.store           = goal_store or GoalStore()
        self._action_gen     = action_generator
        self._miner          = PatternMiner(skill_memory=skill_memory)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyse(self) -> List[ImprovementGoal]:
        """
        Run the full self-improvement analysis cycle.

        1. Load all mistakes from MistakeLog
        2. Load SKILL_GAP records from LearningStore
        3. Mine patterns → DomainWeakness[]
        4. Generate ImprovementGoals for new weaknesses
        5. Optionally trigger research for CRITICAL/HIGH goals
        6. Return all generated goals (this run only)

        Returns
        -------
        List[ImprovementGoal]
            Newly created goals from this analysis run, priority-sorted.
        """
        # 1. Load inputs
        all_mistakes = self.mistakes.load_all()
        skill_gaps   = self.learning.get_by_type(RecordType.SKILL_GAP)

        if not all_mistakes:
            return []

        # 2. Mine patterns
        weaknesses = self._miner.mine(all_mistakes, skill_gaps)

        # 3. Generate goals (skip domains that already have open goals)
        new_goals: List[ImprovementGoal] = []
        for weakness in weaknesses:
            if self.store.exists_for_domain(weakness.domain):
                continue
            goal = self._generate_goal(weakness)
            self.store.save(goal)
            new_goals.append(goal)

        # 4. Trigger research for urgent goals
        if self.research is not None:
            for goal in new_goals:
                if goal.priority in (ImprovementPriority.CRITICAL, ImprovementPriority.HIGH):
                    self._trigger_research(goal, weaknesses)

        return sorted(new_goals, key=lambda g: self._priority_rank(g.priority))

    def priority_queue(self) -> List[ImprovementGoal]:
        """Return all open/in-progress goals, highest priority first."""
        return self.store.get_priority_queue()

    def weakness_report(self) -> str:
        """
        Human-readable weakness report across all tracked domains.

        Example output:
            ╔══ Self-Improvement Report ══╗
            Domain: rf_systems
              Weakness Score : 0.82 (CRITICAL)
              Failures       : 10 / 15 attempts (66.7%)
              Top Gaps       : impedance matching, smith chart
              Status         : OPEN goal created
        """
        all_goals = self.store.get_all()
        if not all_goals:
            return "No improvement goals generated yet. Run analyse() first."

        lines = ["╔══ Self-Improvement Weakness Report ══╗"]
        for g in sorted(all_goals, key=lambda x: self._priority_rank(x.priority)):
            lines.append(f"\n  Domain    : {g.domain}")
            lines.append(f"  Priority  : {g.priority.value.upper()}")
            lines.append(f"  Problem   : {g.problem}")
            lines.append(f"  Root Cause: {g.root_cause}")
            lines.append(f"  Evidence  : {g.evidence_count} mistake(s)")
            lines.append(f"  Status    : {g.status.value}")
            if g.recommended_actions:
                lines.append("  Actions   :")
                for a in g.recommended_actions[:3]:
                    lines.append(f"    - {a}")
        lines.append("\n╚══════════════════════════════════════╝")
        return "\n".join(lines)

    def mark_goal_completed(self, goal_id: str, effectiveness: float = -1.0):
        """Mark a goal as completed and record effectiveness."""
        return self.store.mark_completed(goal_id, effectiveness)

    def get_goals_for_domain(self, domain: str) -> List[ImprovementGoal]:
        return self.store.get_by_domain(domain)

    # ------------------------------------------------------------------
    # Private — goal generation
    # ------------------------------------------------------------------

    def _generate_goal(self, w: DomainWeakness) -> ImprovementGoal:
        """Build an ImprovementGoal from a DomainWeakness."""
        priority = self._weakness_to_priority(w.weakness_score)

        # Root cause: most prominent knowledge gap, or top lesson
        root_cause = (
            w.top_knowledge_gaps[0] if w.top_knowledge_gaps
            else (w.top_lessons[0] if w.top_lessons else f"Recurring failures in {w.domain}")
        )

        # Problem description
        sr_pct = f"{w.failure_rate * 100:.0f}%"
        problem = (
            f"{w.domain} domain fails {sr_pct} of the time "
            f"({w.failure_count} failure(s) in {w.total_attempts} attempt(s))"
        )

        # Get success_rate_before from SkillMemory
        sr_before = -1.0
        if self.skill_mem:
            profile = self.skill_mem.get(w.domain)
            if profile:
                sr_before = profile.success_rate

        # Generate recommended actions
        actions = self._generate_actions(w)

        return ImprovementGoal(
            domain              = w.domain,
            problem             = problem,
            root_cause          = root_cause,
            evidence_count      = w.failure_count + w.partial_count,
            priority            = priority,
            recommended_actions = actions,
            status              = GoalStatus.OPEN,
            success_rate_before = sr_before,
        )

    def _generate_actions(self, w: DomainWeakness) -> List[str]:
        """Generate recommended actions. LLM hook overrides rule-based."""
        if self._action_gen:
            try:
                result = self._action_gen(w)
                if isinstance(result, list) and result:
                    return result[:6]
            except Exception:
                pass

        return self._rule_based_actions(w)

    def _rule_based_actions(self, w: DomainWeakness) -> List[str]:
        """Template-based action generation."""
        top_gap = w.top_knowledge_gaps[0] if w.top_knowledge_gaps else w.domain
        templates = _ACTION_TEMPLATES.get(w.domain, _ACTION_TEMPLATES["default"])

        actions = []
        for tmpl in templates[:5]:
            action = tmpl.format(domain=w.domain, top_gap=top_gap)
            actions.append(action)
        return actions

    # ------------------------------------------------------------------
    # Private — research trigger
    # ------------------------------------------------------------------

    def _trigger_research(self, goal: ImprovementGoal, weaknesses: List[DomainWeakness]) -> None:
        """Trigger ResearchEngine for the top knowledge gap in this goal."""
        topic = goal.root_cause[:100]
        try:
            self.research.research(
                topic  = topic,
                domain = goal.domain,
                notes  = f"triggered by improvement goal {goal.goal_id[:8]}",
            )
        except Exception:
            pass  # Research failure is non-fatal

    # ------------------------------------------------------------------
    # Static helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _weakness_to_priority(score: float) -> ImprovementPriority:
        for threshold, priority in _PRIORITY_THRESHOLDS:
            if score >= threshold:
                return priority
        return ImprovementPriority.LOW

    @staticmethod
    def _priority_rank(p: ImprovementPriority) -> int:
        return {"critical": 0, "high": 1, "medium": 2, "low": 3}[p.value]
