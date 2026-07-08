"""Partial Subtree Repair Replanner Engine (Program 12.4).
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional, Set

from backend.core.planning.plan import Plan
from backend.core.planning.plan_node import PlanNode
from backend.core.planning.goal_graph import GoalGraph
from backend.core.planning.planner_types import GoalStatus
from backend.core.planning.htn_planner import HTNPlanner
from backend.core.planning.failure_classifier import FailureClassifier, FailureCategory
from backend.core.planning.recovery_policy import RecoveryPolicyEngine, RecoveryAction
from backend.core.planning.replanning_events import (
    PlanRepairStartedEvent,
    PlanRepairSucceededEvent,
    PlanRepairFailedEvent,
    PlanAbortedEvent,
)
from backend.core.execution.typed_errors import ValidationError

logger = logging.getLogger(__name__)


class Replanner:
    """Manages failure classification, policy routing, and immutable partial plan subtree repairs."""

    def __init__(self, planner: HTNPlanner, max_attempts: int = 3) -> None:
        self.planner = planner
        self.policy_engine = RecoveryPolicyEngine(max_attempts_per_node=max_attempts)

    def handle_failure(
        self,
        plan: Plan,
        failed_node_id: str,
        error: Exception,
        world_state: Dict[str, Any],
        session_id: str = "default_session",
    ) -> Plan:
        """Processes a node execution failure, applying policy rules to return a repaired Plan or abort."""
        graph = plan.graph
        if failed_node_id not in graph.nodes:
            raise KeyError(f"Failed node '{failed_node_id}' not found in Plan graph.")

        failed_node = graph.nodes[failed_node_id]

        # 1. Classify failure
        category = FailureClassifier.classify(error)
        logger.warning(
            "Replanner intercepted node failure: %s (Category: %s)",
            failed_node.title,
            category.value,
        )

        # 2. Get recovery action
        action = self.policy_engine.get_recovery_action(failed_node_id, category)
        logger.info("Selected recovery policy action: %s", action.value)

        # 3. Handle Abort
        if action == RecoveryAction.ABORT:
            graph.set_status(failed_node_id, GoalStatus.FAILED, reason=str(error))
            self._emit_event(PlanAbortedEvent.create(plan.plan_id, reason=str(error), session_id=session_id))
            raise ValidationError(f"Plan execution aborted due to recovery policy limit: {error}")

        # 4. Handle Escalation
        if action == RecoveryAction.ESCALATE:
            graph.set_status(failed_node_id, GoalStatus.FAILED, reason=str(error))
            self._emit_event(PlanRepairFailedEvent.create(plan.plan_id, failed_node_id, reason="Escalated to human", session_id=session_id))
            # Clone plan and mark as requiring approval
            repaired_plan = Plan.from_dict(plan.to_dict())
            repaired_plan.metadata["requires_human_approval"] = True
            repaired_plan.metadata["escalation_reason"] = f"Action: {action.value} | Error: {str(error)}"
            return repaired_plan

        # 5. Handle Retry (keeping the plan intact, but resetting node status)
        if action == RecoveryAction.RETRY:
            self._emit_event(
                PlanRepairStartedEvent.create(plan.plan_id, failed_node_id, strategy="RETRY", session_id=session_id)
            )
            # Create new Plan generation
            repaired_plan = Plan.from_dict(plan.to_dict())
            repaired_plan.plan_id = f"plan-{uuid.uuid4().hex[:8]}"
            repaired_plan.parent_plan_id = plan.plan_id
            repaired_plan.generation = plan.generation + 1
            
            # Reset node status back to PROPOSED
            repaired_node = repaired_plan.graph.nodes[failed_node_id]
            repaired_node.status = GoalStatus.PROPOSED
            repaired_node.retry_count += 1
            
            self._emit_event(
                PlanRepairSucceededEvent.create(plan.plan_id, repaired_plan.plan_id, repaired_plan.generation, session_id=session_id)
            )
            return repaired_plan

        # 6. Handle Subtree Rebuild & Tool Substitution
        if action in {RecoveryAction.REBUILD_SUBTREE, RecoveryAction.SUBSTITUTE_TOOL}:
            self._emit_event(
                PlanRepairStartedEvent.create(plan.plan_id, failed_node_id, strategy=action.value, session_id=session_id)
            )

            # Identify affected subtree (failed node + downstream dependents if rebuild)
            affected_ids: Set[str] = set()
            if action == RecoveryAction.SUBSTITUTE_TOOL:
                affected_ids.add(failed_node_id)
            else:
                def collect_dependents(node_id: str):
                    if node_id not in affected_ids:
                        affected_ids.add(node_id)
                        for child in graph.adjacency_list.get(node_id, []):
                            collect_dependents(child)
                collect_dependents(failed_node_id)


            # Mark rule or tool as tabu to prevent infinite loop oscillations
            self.policy_engine.mark_tabu(failed_node.title)

            # Choose substitute task if available, or fall back to root task title
            substitute_task = failed_node.title
            if action == RecoveryAction.SUBSTITUTE_TOOL:
                # E.g. download fallback rules could use alternative tool names
                if substitute_task == "DownloadBinary":
                    # If we are offline or download fails, try configuring local fallback if rule exists
                    substitute_task = "ConfigureSettings"

            # Re-generate subtree using HTN planner
            try:
                # Retrieve preconditions/state variables from world state
                initial_state = list(world_state.get("final_state", []))
                # Add current satisfied effects of COMPLETED nodes to state context
                for node in graph.nodes.values():
                    if node.goal_id not in affected_ids and node.status == GoalStatus.COMPLETED:
                        initial_state.extend(node.effects)

                sub_plan = self.planner.generate_plan(
                    goal_id=plan.goal_id,
                    root_task_name=substitute_task,
                    initial_state=list(set(initial_state)),
                )
            except Exception as e:
                # Subtree decomposition failed -> Abort Plan
                self._emit_event(PlanRepairFailedEvent.create(plan.plan_id, failed_node_id, reason=str(e), session_id=session_id))
                raise ValidationError(f"Plan subtree repair failed: {e}")

            # Clone parent plan to build repaired plan version
            repaired_plan = Plan.from_dict(plan.to_dict())
            repaired_plan.plan_id = f"plan-{uuid.uuid4().hex[:8]}"
            repaired_plan.parent_plan_id = plan.plan_id
            repaired_plan.generation = plan.generation + 1

            # Remove affected nodes from the graph
            for node_id in affected_ids:
                if node_id in repaired_plan.graph.nodes:
                    # Remove in plan graph lists
                    repaired_plan.graph.nodes.pop(node_id)
                if node_id in repaired_plan.graph.adjacency_list:
                    repaired_plan.graph.adjacency_list.pop(node_id)
                if node_id in repaired_plan.graph.in_degree_list:
                    repaired_plan.graph.in_degree_list.pop(node_id)
                
                # Cleanup edge links in remaining nodes
                for parents in repaired_plan.graph.in_degree_list.values():
                    if node_id in parents:
                        parents.remove(node_id)
                for children in repaired_plan.graph.adjacency_list.values():
                    if node_id in children:
                        children.remove(node_id)

            # Graft new subtree nodes
            preserved_parents = list(failed_node.dependencies)
            preserved_children = [
                nid for nid, nd in graph.nodes.items()
                if nid not in affected_ids and failed_node_id in nd.dependencies
            ]

            # Add new nodes
            for sub_node_id, sub_node in sub_plan.graph.nodes.items():
                repaired_plan.graph.nodes[sub_node_id] = sub_node
                repaired_plan.graph.adjacency_list[sub_node_id] = list(sub_plan.graph.adjacency_list.get(sub_node_id, []))
                repaired_plan.graph.in_degree_list[sub_node_id] = list(sub_plan.graph.in_degree_list.get(sub_node_id, []))

            # Entry nodes of grafted subtree connect to preserved parents
            grafted_entry_nodes = sub_plan.graph.get_parallel_layers()[0]
            for entry_node_id in grafted_entry_nodes:
                for parent_id in preserved_parents:
                    if parent_id in repaired_plan.graph.nodes:
                        repaired_plan.graph.add_dependency(entry_node_id, parent_id)

            # Exit nodes of grafted subtree connect to preserved children
            grafted_exit_nodes = [
                nid for nid in sub_plan.graph.nodes
                if not sub_plan.graph.adjacency_list.get(nid)
            ]
            for exit_node_id in grafted_exit_nodes:
                for child_id in preserved_children:
                    if child_id in repaired_plan.graph.nodes:
                        repaired_plan.graph.add_dependency(child_id, exit_node_id)


            self._emit_event(
                PlanRepairSucceededEvent.create(plan.plan_id, repaired_plan.plan_id, repaired_plan.generation, session_id=session_id)
            )
            return repaired_plan

        return plan

    def _emit_event(self, event: Any) -> None:
        """Appends recovery transitions to Execution Ledger if active."""
        try:
            from backend.core.cos.kernel import KERNEL
            if KERNEL and KERNEL.ledger:
                KERNEL.ledger.append(event)
        except Exception:
            pass
