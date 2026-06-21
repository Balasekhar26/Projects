import json
import sqlite3
import time
import unittest
from unittest.mock import MagicMock, patch

from backend.core.strategic_memory import StrategicMemory
from backend.core.memory_governance import MemoryGovernance
from backend.core.memory_assembler import MemoryAssembler


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


class TestStrategicMemory(unittest.TestCase):

    def setUp(self):
        # Create a single in-memory database connection for the test class to bypass slow file system handle opens on Windows
        if not hasattr(self.__class__, "_shared_conn"):
            self.__class__._shared_conn = sqlite3.connect(":memory:", check_same_thread=False)
            self.__class__._shared_conn.row_factory = sqlite3.Row
            StrategicMemory._ensure_schema(self.__class__._shared_conn)
            MemoryGovernance._ensure_schema(self.__class__._shared_conn)

            from backend.core.episodic_memory import EpisodicMemory
            EpisodicMemory._ensure_schema(self.__class__._shared_conn)

            from backend.core.semantic_memory import SemanticMemory
            SemanticMemory._ensure_schema(self.__class__._shared_conn)

        # Clear tables between tests
        self.__class__._shared_conn.execute("DELETE FROM hm_strategic_goals")
        self.__class__._shared_conn.execute("DELETE FROM hm_strategic_goal_history")
        self.__class__._shared_conn.execute("DELETE FROM hm_trust_registry")
        self.__class__._shared_conn.execute("DELETE FROM hm_provenance")
        self.__class__._shared_conn.execute("DELETE FROM hm_episodes")
        self.__class__._shared_conn.execute("DELETE FROM hm_semantic_nodes")
        self.__class__._shared_conn.commit()

        # Patch _get_sqlite_conn to return our wrapped shared in-memory connection
        from backend.core.episodic_memory import EpisodicMemory
        from backend.core.semantic_memory import SemanticMemory
        self.conn_patchers = [
            patch.object(StrategicMemory, "_get_sqlite_conn", return_value=NoCloseConnection(self.__class__._shared_conn)),
            patch.object(MemoryGovernance, "_get_sqlite_conn", return_value=NoCloseConnection(self.__class__._shared_conn)),
            patch.object(EpisodicMemory, "_get_sqlite_conn", return_value=NoCloseConnection(self.__class__._shared_conn)),
            patch.object(SemanticMemory, "_get_sqlite_conn", return_value=NoCloseConnection(self.__class__._shared_conn)),
        ]
        for p in self.conn_patchers:
            p.start()

    def tearDown(self):
        for p in self.conn_patchers:
            p.stop()

    def test_goal_crud(self):
        """Verify basic goal creation, retrieval, and listing."""
        # 1. Create goal
        gid = StrategicMemory.create_goal(
            goal="Test Goal",
            description="Detailed intention of the test goal.",
            priority=0.8,
            derived_from=["sem-001", "ep-002"]
        )
        self.assertIsNotNone(gid)

        # 2. Get goal
        goal = StrategicMemory.get_goal(gid)
        self.assertIsNotNone(goal)
        self.assertEqual(goal["goal"], "Test Goal")
        self.assertEqual(goal["description"], "Detailed intention of the test goal.")
        self.assertEqual(goal["status"], "draft") # starts as draft
        self.assertEqual(goal["priority"], 0.8)
        self.assertEqual(goal["version"], 1)
        self.assertIn("sem-001", goal["derived_from"])
        self.assertIn("ep-002", goal["derived_from"])

        # 3. List goals
        goals = StrategicMemory.list_goals(status="draft")
        self.assertEqual(len(goals), 1)
        self.assertEqual(goals[0]["id"], gid)

    def test_approve_goal_promotes_state_and_trust(self):
        """Approve goal should transition draft to active, set trust in governance, and log provenance."""
        gid = StrategicMemory.create_goal(
            goal="Strategic Alignment",
            description="Align teams on standard processes.",
            derived_from=["ep-1"]
        )
        # Initially UNVERIFIED trust
        self.assertEqual(MemoryGovernance.get_trust(gid), "TRUST_UNVERIFIED")

        # Approve goal
        success = StrategicMemory.approve_goal(gid, approved_by="user")
        self.assertTrue(success)

        # Verify state promoted
        goal = StrategicMemory.get_goal(gid)
        self.assertEqual(goal["status"], "active")
        self.assertEqual(goal["approved_by_user"], 1)
        self.assertEqual(goal["trust_level"], "TRUST_USER")

        # Verify trust level upgraded in Governance Registry
        self.assertEqual(MemoryGovernance.get_trust(gid), "TRUST_USER")

        # Verify provenance is logged in Governance
        prov = MemoryGovernance.get_provenance(gid)
        self.assertIsNotNone(prov)
        self.assertEqual(prov["memory_type"], "strategic")
        self.assertEqual(prov["source"], "user")
        self.assertIn("ep-1", prov["derived_from"])

    def test_no_auto_promotion(self):
        """Goals should strictly remain in draft state unless explicitly approved."""
        gid = StrategicMemory.create_goal("Draft Only", "Should stay draft")
        goal = StrategicMemory.get_goal(gid)
        self.assertEqual(goal["status"], "draft")
        self.assertEqual(goal["approved_by_user"], 0)

    def test_lifecycle_state_machine_transitions(self):
        """Ensure only valid transitions are accepted, and invalid transitions raise ValueError."""
        gid = StrategicMemory.create_goal("State Goal", "Check transitions")

        # Initial draft status
        goal = StrategicMemory.get_goal(gid)
        self.assertEqual(goal["status"], "draft")

        # 1. draft -> active (approve)
        StrategicMemory.approve_goal(gid)
        self.assertEqual(StrategicMemory.get_goal(gid)["status"], "active")

        # 2. active -> paused (valid)
        StrategicMemory.set_status(gid, "paused")
        self.assertEqual(StrategicMemory.get_goal(gid)["status"], "paused")

        # 3. paused -> active (valid)
        StrategicMemory.set_status(gid, "active")
        self.assertEqual(StrategicMemory.get_goal(gid)["status"], "active")

        # 4. active -> completed (valid)
        StrategicMemory.set_status(gid, "completed")
        self.assertEqual(StrategicMemory.get_goal(gid)["status"], "completed")

        # 5. completed -> active (invalid!)
        with self.assertRaises(ValueError):
            StrategicMemory.set_status(gid, "active")

        # 6. completed -> archived (valid)
        StrategicMemory.set_status(gid, "archived")
        self.assertEqual(StrategicMemory.get_goal(gid)["status"], "archived")

        # 7. archived -> active (invalid!)
        with self.assertRaises(ValueError):
            StrategicMemory.set_status(gid, "active")

    def test_version_history_tracking(self):
        """Goal updates should increment version and append append-only snapshots to history."""
        gid = StrategicMemory.create_goal("Goal V1", "Initial description", priority=0.3)
        
        # Approve to make it active (this snapshots version 1)
        StrategicMemory.approve_goal(gid)

        # Update description (this increments version to 2)
        StrategicMemory.update_goal(gid, description="Updated V2 description", priority=0.6)

        goal = StrategicMemory.get_goal(gid)
        self.assertEqual(goal["version"], 2)
        self.assertEqual(goal["description"], "Updated V2 description")
        self.assertEqual(goal["priority"], 0.6)

        # Retrieve history
        history = StrategicMemory.get_goal_history(gid)
        self.assertEqual(len(history), 2)
        
        self.assertEqual(history[0]["version"], 1)
        self.assertEqual(history[0]["snapshot"]["description"], "Initial description")
        
        self.assertEqual(history[1]["version"], 2)
        self.assertEqual(history[1]["snapshot"]["description"], "Updated V2 description")

    def test_priority_ordering(self):
        """list_goals should return goals ordered by priority descending."""
        StrategicMemory.create_goal("Low Priority", "P=0.1", priority=0.1)
        StrategicMemory.create_goal("High Priority", "P=0.9", priority=0.9)
        StrategicMemory.create_goal("Medium Priority", "P=0.5", priority=0.5)

        goals = StrategicMemory.list_goals()
        self.assertEqual(len(goals), 3)
        self.assertEqual(goals[0]["goal"], "High Priority")
        self.assertEqual(goals[1]["goal"], "Medium Priority")
        self.assertEqual(goals[2]["goal"], "Low Priority")

    def test_blocked_updates_on_archived_goals(self):
        """Updating any field on an archived goal must raise ValueError."""
        gid = StrategicMemory.create_goal("Archived Goal", "Desc")
        StrategicMemory.set_status(gid, "archived")
        
        with self.assertRaises(ValueError):
            StrategicMemory.update_goal(gid, description="Updated desc")

    def test_parent_child_hierarchy(self):
        """Goals can reference parent goals to construct tree-like plan structures."""
        parent_id = StrategicMemory.create_goal("Parent Goal", "Root objective")
        child_id = StrategicMemory.create_goal(
            "Child Goal",
            "Sub objective",
            parent_goal_id=parent_id
        )

        child = StrategicMemory.get_goal(child_id)
        self.assertEqual(child["parent_goal_id"], parent_id)

        # Invalid parent ID should raise ValueError
        with self.assertRaises(ValueError):
            StrategicMemory.create_goal("Orphan Goal", "Invalid parent", parent_goal_id="invalid-uuid")

    def test_assembler_integration_surfaces_goals(self):
        """MemoryAssembler.assemble_context must query and return active goals."""
        gid1 = StrategicMemory.create_goal("Active Goal", "Active", priority=0.8)
        gid2 = StrategicMemory.create_goal("Draft Goal", "Draft", priority=0.9)

        # Approve only the active goal
        StrategicMemory.approve_goal(gid1)

        # Query assembler (disable procedural and memory mocks to run purely on SQLite)
        # Note: assemble_context will query SQLite for semantic / episodic which will return empty list since those are empty tables
        result = MemoryAssembler.assemble_context("arbitrary query")
        
        self.assertIn("goals", result)
        self.assertEqual(len(result["goals"]), 1)
        self.assertEqual(result["goals"][0]["id"], gid1)
        self.assertEqual(result["goals"][0]["goal"], "Active Goal")
