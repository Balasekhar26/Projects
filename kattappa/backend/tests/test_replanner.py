import pytest
import os
import tempfile
from pathlib import Path
from backend.core.orchestrator.base import Task, TaskResult, BaseAgent
from backend.core.orchestrator.task_graph import TaskGraph
from backend.core.orchestrator.scheduler import TaskScheduler
from backend.core.orchestrator.registry import AgentRegistry
from backend.core.orchestrator.replanner import FailureReplanner

# Custom mock agent for testing failure replan execution
class FailingAgent(BaseAgent):
    def __init__(self, name: str = "FailingAgent"):
        self.call_count = 0
        self._name = name
        
    @property
    def name(self) -> str:
        return self._name

    def initialize(self) -> None:
        pass

    def execute(self, task: Task, context) -> TaskResult:
        self.call_count += 1
        if task.action == "INSTALL":
            if self.call_count == 1:
                # Fail the first attempt to trigger retry and replan
                return TaskResult(success=False, error="Pip install failed: no virtualenv active")
            else:
                # Succeed after recovery has executed
                return TaskResult(success=True, output="Successfully installed package")
        elif task.action == "RUN_SHELL":
            # Recovery task execution
            return TaskResult(success=True, output="Created virtualenv")
        return TaskResult(success=True)

    def terminate(self, task_id: str) -> None:
        pass

@pytest.fixture
def test_env_setup(monkeypatch):
    temp_dir = tempfile.mkdtemp(prefix="replanner_test_")
    monkeypatch.setenv("KATTAPPA_ROOT", temp_dir)
    monkeypatch.setenv("KATTAPPA_TEST_MODE", "true")
    monkeypatch.setenv("KATTAPPA_ENV", "test")
    yield temp_dir

def test_replanner_dynamic_graph_mutation(test_env_setup) -> None:
    graph = TaskGraph()
    graph.goal = "Setup and run flask app"
    
    t1 = Task(
        task_id="t1",
        agent_name="FailingAgent",
        action="INSTALL",
        params={"package": "flask"},
        dependencies=[]
    )
    t1.max_attempts = 1  # force direct replanning on first failure after exhaustion
    graph.add_task(t1)
    
    # 1. Directly invoke analyzer to verify graph mutation
    replan_ok = FailureReplanner.analyze_and_replan(
        graph=graph,
        failed_task=t1,
        error_msg="pip install failed: no virtualenv active",
        context={}
    )
    
    assert replan_ok is True
    
    # Verify corrective task was injected
    recovery_tasks = [tid for tid in graph.tasks if tid.startswith("recover_venv_t1")]
    assert len(recovery_tasks) == 1
    recovery_task_id = recovery_tasks[0]
    
    rec_task = graph.tasks[recovery_task_id]
    assert rec_task.action == "RUN_SHELL"
    assert rec_task.status == "PENDING"
    
    # Verify dependencies are mapped correctly
    assert t1.dependencies == [recovery_task_id]
    assert rec_task.dependencies == []
    
    # Verify failed task state reset
    assert t1.status == "PENDING"
    assert t1.retry_count == 0

def test_scheduler_replanning_loop(test_env_setup) -> None:
    registry = AgentRegistry()
    agent = FailingAgent("FailingAgent")
    tool_exec = FailingAgent("Tool Executor")
    registry.register(agent)
    registry.register(tool_exec)
    
    scheduler = TaskScheduler(registry=registry)
    
    graph = TaskGraph()
    graph.goal = "Setup project dependencies"
    
    t1 = Task(
        task_id="t1",
        agent_name="FailingAgent",
        action="INSTALL",
        params={"package": "flask"},
        dependencies=[]
    )
    t1.max_attempts = 1  # trigger replan on first attempt failure
    graph.add_task(t1)
    
    # Run the scheduler
    context = scheduler.run_graph(graph, graph_id="test_run_1")
    
    # Verify the entire graph completed successfully
    assert graph.is_finished() is True
    assert graph.has_failures() is False
    
    # Verify execution order:
    # 1. failing agent called for t1 (attempt 1) -> fails
    # 2. replanner runs -> injects recovery task (recover_venv_t1)
    # 3. recovery task runs -> succeeds (run_shell on tool_exec)
    # 4. t1 runs again (attempt 2) -> succeeds
    assert agent.call_count == 2
    assert tool_exec.call_count == 1
    
    assert graph.tasks["t1"].status == "COMPLETED"
    assert any(tid.startswith("recover_venv_t1") and t.status == "COMPLETED" for tid, t in graph.tasks.items())
