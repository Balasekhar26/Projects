"""Planning Stack Router (Program 5G-1).

Exposes REST endpoints for goal configuration, dependency paths, and status tracking.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.core.planning.goal import Goal, GoalRegistry

router = APIRouter(prefix="/planning", tags=["Planning"])

# Single in-memory GoalRegistry instance for the API router lifecycle
_registry = GoalRegistry()


class GoalConfig(BaseModel):
    goal_id: str = Field(..., description="Unique Goal ID")
    name: str = Field(..., description="Goal name")
    priority: Optional[str] = Field("Medium", description="Goal priority")
    deadline: Optional[float] = Field(None, description="Epoch deadline timestamp")
    importance: Optional[float] = Field(1.0, description="Goal importance weight")
    constraints: Optional[List[str]] = Field(None, description="Plan constraint flags")
    dependencies: Optional[List[str]] = Field(None, description="Goal parent dependencies")
    owner: Optional[str] = Field(None, description="Target execution owner agent")
    reward: Optional[float] = Field(100.0, description="Utility success payoff")
    failure_cost: Optional[float] = Field(-50.0, description="Utility failure cost penalty")


class UpdateGoalStatusRequest(BaseModel):
    status: str = Field(..., description="New status value (Pending, InProgress, Completed, Failed)")


@router.post("/goals", summary="Register a target goal")
def register_goal(req: GoalConfig) -> Dict[str, Any]:
    """Registers a goal in the planning registry, checking for cycles and dependency validity."""
    try:
        goal = Goal(
            goal_id=req.goal_id,
            name=req.name,
            priority=req.priority or "Medium",
            deadline=req.deadline,
            importance=req.importance or 1.0,
            constraints=req.constraints or [],
            dependencies=req.dependencies or [],
            owner=req.owner,
            reward=req.reward or 100.0,
            failure_cost=req.failure_cost or -50.0,
        )
        _registry.register_goal(goal)
        return {"status": "ok", "goal_id": goal.goal_id}
    except ValueError as val_exc:
        raise HTTPException(status_code=400, detail=str(val_exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/goals", summary="List registered goals")
def list_goals() -> Dict[str, Any]:
    """Lists all registered goals along with their current execution status."""
    goals = _registry.list_goals()
    return {
        "status": "ok",
        "goals": [
            {
                "goal_id": g.goal_id,
                "name": g.name,
                "priority": g.priority,
                "deadline": g.deadline,
                "importance": g.importance,
                "constraints": g.constraints,
                "dependencies": g.dependencies,
                "owner": g.owner,
                "status": g.status,
                "reward": g.reward,
                "failure_cost": g.failure_cost,
            }
            for g in goals
        ]
    }


@router.put("/goals/{goal_id}/status", summary="Update goal execution status")
def update_goal_status(goal_id: str, req: UpdateGoalStatusRequest) -> Dict[str, Any]:
    """Updates the status of a target registered goal."""
    try:
        _registry.update_goal_status(goal_id, req.status)
        return {"status": "ok", "goal_id": goal_id, "new_status": req.status}
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Goal '{goal_id}' not found.")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/goals/order", summary="Get topological planning order")
def get_planning_order() -> Dict[str, Any]:
    """Resolves goal dependencies and returns topologically sorted Goal IDs."""
    try:
        order = _registry.get_topological_order()
        return {"status": "ok", "topological_order": order}
    except ValueError as val_exc:
        raise HTTPException(status_code=400, detail=str(val_exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/goals/trace", summary="Get dependency visualizer trace")
def get_dependency_trace() -> Dict[str, Any]:
    """Returns a formatted markdown trace detailing goal dependencies and statuses."""
    try:
        trace = _registry.generate_dependency_trace()
        return {"status": "ok", "trace": trace}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# HTN Planner Endpoints (Program 5G-2)
# ---------------------------------------------------------------------------

class CreatePlanRequest(BaseModel):
    goal_id: str
    initial_variables: Dict[str, Any] = Field(default_factory=dict, description="Initial state variables context")
    methods: List[Dict[str, Any]] = Field(..., description="List of registered decomposition methods")
    operators: List[Dict[str, Any]] = Field(..., description="List of registered primitive actions")


class ValidatePlanRequest(BaseModel):
    plan: Dict[str, Any] = Field(..., description="Plan object to validate")
    initial_variables: Dict[str, Any] = Field(..., description="Initial state variables context")


# In-memory plan store
_plans: Dict[str, Plan] = {}


@router.post("/plan", summary="Generate a plan for a goal")
def generate_plan(req: CreatePlanRequest) -> Dict[str, Any]:
    """Generates an HTN plan for the target registered goal using methods and operators."""
    goal = _registry.get_goal(req.goal_id)
    if not goal:
        raise HTTPException(status_code=404, detail=f"Goal '{req.goal_id}' not found.")

    try:
        from backend.core.planning.planner import HTNPlanner
        from backend.core.planning.task import PlannerState, Operator, Method

        planner = HTNPlanner()

        # Register Operators
        for op_data in req.operators:
            op = Operator(
                operator_id=op_data["operator_id"],
                name=op_data["name"],
                parameters=op_data.get("parameters", {}),
                preconditions=op_data.get("preconditions", {}),
                effects=op_data.get("effects", {}),
                estimated_cost=float(op_data.get("estimated_cost", 1.0)),
                estimated_time=float(op_data.get("estimated_time", 1.0)),
            )
            planner.register_operator(op)

        # Register Methods
        for m_data in req.methods:
            m = Method(
                method_id=m_data["method_id"],
                task_name=m_data["task_name"],
                subtasks=m_data["subtasks"],
                preconditions=m_data.get("preconditions", {}),
            )
            planner.register_method(m)

        state = PlannerState(current_goal=req.goal_id, variables=req.initial_variables)
        plan = planner.find_plan(goal, state)

        if not plan:
            raise HTTPException(status_code=400, detail="No valid HTN plan found for this goal.")

        _plans[plan.plan_id] = plan
        return {
            "status": "ok",
            "plan_id": plan.plan_id,
            "steps": [
                {
                    "operator_id": op.operator_id,
                    "name": op.name,
                    "parameters": op.parameters,
                    "preconditions": op.preconditions,
                    "effects": op.effects,
                }
                for op in plan.steps
            ],
            "metrics": {
                "expected_cost": plan.expected_cost,
                "expected_duration": plan.expected_duration,
                "reward": plan.expected_reward,
                "risk": plan.expected_risk,
                "confidence": plan.confidence,
            }
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/validate", summary="Validate a candidate plan")
def validate_plan(req: ValidatePlanRequest) -> Dict[str, Any]:
    """Validates plan preconditions, constraints, and dependencies before scheduling."""
    try:
        from backend.core.planning.planner import PlanValidator
        from backend.core.planning.task import Plan, Operator

        steps = []
        for step in req.plan.get("steps", []):
            steps.append(Operator(
                operator_id=step["operator_id"],
                name=step["name"],
                parameters=step.get("parameters", {}),
                preconditions=step.get("preconditions", {}),
                effects=step.get("effects", {}),
            ))

        plan = Plan(
            plan_id=req.plan.get("plan_id", "test_plan"),
            goal_id=req.plan.get("goal_id", "test_goal"),
            steps=steps,
        )

        success, errors = PlanValidator.validate_plan(plan, req.initial_variables)
        return {
            "status": "ok",
            "valid": success,
            "validation_errors": errors,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/plans/{plan_id}", summary="Retrieve plan details")
def get_plan(plan_id: str) -> Dict[str, Any]:
    """Retrieves metadata and steps for a previously compiled plan."""
    plan = _plans.get(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail=f"Plan '{plan_id}' not found.")
    return {
        "status": "ok",
        "plan_id": plan.plan_id,
        "goal_id": plan.goal_id,
        "steps_count": len(plan.steps),
        "status": plan.status,
    }


@router.post("/plans/{plan_id}/cancel", summary="Cancel a compiled plan")
def cancel_plan(plan_id: str) -> Dict[str, Any]:
    """Cancels/retracts a plan from the active queue."""
    if plan_id not in _plans:
        raise HTTPException(status_code=404, detail=f"Plan '{plan_id}' not found.")
    _plans[plan_id].status = "Cancelled"
    return {"status": "ok", "plan_id": plan_id, "new_status": "Cancelled"}


# ---------------------------------------------------------------------------
# Plan Graph Builder Endpoints (Program 5G-3)
# ---------------------------------------------------------------------------

class CompileGraphRequest(BaseModel):
    plan_id: str
    steps: List[Dict[str, Any]] = Field(..., description="Linear plan steps sequence")


@router.post("/plan/compile", summary="Compile a plan to a DependencyGraph DAG")
def compile_plan_to_graph_endpoint(req: CompileGraphRequest) -> Dict[str, Any]:
    """Parses linear sequence plan and compiles it to a DependencyGraph DAG with parallel execution layers."""
    try:
        from backend.core.planning.plan_graph import PlanCompiler
        from backend.core.planning.task import Plan, Operator

        steps = []
        for step in req.steps:
            steps.append(Operator(
                operator_id=step["operator_id"],
                name=step["name"],
                parameters=step.get("parameters", {}),
                preconditions=step.get("preconditions", {}),
                effects=step.get("effects", {}),
            ))

        plan = Plan(
            plan_id=req.plan_id,
            goal_id="unknown_goal",
            steps=steps,
        )

        graph = PlanCompiler.compile_plan_to_graph(plan)
        layers = graph.get_parallel_layers()

        return {
            "status": "ok",
            "plan_id": req.plan_id,
            "graph": graph.to_json(),
            "parallel_layers": layers,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/plan/viz", summary="Get Graphviz visualization of a plan graph")
def visualize_plan_graph(req: CompileGraphRequest) -> Dict[str, Any]:
    """Compiles a plan and returns its Graphviz DOT representation."""
    try:
        from backend.core.planning.plan_graph import PlanCompiler
        from backend.core.planning.task import Plan, Operator

        steps = []
        for step in req.steps:
            steps.append(Operator(
                operator_id=step["operator_id"],
                name=step["name"],
                parameters=step.get("parameters", {}),
                preconditions=step.get("preconditions", {}),
                effects=step.get("effects", {}),
            ))

        plan = Plan(
            plan_id=req.plan_id,
            goal_id="unknown_goal",
            steps=steps,
        )

        graph = PlanCompiler.compile_plan_to_graph(plan)
        dot_str = graph.to_graphviz()

        return {
            "status": "ok",
            "graphviz_dot": dot_str,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Constraint Engine Endpoints (Program 5G-4)
# ---------------------------------------------------------------------------

class ValidateConstraintsRequest(BaseModel):
    plan_id: str
    steps: List[Dict[str, Any]] = Field(..., description="Linear plan steps sequence")
    world_state: Dict[str, Any] = Field(..., description="Active world state context variables")


class EnableValidatorRequest(BaseModel):
    validator_id: str
    enabled: bool


@router.post("/constraints/validate", summary="Validate plan graph constraints")
def validate_plan_constraints(req: ValidateConstraintsRequest) -> Dict[str, Any]:
    """Compiles the plan to a DAG and runs all enabled constraint validation checks."""
    try:
        from backend.core.planning.plan_graph import PlanCompiler
        from backend.core.planning.task import Plan, Operator
        from backend.core.planning.constraints.engine import ConstraintEngine

        steps = []
        for step in req.steps:
            steps.append(Operator(
                operator_id=step["operator_id"],
                name=step["name"],
                parameters=step.get("parameters", {}),
                preconditions=step.get("preconditions", {}),
                effects=step.get("effects", {}),
            ))

        plan = Plan(
            plan_id=req.plan_id,
            goal_id="unknown_goal",
            steps=steps,
        )

        graph = PlanCompiler.compile_plan_to_graph(plan)
        engine = ConstraintEngine.get_instance()
        report = engine.validate(graph, req.world_state)

        return {
            "status": "ok",
            "passed": report.passed,
            "violations": [
                {
                    "constraint_id": v.constraint_id,
                    "node_id": v.node_id,
                    "explanation": v.explanation,
                    "severity": v.severity,
                    "suggested_fix": v.suggested_fix,
                }
                for v in report.violations
            ],
            "warnings": [
                {
                    "constraint_id": w.constraint_id,
                    "node_id": w.node_id,
                    "explanation": w.explanation,
                    "severity": w.severity,
                    "suggested_fix": w.suggested_fix,
                }
                for w in report.warnings
            ],
            "metrics": report.metrics,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/constraints/repair", summary="Get suggested fixes for plan violations")
def get_constraint_repairs(req: ValidateConstraintsRequest) -> Dict[str, Any]:
    """Compiles plan to DAG, runs constraints, and compiles unique repair suggestions."""
    try:
        from backend.core.planning.plan_graph import PlanCompiler
        from backend.core.planning.task import Plan, Operator
        from backend.core.planning.constraints.engine import ConstraintEngine

        steps = []
        for step in req.steps:
            steps.append(Operator(
                operator_id=step["operator_id"],
                name=step["name"],
                parameters=step.get("parameters", {}),
                preconditions=step.get("preconditions", {}),
                effects=step.get("effects", {}),
            ))

        plan = Plan(
            plan_id=req.plan_id,
            goal_id="unknown_goal",
            steps=steps,
        )

        graph = PlanCompiler.compile_plan_to_graph(plan)
        engine = ConstraintEngine.get_instance()
        report = engine.validate(graph, req.world_state)
        repairs = engine.get_repair_suggestions(report)

        return {
            "status": "ok",
            "passed": report.passed,
            "suggested_repairs": repairs,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/constraints/types", summary="Get list of registered validators")
def get_validator_types() -> Dict[str, Any]:
    """Returns the ID, name, and enable status of all registered validators."""
    try:
        from backend.core.planning.constraints.engine import ConstraintEngine
        engine = ConstraintEngine.get_instance()
        return {
            "status": "ok",
            "validators": engine.get_validators(),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/constraints/enable", summary="Enable/disable a validator")
def enable_constraint_validator(req: EnableValidatorRequest) -> Dict[str, Any]:
    """Enables or disables a target constraint validator dynamically at runtime."""
    try:
        from backend.core.planning.constraints.engine import ConstraintEngine
        engine = ConstraintEngine.get_instance()
        if req.enabled:
            engine.enable_validator(req.validator_id)
        else:
            engine.disable_validator(req.validator_id)

        return {
            "status": "ok",
            "validator_id": req.validator_id,
            "enabled": req.enabled,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))



