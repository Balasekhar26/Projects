from enum import Enum


class EventType(Enum):
    GOAL_CREATED = "GoalCreated"
    INTENT_CLASSIFIED = "IntentClassified"
    MEMORY_RETRIEVED = "MemoryRetrieved"
    MEMORY_STORED = "MemoryStored"
    PLAN_GENERATED = "PlanGenerated"
    SIMULATION_STARTED = "SimulationStarted"
    SIMULATION_FINISHED = "SimulationFinished"
    DECISION_MADE = "DecisionMade"
    SAFETY_CHECKED = "SafetyChecked"
    BUDGET_ALLOCATED = "BudgetAllocated"
    TOOL_REQUESTED = "ToolRequested"
    TOOL_STARTED = "ToolStarted"
    TOOL_COMPLETED = "ToolCompleted"
    TOOL_FAILED = "ToolFailed"
    OBSERVATION_RECORDED = "ObservationRecorded"
    REFLECTION_GENERATED = "ReflectionGenerated"
    LEARNING_RECORDED = "LearningRecorded"
    INTERRUPT_RAISED = "InterruptRaised"
    INTERRUPT_HANDLED = "InterruptHandled"
    EXECUTION_COMPLETED = "ExecutionCompleted"
    EXECUTION_CANCELLED = "ExecutionCancelled"
    # Program 4: World State & Event System
    STATE_TRANSITIONED = "StateTransitioned"
    WORLD_SNAPSHOT_TAKEN = "WorldSnapshotTaken"
    # Program 3: MCE integration
    MCE_CYCLE_COMPLETED = "MceCycleCompleted"
    # Program 2: ECL integration
    ECL_GOAL_DECOMPOSED = "EclGoalDecomposed"
    ECL_PLAN_EXECUTED = "EclPlanExecuted"

