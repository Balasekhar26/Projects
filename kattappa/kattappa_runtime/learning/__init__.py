"""
Kattappa Learning Engine — Step 22
====================================
Converts Reflections into durable, structured knowledge records.

Pipeline position:
    ReflectionEngine → LearningEngine → SkillMemory / SemanticMemory

Public API:
    from kattappa_runtime.learning import LearningEngine, LearningRecord, RecordType

    engine = LearningEngine(memory_provider, skill_memory=skill_store)
    record = engine.learn_from(reflection)
"""

from kattappa_runtime.learning.engine import LearningEngine
from kattappa_runtime.learning.schema import LearningRecord, RecordType, LearningPriority
from kattappa_runtime.learning.store  import LearningStore

__all__ = [
    "LearningEngine",
    "LearningRecord",
    "RecordType",
    "LearningPriority",
    "LearningStore",
]
