from fastapi import APIRouter, HTTPException, Query, Body
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional
from backend.core.ecl.coordinator import ECLCoordinator
from backend.core.ecl.goal_decomposer import ECLGoalDecomposer
from backend.core.ecl.simulation_runner import ECLSimulationRunner

ecl_router = APIRouter(tags=["ECL"])

class DecomposeRequest(BaseModel):
    title: str = Field(..., description="High-level goal title")
    description: str = Field("", description="Optional details of the goal")

class EvaluateRequest(BaseModel):
    title: str = Field(..., description="Goal title")
    tasks: List[Dict[str, Any]] = Field(..., description="List of plan task steps")

class ExecuteRequest(BaseModel):
    title: str = Field(..., description="High-level goal title")
    description: str = Field("", description="Optional details of the goal")
    priority: str = Field("MEDIUM", description="Task priority (LOW, MEDIUM, HIGH)")

@ecl_router.post("/ecl/decompose")
def decompose_goal(request: DecomposeRequest) -> Dict[str, Any]:
    """Decomposes a high-level goal into structured subgoals and tasks."""
    try:
        return ECLGoalDecomposer.decompose(request.title, request.description)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

@ecl_router.post("/ecl/evaluate")
def evaluate_plan(request: EvaluateRequest) -> Dict[str, Any]:
    """Evaluates a plan candidate via counterfactual branch simulation."""
    try:
        return ECLSimulationRunner.evaluate_viability(request.title, request.tasks)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

@ecl_router.post("/ecl/execute")
def execute_ecl_transaction(request: ExecuteRequest) -> Dict[str, Any]:
    """Orchestrates goal decomposition, budgeting, policy checks, simulations, and scheduling."""
    try:
        res = ECLCoordinator.plan_and_execute(
            goal_title=request.title,
            goal_desc=request.description,
            priority=request.priority
        )
        return res
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

@ecl_router.get("/ecl/status")
def get_ecl_status() -> Dict[str, Any]:
    """Returns general status and policies of the ECL router and budget limits."""
    from backend.core.ecl.budget_manager import ECLBudgetManager
    from backend.core.ecl.router import ECLRouter
    return {
        "status": "ACTIVE",
        "active_policies": ["unverified_deletion_block", "self_modification_halt", "network_isolation_check"],
        "default_budgets": {
            "low": ECLBudgetManager.calculate_budget("LOW"),
            "medium": ECLBudgetManager.calculate_budget("MEDIUM"),
            "high": ECLBudgetManager.calculate_budget("HIGH")
        },
        "default_routes": {
            "code_sample": ECLRouter.route_task("write python code"),
            "reason_sample": ECLRouter.route_task("explain how quantum physics works"),
            "general_sample": ECLRouter.route_task("say hello")
        }
    }
