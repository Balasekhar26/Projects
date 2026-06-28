"""MemoryKeeperAgent — Phase K8.

Routes all memory reads and writes through CognitiveMemoryBus instead of
calling individual memory modules directly.
"""
from __future__ import annotations

from backend.core.orchestrator.base import BaseAgent, Task, TaskResult
from backend.core.orchestrator.context import SharedContext
from backend.core.logger import log_event


class MemoryKeeperAgent(BaseAgent):
    @property
    def name(self) -> str:
        return "Memory Keeper"

    def initialize(self) -> None:
        pass

    def execute(self, task: Task, context: SharedContext) -> TaskResult:
        log_event("memory_keeper_exec", "MemoryKeeperAgent executing via CognitiveMemoryBus")

        action = task.params.get("action", "read")
        memory_type = task.params.get("memory_type")
        query = task.params.get("query") or context.get("memory_query") or ""

        try:
            from backend.core.cognitive_memory_bus import MEMORY_BUS

            if action == "write":
                data = task.params.get("data", {})
                if not memory_type:
                    return TaskResult(success=False, error="memory_type required for write")
                confidence = task.params.get("confidence", 1.0)
                verified = task.params.get("verified", False)
                result = MEMORY_BUS.write(
                    memory_type=memory_type,
                    data=data,
                    confidence=confidence,
                    verified=verified,
                )
                if result.success:
                    context.set("memory_write_id", result.record_id)
                    return TaskResult(success=True, output={"record_id": result.record_id})
                return TaskResult(success=False, error=result.reason)

            else:  # read
                memory_types = (
                    [memory_type] if memory_type
                    else ["working", "episodic", "semantic", "knowledge_graph"]
                )
                session_id = task.params.get("session_id") or context.get("chat_session_id")
                results = MEMORY_BUS.read(
                    query=query,
                    memory_types=memory_types,
                    session_id=session_id,
                    limit=task.params.get("limit", 10),
                )
                combined: list[dict] = []
                for r in results:
                    combined.extend(r.records)
                context.set("memory_results", combined)
                return TaskResult(success=True, output=combined)

        except Exception as e:
            log_event("memory_keeper_error", str(e))
            return TaskResult(success=False, error=str(e))

    def terminate(self, task_id: str) -> None:
        pass
