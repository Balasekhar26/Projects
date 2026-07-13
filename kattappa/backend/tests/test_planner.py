import unittest
from backend.planner.gtpyhop_adapter import GTPyhopAdapter
from backend.planner.task_decomposer import TaskDecomposer, Operator, Method
from backend.planner.goal_stack import GoalItem

class TestPlanner(unittest.TestCase):
    """Unit tests for persistent HTN planner: alternative methods, backtracking, utility, confidence, and temporal constraints."""

    def setUp(self) -> None:
        self.decomposer = TaskDecomposer()
        
        # Operators for travel domain
        self.decomposer.declare_operator(Operator("book_flight", {}, {"has_ticket": True}, estimated_cost=50.0, estimated_time=2.0))
        self.decomposer.declare_operator(Operator("board_flight", {"has_ticket": True}, {"at_destination": True}, estimated_cost=5.0, estimated_time=1.0))
        self.decomposer.declare_operator(Operator("book_bus", {}, {"has_bus_ticket": True}, estimated_cost=20.0, estimated_time=12.0))
        self.decomposer.declare_operator(Operator("board_bus", {"has_bus_ticket": True}, {"at_destination": True}, estimated_cost=5.0, estimated_time=2.0))
        self.decomposer.declare_operator(Operator("long_drive", {}, {"at_destination": True}, estimated_cost=10.0, estimated_time=150.0))
        
        # Alternative methods for compound task: travel_to_hyderabad
        # Method A: take_flight (high utility: short time)
        self.decomposer.declare_method(Method(
            name="take_flight",
            task_name="travel_to_hyderabad",
            preconditions={"has_ticket": True},
            subtasks=["board_flight"],
            reward=150.0
        ))
        # Method B: buy_ticket_then_flight (medium utility: buys ticket first)
        self.decomposer.declare_method(Method(
            name="buy_ticket_then_flight",
            task_name="travel_to_hyderabad",
            preconditions={"has_ticket": False},
            subtasks=["book_flight", "board_flight"],
            reward=150.0
        ))
        # Method C: take_bus (lower utility: takes longer time)
        self.decomposer.declare_method(Method(
            name="take_bus",
            task_name="travel_to_hyderabad",
            preconditions={},
            subtasks=["book_bus", "board_bus"],
            reward=150.0
        ))
        # Method D: drive (pruned utility: too slow)
        self.decomposer.declare_method(Method(
            name="drive",
            task_name="travel_to_hyderabad",
            preconditions={},
            subtasks=["long_drive"],
            reward=150.0
        ))
        
        self.adapter = GTPyhopAdapter(decomposer=self.decomposer)

    def test_alternative_methods_and_utility_sorting(self) -> None:
        initial_state = {"has_ticket": True, "at_destination": False}
        
        # With has_ticket = True, "take_flight" method preconditions are met.
        # Its time (1.0) and cost (5.0) are very low, so it has highest utility.
        plan = self.adapter.create_plan(
            goal="travel_to_hyderabad",
            world_state=initial_state,
            constraints={"timeout": 10.0}
        )
        # Expected optimal plan: ["board_flight"]
        self.assertEqual(len(plan["steps"]), 1)
        self.assertEqual(plan["steps"][0]["name"], "board_flight")

    def test_backtracking_and_precondition_resolution(self) -> None:
        initial_state = {"has_ticket": False, "at_destination": False}
        
        # With has_ticket = False, "take_flight" method preconditions fail.
        # The planner backtracks and selects the next highest utility method "buy_ticket_then_flight".
        plan = self.adapter.create_plan(
            goal="travel_to_hyderabad",
            world_state=initial_state,
            constraints={"timeout": 10.0}
        )
        # Expected plan: ["book_flight", "board_flight"]
        self.assertEqual(len(plan["steps"]), 2)
        self.assertEqual(plan["steps"][0]["name"], "book_flight")
        self.assertEqual(plan["steps"][1]["name"], "board_flight")

    def test_probabilistic_preconditions(self) -> None:
        # Operator that needs high-confidence network alive check
        self.decomposer.declare_operator(Operator("query_api", {"network_alive": True}, {"data_downloaded": True}))
        self.decomposer.declare_method(Method("download", "fetch_data", {}, ["query_api"]))
        
        # Set low confidence in belief store
        self.adapter.belief_store.set_belief("network_alive", True, confidence=0.5, source="unreliable_wifi")
        
        # Planning should fail or backtrack because confidence (0.5) is below standard threshold (0.85)
        with self.assertRaises(ValueError):
            self.adapter.create_plan(
                goal="fetch_data",
                world_state={},
                constraints={"confidence_threshold": 0.85}
            )

    def test_temporal_pruning(self) -> None:
        initial_state = {"at_destination": False}
        
        # If we only have drive method, but timeout limit is set to 100 seconds
        # drive takes 150 seconds. The branch should get pruned immediately.
        self.decomposer.methods = [m for m in self.decomposer.methods if m.name == "drive"]
        
        with self.assertRaises(ValueError):
            self.adapter.create_plan(
                goal="travel_to_hyderabad",
                world_state=initial_state,
                constraints={"timeout": 100.0}
            )

