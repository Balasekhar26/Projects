"""Multi-Agent Orchestrator (Program 52.0).

Coordinates dynamic spawning of specialist agents, blackboard postings,
consensus debates, and reputation-aware goal execution loops.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from backend.core.agent_registry import DEFAULT_REGISTRY
from backend.core.agent_router import DEFAULT_ROUTER, ConfidenceTier
from backend.core.agent_runtime import Agent
from backend.core.agent_society import AgentSociety
from backend.core.blackboard import BLACKBOARD
from backend.core.event_bus import EventBus, EventName
from backend.core.goal_manager import GoalManager, GoalStatus


class MultiAgentOrchestrator:
    """Centralized coordinator managing multi-agent reasoning and execution consensus."""

    @classmethod
    def orchestrate_goal(cls, prompt: str, mode: str = "BALANCED") -> Dict[str, Any]:
        """Routes prompt, spawns agents, triggers debates when needed, and updates reputation."""
        # 1. Routing decision
        decision = DEFAULT_ROUTER.route(prompt, mode)
        
        # 2. Spawn runtime agents dynamically
        spawned_agents: List[Agent] = []
        for agent_name in decision.agents:
            defn = DEFAULT_REGISTRY.get(agent_name)
            if defn:
                spawned_agents.append(Agent(defn))

        # 3. Register goal in GoalManager
        goal = GoalManager.add_goal(
            title=f"Resolve prompt: {prompt[:60]}",
            description=prompt,
            priority="HIGH",
        )
        goal_id = goal["goal_id"]
        GoalManager.start(goal_id)

        # 4. Post intent assessment to Blackboard
        BLACKBOARD.publish(
            publisher="MultiAgentOrchestrator",
            topic="intent_assessment",
            payload={
                "goal_id": goal_id,
                "prompt": prompt,
                "intent": decision.intent.value,
                "agents": decision.agents,
                "confidence_tier": decision.confidence_tier.value,
                "security_mandatory": decision.security_mandatory,
            },
        )

        # 5. Debate consensus loop (low confidence or security-sensitive prompts trigger debate)
        needs_debate = (
            decision.confidence_tier == ConfidenceTier.LOW 
            or decision.security_mandatory 
            or "debate" in prompt.lower()
        )

        debate_info: Optional[Dict[str, Any]] = None
        consensus_status = "APPROVED"

        if needs_debate:
            debate_info = AgentSociety.trigger_debate(
                title=f"Verify resolution for: {prompt[:30]}",
                details=f"Verifying security compliance and agent routing feasibility for prompt: {prompt}",
            )
            consensus_status = debate_info["consensus"]

        # 6. Apply outcomes and update reputations
        if consensus_status == "APPROVED":
            # Execution success: update reputations
            for agent_name in decision.agents:
                AgentSociety.update_agent_reputation(agent_name, success=True)
            
            GoalManager.complete(goal_id)
            
            # Notify event bus
            EventBus.publish(
                event_name=EventName.GOAL_COMPLETED,
                payload={"goal_id": goal_id, "prompt": prompt},
                source="MultiAgentOrchestrator",
            )

            return {
                "status": "success",
                "goal_id": goal_id,
                "agents": decision.agents,
                "needs_debate": needs_debate,
                "debate": debate_info,
            }
        else:
            # Consensus failed or vetoed: degrade reputations
            for agent_name in decision.agents:
                AgentSociety.update_agent_reputation(agent_name, success=False)
            
            GoalManager.fail(goal_id)
            
            # Notify event bus
            EventBus.publish(
                event_name=EventName.GOAL_FAILED,
                payload={"goal_id": goal_id, "reason": "debate consensus rejected"},
                source="MultiAgentOrchestrator",
            )

            return {
                "status": "failed",
                "goal_id": goal_id,
                "reason": "Consensus Rejected",
                "needs_debate": needs_debate,
                "debate": debate_info,
            }
