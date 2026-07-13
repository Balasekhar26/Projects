import unittest
from backend.planner.gtpyhop_adapter import GTPyhopAdapter
from backend.planner.task_decomposer import TaskDecomposer, Operator, Method

class TestReplanning(unittest.TestCase):
    """Unit tests for adaptive replanning triggers when tool or precondition failures are encountered."""

    def setUp(self) -> None:
        self.decomposer = TaskDecomposer()
        
        # Define tasks representing a build and deploy cycle
        self.decomposer.declare_operator(Operator(
            name="compile_code",
            preconditions={"has_source": True},
            effects={"code_compiled": True}
        ))
        self.decomposer.declare_operator(Operator(
            name="run_tests",
            preconditions={"code_compiled": True},
            effects={"tests_passed": True}
        ))
        self.decomposer.declare_operator(Operator(
            name="deploy_binary",
            preconditions={"tests_passed": True},
            effects={"app_deployed": True}
        ))
        
        self.decomposer.declare_method(Method(
            name="run_release",
            task_name="release_cycle",
            preconditions={},
            subtasks=["compile_code", "run_tests", "deploy_binary"]
        ))
        
        self.adapter = GTPyhopAdapter(decomposer=self.decomposer)

    def test_replan_after_precondition_failure(self) -> None:
        initial_state = {
            "has_source": True,
            "code_compiled": False,
            "tests_passed": False,
            "app_deployed": False
        }
        
        # Generate initial plan
        plan = self.adapter.create_plan(
            goal="release_cycle",
            world_state=initial_state,
            constraints={}
        )
        self.assertEqual(len(plan["steps"]), 3)
        self.assertEqual(plan["steps"][0]["name"], "compile_code")

        # Step 1: compile code succeeds
        res = self.adapter.execute_step(plan["steps"][0]["step_id"], initial_state)
        self.assertTrue(res["world_state"]["code_compiled"])

        # Precondition for step 2 (run_tests) requires code_compiled = True
        # Simulate world state drift: code compilation gets corrupted/deleted, setting code_compiled to False
        driffed_state = dict(res["world_state"])
        driffed_state["code_compiled"] = False

        # Attempting to run step 2 throws error
        with self.assertRaises(ValueError):
            self.adapter.execute_step(plan["steps"][1]["step_id"], driffed_state)

        # Trigger replan to recover from failure state
        replanned = self.adapter.replan(
            failed_step_id=plan["steps"][1]["step_id"],
            current_state=driffed_state
        )

        # The replan must include the compile_code step again to satisfy preconditions
        self.assertEqual(replanned["steps"][0]["name"], "compile_code")
        self.assertEqual(replanned["steps"][1]["name"], "run_tests")
        self.assertEqual(replanned["steps"][2]["name"], "deploy_binary")

