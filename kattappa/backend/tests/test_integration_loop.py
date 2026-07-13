import unittest
from backend.agents.planner import planner_node
from backend.agents.evaluator import evaluator_node
from backend.core.state import AgentState

class TestIntegrationLoop(unittest.TestCase):
    """Integration tests verifying the live planner routing and cognitive update loops."""

    def test_planner_routing_and_chaining(self) -> None:
        state: AgentState = {
            "user_input": "Book meeting tomorrow",
            "logs": []
        }
        
        # 1. Run planner node to generate HTN plan
        res_state = planner_node(state)
        
        # Verify TASK 2/3 extraction outputs
        self.assertIn("schedule_meeting", res_state["goal_tree"])
        self.assertIn("check_calendar", res_state["execution_plan"])
        self.assertIn("reserve_slot", res_state["execution_plan"])
        
        # Verify TASK 4 agent routing
        self.assertEqual(res_state["selected_agent"], "memory")  # check_calendar routes to memory
        self.assertEqual(res_state["execution_steps"], ["memory"])  # reserve_slot routes to memory

    def test_failure_reflection_node(self) -> None:
        state: AgentState = {
            "user_input": "Install software",
            "result": "Execution failed: Timeout error occurred.",
            "logs": []
        }
        
        # Run evaluator node to handle execution failure and reflection
        res_state = evaluator_node(state)
        
        # Verify TASK 6 reflection decision
        self.assertEqual(res_state.get("reflection_decision"), "retry")
        self.assertTrue(any("failure detected" in log for log in res_state["logs"]))
