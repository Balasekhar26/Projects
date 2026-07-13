import unittest
from backend.planner.gtpyhop_adapter import GTPyhopAdapter
from backend.planner.task_decomposer import TaskDecomposer, Operator, Method

class TestCheckpointRecovery(unittest.TestCase):
    """Unit tests for planner state checkpoint serialization and migration/restoration properties."""

    def setUp(self) -> None:
        self.decomposer = TaskDecomposer()
        self.decomposer.declare_operator(Operator(
            name="step_a",
            preconditions={"start": True},
            effects={"done_a": True}
        ))
        self.decomposer.declare_operator(Operator(
            name="step_b",
            preconditions={"done_a": True},
            effects={"done_b": True}
        ))
        self.decomposer.declare_method(Method(
            name="run_seq",
            task_name="sequence_task",
            preconditions={},
            subtasks=["step_a", "step_b"]
        ))
        self.adapter = GTPyhopAdapter(decomposer=self.decomposer)

    def test_checkpoint_serialize_and_restore(self) -> None:
        initial_state = {"start": True, "done_a": False, "done_b": False}
        
        # Step 1: Create initial plan
        plan = self.adapter.create_plan(
            goal="sequence_task",
            world_state=initial_state,
            constraints={}
        )
        self.assertEqual(len(self.adapter.remaining_plan), 2)

        # Step 2: Execute first node
        res = self.adapter.execute_step(plan["steps"][0]["step_id"], initial_state)
        self.assertEqual(len(self.adapter.remaining_plan), 1)
        self.assertEqual(self.adapter.completed_tasks, ["step_a"])

        # Step 3: Serialize state
        checkpoint_data = self.adapter.checkpoint()
        self.assertTrue(len(checkpoint_data) > 0)

        # Step 4: Instantiate fresh new adapter and restore state
        new_adapter = GTPyhopAdapter(decomposer=self.decomposer)
        new_adapter.restore(checkpoint_data)

        # Step 5: Verify restored properties
        self.assertEqual(new_adapter.active_goal, "sequence_task")
        self.assertEqual(new_adapter.completed_tasks, ["step_a"])
        self.assertEqual(len(new_adapter.remaining_plan), 1)
        self.assertEqual(new_adapter.world_state.variables["done_a"], True)

        # Step 6: Verify we can resume execution seamlessly on the new instance
        next_step = new_adapter.remaining_plan[0]
        res_next = new_adapter.execute_step(next_step["step_id"], new_adapter.world_state.variables)
        self.assertEqual(res_next["status"], "COMPLETED")
        self.assertTrue(res_next["world_state"]["done_b"])

    def test_durable_checkpoint_across_process_restart(self) -> None:
        import os
        checkpoint_file = "planner_checkpoint.bin"
        initial_state = {"start": True, "done_a": False, "done_b": False}
        
        # 1. Start plan
        plan = self.adapter.create_plan(
            goal="sequence_task",
            world_state=initial_state,
            constraints={}
        )
        # 2. Execute first step
        res = self.adapter.execute_step(plan["steps"][0]["step_id"], initial_state)
        
        # 3. Serialize checkpoint to disk (simulating process exit)
        checkpoint_data = self.adapter.checkpoint()
        with open(checkpoint_file, "wb") as f:
            f.write(checkpoint_data)
            
        # 4. Kill planner instance by deleting reference
        del self.adapter
        
        # 5. Restore checkpoint from disk in a fresh new process simulation
        self.assertTrue(os.path.exists(checkpoint_file))
        with open(checkpoint_file, "rb") as f:
            restored_bytes = f.read()
            
        new_adapter = GTPyhopAdapter(decomposer=self.decomposer)
        new_adapter.restore(restored_bytes)
        
        # Clean up checkpoint file
        if os.path.exists(checkpoint_file):
            os.remove(checkpoint_file)
            
        # 6. Continue execution on the remaining steps
        self.assertEqual(new_adapter.active_goal, "sequence_task")
        next_step = new_adapter.remaining_plan[0]
        res_next = new_adapter.execute_step(next_step["step_id"], new_adapter.world_state.variables)
        self.assertEqual(res_next["status"], "COMPLETED")
        self.assertTrue(res_next["world_state"]["done_b"])


