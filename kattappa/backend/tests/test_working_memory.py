import json
import sqlite3
import time
import unittest
from unittest.mock import patch

from backend.core.working_memory import WorkingMemory
from backend.core.reflection_memory import ReflectionMemory


class NoCloseConnection:
    def __init__(self, conn):
        self._conn = conn

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


class TestWorkingMemory(unittest.TestCase):

    def setUp(self):
        # Create shared in-memory connection
        if not hasattr(self.__class__, "_shared_conn"):
            self.__class__._shared_conn = sqlite3.connect(":memory:", check_same_thread=False)
            self.__class__._shared_conn.row_factory = sqlite3.Row
            WorkingMemory._ensure_schema(self.__class__._shared_conn)
            ReflectionMemory._ensure_schema(self.__class__._shared_conn)

        # Clear tables
        self.__class__._shared_conn.execute("DELETE FROM hm_working_memory_sessions")
        self.__class__._shared_conn.execute("DELETE FROM hm_working_memory_goals")
        self.__class__._shared_conn.execute("DELETE FROM hm_working_memory_tasks")
        self.__class__._shared_conn.execute("DELETE FROM hm_working_memory_traces")
        self.__class__._shared_conn.execute("DELETE FROM hm_reflections")
        self.__class__._shared_conn.execute("DELETE FROM hm_guardrails")
        self.__class__._shared_conn.commit()

        # Patch connection getters
        self.conn_patchers = [
            patch.object(WorkingMemory, "_get_sqlite_conn", return_value=NoCloseConnection(self.__class__._shared_conn)),
            patch.object(ReflectionMemory, "_get_sqlite_conn", return_value=NoCloseConnection(self.__class__._shared_conn)),
        ]
        for p in self.conn_patchers:
            p.start()

    def tearDown(self):
        for p in self.conn_patchers:
            p.stop()

    def test_session_initialization(self):
        """Verify sessions can be initialized and found."""
        session_id = "sess_101"
        WorkingMemory.initialize_session(session_id)
        
        row = self.__class__._shared_conn.execute("SELECT * FROM hm_working_memory_sessions WHERE id = ?", (session_id,)).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["status"], "active")

    def test_goal_stack_and_parenting(self):
        """Verify goal stacks support hierarchical sub-goals and status completions."""
        session_id = "sess_101"
        
        # 1. Push parent goal
        parent_id = WorkingMemory.push_goal(session_id, "Build code repository")
        parent = self.__class__._shared_conn.execute("SELECT * FROM hm_working_memory_goals WHERE id = ?", (parent_id,)).fetchone()
        self.assertIsNotNone(parent)
        self.assertEqual(parent["goal_text"], "Build code repository")
        self.assertIsNone(parent["parent_goal_id"])
        
        # 2. Push child goal
        child_id = WorkingMemory.push_goal(session_id, "Create database connection script", parent_goal_id=parent_id)
        child = self.__class__._shared_conn.execute("SELECT * FROM hm_working_memory_goals WHERE id = ?", (child_id,)).fetchone()
        self.assertIsNotNone(child)
        self.assertEqual(child["parent_goal_id"], parent_id)

        # 3. Fail pushing child with non-existent parent
        with self.assertRaises(ValueError):
            WorkingMemory.push_goal(session_id, "Bad child", parent_goal_id="invalid_id")

        # 4. Complete parent goal
        success = WorkingMemory.complete_goal(parent_id)
        self.assertTrue(success)
        parent_updated = self.__class__._shared_conn.execute("SELECT status FROM hm_working_memory_goals WHERE id = ?", (parent_id,)).fetchone()
        self.assertEqual(parent_updated["status"], "completed")

    def test_task_status_tracking(self):
        """Verify tasks default to pending and change status correctly."""
        session_id = "sess_101"
        goal_id = WorkingMemory.push_goal(session_id, "Write code tests")
        
        # 1. Push task
        task_id = WorkingMemory.push_task(goal_id, "Run coverage reporting tool")
        task = self.__class__._shared_conn.execute("SELECT * FROM hm_working_memory_tasks WHERE id = ?", (task_id,)).fetchone()
        self.assertIsNotNone(task)
        self.assertEqual(task["task_description"], "Run coverage reporting tool")
        self.assertEqual(task["status"], "pending")

        # 2. Update status
        self.assertTrue(WorkingMemory.update_task_status(task_id, "running"))
        task_run = self.__class__._shared_conn.execute("SELECT status FROM hm_working_memory_tasks WHERE id = ?", (task_id,)).fetchone()
        self.assertEqual(task_run["status"], "running")

        # 3. Fail updating with invalid status
        with self.assertRaises(ValueError):
            WorkingMemory.update_task_status(task_id, "invalid_status")

    @patch("backend.core.reflection_memory.ReflectionMemory.list_active_guardrails")
    def test_trace_logging_and_active_guardrails(self, mock_guardrails):
        """Verify traces capture active guardrail snapshots at log time."""
        session_id = "sess_101"
        
        # Mock 2 active guardrails
        mock_guardrails.return_value = [
            {"id": "G-100", "rule": "Be safe"},
            {"id": "G-102", "rule": "Be brief"}
        ]
        
        # Log trace
        trace_id = WorkingMemory.log_trace(
            session_id=session_id,
            goal_id=None,
            task_id=None,
            trace_type="thought",
            content="Initializing main cognitive loop."
        )
        
        trace = self.__class__._shared_conn.execute("SELECT * FROM hm_working_memory_traces WHERE id = ?", (trace_id,)).fetchone()
        self.assertIsNotNone(trace)
        self.assertEqual(trace["trace_type"], "thought")
        self.assertEqual(trace["content"], "Initializing main cognitive loop.")
        
        # Verify active guardrails captured
        g_ids = json.loads(trace["active_guardrails"])
        self.assertIn("G-100", g_ids)
        self.assertIn("G-102", g_ids)

    def test_active_workspace_context_retrieval(self):
        """Verify the active context query constructs the workspace structure."""
        session_id = "sess_101"
        
        goal_id = WorkingMemory.push_goal(session_id, "Core reasoning goal")
        task_id = WorkingMemory.push_task(goal_id, "Evaluate parser safety limits")
        WorkingMemory.log_trace(session_id, goal_id, task_id, "thought", "Checking parser recursion filters.")
        
        context = WorkingMemory.get_active_workspace_context(session_id)
        self.assertEqual(context["session_id"], session_id)
        
        self.assertEqual(len(context["active_goals"]), 1)
        self.assertEqual(context["active_goals"][0]["goal_text"], "Core reasoning goal")
        
        self.assertEqual(len(context["tasks"]), 1)
        self.assertEqual(context["tasks"][0]["task_description"], "Evaluate parser safety limits")
        
        self.assertEqual(len(context["traces"]), 1)
        self.assertEqual(context["traces"][0]["content"], "Checking parser recursion filters.")

    def test_cascading_clear_session(self):
        """Verify cascading clear deletes all goals, tasks, and traces linked to a session."""
        session_id = "sess_101"
        
        goal_id = WorkingMemory.push_goal(session_id, "Temporary goals stack")
        task_id = WorkingMemory.push_task(goal_id, "Temporary task stack")
        WorkingMemory.log_trace(session_id, goal_id, task_id, "thought", "Transient logic checks.")

        # Ensure they exist in DB
        self.assertIsNotNone(self.__class__._shared_conn.execute("SELECT id FROM hm_working_memory_goals WHERE session_id = ?", (session_id,)).fetchone())
        self.assertIsNotNone(self.__class__._shared_conn.execute("SELECT id FROM hm_working_memory_tasks WHERE goal_id = ?", (goal_id,)).fetchone())
        self.assertIsNotNone(self.__class__._shared_conn.execute("SELECT id FROM hm_working_memory_traces WHERE session_id = ?", (session_id,)).fetchone())

        # Clear session
        self.assertTrue(WorkingMemory.clear_session(session_id))

        # Verify cascades wiped everything
        self.assertIsNone(self.__class__._shared_conn.execute("SELECT id FROM hm_working_memory_sessions WHERE id = ?", (session_id,)).fetchone())
        self.assertIsNone(self.__class__._shared_conn.execute("SELECT id FROM hm_working_memory_goals WHERE session_id = ?", (session_id,)).fetchone())
        self.assertIsNone(self.__class__._shared_conn.execute("SELECT id FROM hm_working_memory_tasks WHERE goal_id = ?", (goal_id,)).fetchone())
        self.assertIsNone(self.__class__._shared_conn.execute("SELECT id FROM hm_working_memory_traces WHERE session_id = ?", (session_id,)).fetchone())
