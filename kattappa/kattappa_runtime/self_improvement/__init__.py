"""
Kattappa Self-Improvement Engine — Step 25
==========================================
Analyses accumulated failures and generates prioritised improvement plans.

Pipeline position:
    MistakeLog + LearningStore + SkillMemory + ResearchEngine
        → PatternMiner → ImprovementGoal[] → GoalStore

Public API:
    from kattappa_runtime.self_improvement import SelfImprovementEngine

    engine = SelfImprovementEngine(
        mistake_log=mistake_log,
        learning_store=learning_store,
        skill_memory=skill_memory,
        research_engine=research_engine,
    )
    goals = engine.analyse()
    print(engine.weakness_report())
"""

from kattappa_runtime.self_improvement.engine       import SelfImprovementEngine
from kattappa_runtime.self_improvement.schema       import (
    ImprovementGoal, DomainWeakness,
    ImprovementPriority, GoalStatus
)
from kattappa_runtime.self_improvement.store        import GoalStore
from kattappa_runtime.self_improvement.pattern_miner import PatternMiner

__all__ = [
    "SelfImprovementEngine",
    "ImprovementGoal",
    "DomainWeakness",
    "ImprovementPriority",
    "GoalStatus",
    "GoalStore",
    "PatternMiner",
]
