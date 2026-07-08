from __future__ import annotations
import pytest
import time
from backend.core.orchestrator.base import Task, TaskResult, BaseAgent
from backend.core.orchestrator.context import SharedContext
from backend.core.orchestrator.message_bus import MessageBus
from backend.core.orchestrator.task_graph import TaskGraph
from backend.core.orchestrator.scheduler import TaskScheduler
from backend.core.orchestrator.registry import AgentRegistry

class MockTaskAgent(BaseAgent):
    def __init__(self, name: str, execution_time: float = 0.05, fail: bool = False):
        self._name = name
        self.execution_time = execution_time
        self.fail = fail
        self.initialize_called = False
        self.execute_called_with = []
        self.terminate_called_with = []

    @property
    def name(self) -> str:
        return self._name

    def initialize(self) -> None:
        self.initialize_called = True

    def execute(self, task: Task, context: SharedContext) -> TaskResult:
        self.execute_called_with.append(task.task_id)
        time.sleep(self.execution_time)
        if self.fail:
            return TaskResult(success=False, error="Mock execution failure")
        context.set(f"output_{task.task_id}", f"Result from {self.name}")
        return TaskResult(success=True, output=f"output_{task.task_id}")

    def terminate(self, task_id: str) -> None:
        self.terminate_called_with.append(task_id)


def test_task_graph_cycle_detection():
    graph = TaskGraph()
    task1 = Task("task1", "AgentA", "action1", {})
    task2 = Task("task2", "AgentB", "action2", {})
    graph.add_task(task1)
    graph.add_task(task2)
    
    graph.add_dependency("task2", "task1")
    assert "task1" in graph.dependencies["task2"]
    
    with pytest.raises(ValueError, match="Circular dependency"):
        graph.add_dependency("task1", "task2")


def test_message_bus():
    bus = MessageBus()
    received = []
    
    def cb(data):
        received.append(data)
        
    bus.subscribe("test/topic", cb)
    bus.publish("test/topic", "hello")
    assert received == ["hello"]


def test_shared_context():
    context = SharedContext({"a": 1})
    assert context.get("a") == 1
    context.set("b", 2)
    assert context.get("b") == 2
    assert context.to_dict() == {"a": 1, "b": 2}


def test_scheduler_dag_execution():
    registry = AgentRegistry()
    agent_a = MockTaskAgent("AgentA")
    agent_b = MockTaskAgent("AgentB")
    registry.register(agent_a)
    registry.register(agent_b)
    
    scheduler = TaskScheduler(registry=registry)
    graph = TaskGraph()
    task1 = Task("task1", "AgentA", "action1", {})
    task2 = Task("task2", "AgentB", "action2", {})
    graph.add_task(task1)
    graph.add_task(task2)
    graph.add_dependency("task2", "task1")
    
    context = scheduler.run_graph(graph, "test_graph_id")
    
    assert task1.status == "COMPLETED"
    assert task2.status == "COMPLETED"
    assert context.get("output_task1") == "Result from AgentA"
    assert context.get("output_task2") == "Result from AgentB"
    assert agent_a.execute_called_with == ["task1"]
    assert agent_b.execute_called_with == ["task2"]


def test_scheduler_retry_on_failure():
    registry = AgentRegistry()
    agent_a = MockTaskAgent("AgentA", fail=True)
    registry.register(agent_a)
    
    scheduler = TaskScheduler(registry=registry)
    graph = TaskGraph()
    task1 = Task("task1", "AgentA", "action1", {})
    task1.max_attempts = 2
    graph.add_task(task1)
    
    scheduler.run_graph(graph, "test_graph_failure")
    
    assert task1.status == "FAILED"
    assert task1.retry_count == 2
