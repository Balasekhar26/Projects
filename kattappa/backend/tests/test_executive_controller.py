import time
from backend.core.cos.executive_controller import (
    ExecutiveController,
    Interrupt,
    InterruptType,
    Budget,
)
from backend.core.orchestrator.base import Task

def test_executive_controller_singleton():
    ec1 = ExecutiveController()
    ec2 = ExecutiveController()
    assert ec1 is ec2

def test_allocate_budget():
    ec = ExecutiveController()
    # High complexity
    t_high = Task(task_id="t1", agent_name="reasoning", action="execute", params={"complexity": "high"})
    b_high = ec.allocate_budget(t_high)
    assert b_high.max_latency_seconds == 10.0
    assert b_high.max_tokens == 4000

    # Low complexity
    t_low = Task(task_id="t2", agent_name="reasoning", action="execute", params={"complexity": "low"})
    b_low = ec.allocate_budget(t_low)
    assert b_low.max_latency_seconds == 2.0
    assert b_low.max_tokens == 1000

    # Normal complexity (default)
    t_normal = Task(task_id="t3", agent_name="reasoning", action="execute", params={})
    b_normal = ec.allocate_budget(t_normal)
    assert b_normal.max_latency_seconds == 5.0
    assert b_normal.max_tokens == 2000

def test_sequential_stages():
    ec = ExecutiveController()
    # Clear any previous handlers/interrupts
    ec._stage_handlers = {k: [] for k in ec._stage_handlers}
    ec._active_interrupts.clear()

    execution_order = []

    def make_handler(name):
        return lambda: execution_order.append(name)

    for stage in ["learn", "act", "plan", "reason", "retrieve", "perceive"]:
        ec.register_stage_handler(stage, make_handler(stage))

    # Trigger process_tick
    ec.process_tick()

    # The expected execution order of stages is: perceive -> retrieve -> reason -> plan -> act -> learn
    assert execution_order == ["perceive", "retrieve", "reason", "plan", "act", "learn"]

def test_interrupt_handling():
    ec = ExecutiveController()
    ec._stage_handlers = {k: [] for k in ec._stage_handlers}
    ec._active_interrupts.clear()
    ec._interrupt_handlers.clear()

    stage_run = False
    def stage_handler():
        nonlocal stage_run
        stage_run = True

    ec.register_stage_handler("perceive", stage_handler)

    handled_interrupt = None
    def interrupt_handler(intr):
        nonlocal handled_interrupt
        handled_interrupt = intr

    ec.register_interrupt_handler(InterruptType.SAFETY_VIOLATION, interrupt_handler)

    # Trigger safety violation interrupt
    violation = Interrupt(
        type=InterruptType.SAFETY_VIOLATION,
        priority=100,
        message="Safety fence boundary crossed"
    )
    ec.trigger_interrupt(violation)

    # When process_tick runs, it should execute the interrupt handler first and skip stage processing
    ec.process_tick()

    assert handled_interrupt is violation
    assert not stage_run

def test_controller_loop_execution():
    ec = ExecutiveController()
    ec._stage_handlers = {k: [] for k in ec._stage_handlers}
    ec._active_interrupts.clear()

    tick_count = 0
    def tick_handler():
        nonlocal tick_count
        tick_count += 1

    ec.register_stage_handler("perceive", tick_handler)

    # Start loop with a fast tick rate for testing
    ec.start(tick_rate_ms=20)
    try:
        time.sleep(0.1)
        assert tick_count > 0
    finally:
        ec.stop()
