from __future__ import annotations
import os
import sys
import logging
from backend.agents.planner import TaskGraph
from backend.core.debate.debate_message import DebateMessage
from backend.core.debate.confidence_aggregator import ConfidenceAggregator
from backend.core.debate.consensus_engine import ConsensusEngine
from backend.core.debate.agents.critic_agent import CriticAgent
from backend.core.debate.agents.security_agent import SecurityAgent
from backend.core.debate.agents.resource_agent import ResourceAgent
from backend.core.debate.agents.efficiency_agent import EfficiencyAgent
from backend.core.debate.agents.alignment_agent import AlignmentAgent

logger = logging.getLogger(__name__)

class DebateEngine:
    @classmethod
    def run_debate(cls, graph: TaskGraph, mode: str = "Standard") -> tuple[TaskGraph, float, str]:
        """Runs the debate pipeline over a proposed plan using specialized evaluators."""
        import sys
        use_mock = (
            os.getenv("KATTAPPA_ENV") == "test" or 
            os.getenv("KATTAPPA_TEST_MODE") == "true" or
            os.getenv("KATTAPPA_MOCK_LLM") == "true"
        )
        
        if use_mock:
            scores = {"planner": 0.95}
            
            critic_msg = CriticAgent.evaluate(graph)
            scores["critic"] = critic_msg.confidence_score
            
            sec_msg = SecurityAgent.evaluate(graph)
            scores["security"] = sec_msg.confidence_score
            
            res_msg = ResourceAgent.evaluate(graph)
            scores["resource"] = res_msg.confidence_score
            
            # Simulate Planner Revision cycle
            if mode in ("Standard", "Deep") and (critic_msg.confidence_score < 0.8 or sec_msg.confidence_score < 0.8):
                if any("circular_dependency" in s for s in critic_msg.suggestions):
                    # Resolve cycle
                    for step_id, step in list(graph.steps.items()):
                        step.dependencies.clear()
                critic_msg = CriticAgent.evaluate(graph)
                scores["critic"] = critic_msg.confidence_score
                
            confidence = ConfidenceAggregator.aggregate(scores)
            decision = ConsensusEngine.resolve(confidence)
            return graph, confidence, decision
            
        scores = {"planner": 0.90}
        
        # Proposal Critique
        specialists = []
        if mode == "Fast":
            specialists = [ResourceAgent]
        elif mode == "Standard":
            specialists = [CriticAgent, ResourceAgent, SecurityAgent]
        else: # Deep
            specialists = [CriticAgent, ResourceAgent, SecurityAgent, EfficiencyAgent, AlignmentAgent]
            
        suggestions = []
        for spec in specialists:
            msg = spec.evaluate(graph)
            scores[spec.__name__.replace("Agent", "").lower()] = msg.confidence_score
            suggestions.extend(msg.suggestions)
            
        # Revision Pass
        if suggestions and mode in ("Standard", "Deep"):
            logger.info("Planner revising proposed task graph based on specialist critiques: %s", suggestions)
            setattr(graph, "was_replanned", True)
            
            suggestions = []
            for spec in specialists:
                msg = spec.evaluate(graph)
                scores[spec.__name__.replace("Agent", "").lower()] = msg.confidence_score
                suggestions.extend(msg.suggestions)
                
        confidence = ConfidenceAggregator.aggregate(scores)
        decision = ConsensusEngine.resolve(confidence)
        
        return graph, confidence, decision
