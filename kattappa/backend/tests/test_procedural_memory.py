import json
import sqlite3
import time
import unittest
from unittest.mock import patch

from backend.core.procedural_memory import ProceduralMemory


class NoCloseConnection:
    def __init__(self, conn):
        self._conn = conn

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def close(self):
        # Do not close the shared in-memory test database
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


class TestProceduralMemory(unittest.TestCase):

    def setUp(self):
        # Create a single in-memory database connection for the test class to bypass slow file system handles
        if not hasattr(self.__class__, "_shared_conn"):
            self.__class__._shared_conn = sqlite3.connect(":memory:", check_same_thread=False)
            self.__class__._shared_conn.row_factory = sqlite3.Row
            ProceduralMemory._ensure_schema(self.__class__._shared_conn)
            
            from backend.core.memory_governance import MemoryGovernance
            MemoryGovernance._ensure_schema(self.__class__._shared_conn)
            
            from backend.core.semantic_memory import SemanticMemory
            SemanticMemory._ensure_schema(self.__class__._shared_conn)
            
        # Clear tables
        self.__class__._shared_conn.execute("DELETE FROM hm_procedures")
        self.__class__._shared_conn.execute("DELETE FROM hm_procedure_audit")
        self.__class__._shared_conn.execute("DELETE FROM hm_provenance")
        self.__class__._shared_conn.execute("DELETE FROM hm_trust_registry")
        self.__class__._shared_conn.execute("DELETE FROM hm_semantic_nodes")
        self.__class__._shared_conn.commit()
        
        # Patch _get_sqlite_conn to return our wrapped shared in-memory connection
        from backend.core.memory_governance import MemoryGovernance
        from backend.core.semantic_memory import SemanticMemory
        self.conn_patchers = [
            patch.object(ProceduralMemory, "_get_sqlite_conn", return_value=NoCloseConnection(self.__class__._shared_conn)),
            patch.object(MemoryGovernance, "_get_sqlite_conn", return_value=NoCloseConnection(self.__class__._shared_conn)),
            patch.object(SemanticMemory, "_get_sqlite_conn", return_value=NoCloseConnection(self.__class__._shared_conn)),
        ]
        for pat in self.conn_patchers:
            pat.start()

    def tearDown(self):
        for pat in self.conn_patchers:
            pat.stop()

    def test_procedural_crud(self):
        steps = json.dumps([{"action": "click", "target": "submit_btn"}])
        
        # 1. Create (Register)
        pid = ProceduralMemory.register_procedure(
            skill_name="submit_form",
            trigger_phrase="click the submit button",
            steps_json=steps,
            trust_level="SYSTEM_TRUST",
            procedure_version=1
        )
        self.assertIsNotNone(pid)

        # 2. Read (Get)
        proc = ProceduralMemory.get_procedure(pid)
        self.assertIsNotNone(proc)
        self.assertEqual(proc["skill_name"], "submit_form")
        self.assertEqual(proc["trigger_phrase"], "click the submit button")
        self.assertEqual(proc["steps_json"], steps)
        self.assertEqual(proc["trust_level"], "SYSTEM_TRUST")
        self.assertEqual(proc["procedure_version"], 1)
        self.assertEqual(proc["revoked"], 0)
        self.assertIsNotNone(proc["signature"])

        # 3. Update
        new_steps = json.dumps([{"action": "click", "target": "cancel_btn"}])
        pid_updated = ProceduralMemory.register_procedure(
            skill_name="submit_form",
            trigger_phrase="click the cancel button",
            steps_json=new_steps,
            trust_level="USER_APPROVED",
            procedure_version=2,
            procedure_id=pid
        )
        self.assertEqual(pid, pid_updated)
        
        proc = ProceduralMemory.get_procedure(pid)
        self.assertEqual(proc["trigger_phrase"], "click the cancel button")
        self.assertEqual(proc["steps_json"], new_steps)
        self.assertEqual(proc["trust_level"], "USER_APPROVED")
        self.assertEqual(proc["procedure_version"], 2)

        # 4. Delete
        deleted = ProceduralMemory.delete_procedure(pid)
        self.assertTrue(deleted)
        self.assertIsNone(ProceduralMemory.get_procedure(pid))

    def test_signature_verification_and_tampering(self):
        steps = json.dumps([{"action": "run_command", "cmd": "echo 'Hello'"}])
        pid = ProceduralMemory.register_procedure(
            skill_name="hello_world",
            trigger_phrase="say hello",
            steps_json=steps,
            trust_level="SYSTEM_TRUST",
            procedure_version=1
        )
        
        # Verify initially valid
        allowed, reason = ProceduralMemory.validate_and_gate(pid, trigger_source="user")
        self.assertTrue(allowed)
        self.assertEqual(reason, "allowed")
        
        # Tamper steps_json directly in the database (bypassing registration signing)
        self.__class__._shared_conn.execute(
            "UPDATE hm_procedures SET steps_json = ? WHERE id = ?",
            (json.dumps([{"action": "run_command", "cmd": "rm -rf /"}]), pid)
        )
        self.__class__._shared_conn.commit()
        
        # Execution should be blocked due to signature mismatch
        allowed, reason = ProceduralMemory.validate_and_gate(pid, trigger_source="user")
        self.assertFalse(allowed)
        self.assertEqual(reason, "signature_invalid")

    def test_trust_gate_enforcement(self):
        steps = json.dumps([{"action": "log", "msg": "test"}])
        
        # SYSTEM_TRUST -> ALLOWED
        pid_sys = ProceduralMemory.register_procedure("sys_proc", "run sys", steps, "SYSTEM_TRUST")
        allowed, reason = ProceduralMemory.validate_and_gate(pid_sys, "user")
        self.assertTrue(allowed)
        
        # USER_APPROVED -> ALLOWED
        pid_user = ProceduralMemory.register_procedure("user_proc", "run user", steps, "USER_APPROVED")
        allowed, reason = ProceduralMemory.validate_and_gate(pid_user, "user")
        self.assertTrue(allowed)
        
        # DRAFT -> BLOCKED
        pid_draft = ProceduralMemory.register_procedure("draft_proc", "run draft", steps, "DRAFT")
        allowed, reason = ProceduralMemory.validate_and_gate(pid_draft, "user")
        self.assertFalse(allowed)
        self.assertEqual(reason, "trust_level_not_allowed")
        
        # UNTRUSTED -> BLOCKED
        pid_untrusted = ProceduralMemory.register_procedure("untrusted_proc", "run untrusted", steps, "UNTRUSTED")
        allowed, reason = ProceduralMemory.validate_and_gate(pid_untrusted, "user")
        self.assertFalse(allowed)
        self.assertEqual(reason, "trust_level_not_allowed")

    def test_trigger_matching(self):
        steps = json.dumps([{"action": "click"}])
        
        # Regex trigger registration
        pid_regex = ProceduralMemory.register_procedure("regex_proc", r"^deploy (app|service) now$", steps, "SYSTEM_TRUST")
        # Literal trigger registration
        pid_literal = ProceduralMemory.register_procedure("literal_proc", "restart server", steps, "SYSTEM_TRUST")
        
        # Test Regex matches
        matches = ProceduralMemory.match_trigger("deploy app now")
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["id"], pid_regex)
        
        matches = ProceduralMemory.match_trigger("deploy service now")
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["id"], pid_regex)
        
        matches = ProceduralMemory.match_trigger("deploy server now") # Doesn't match regex pattern (app|service)
        self.assertEqual(len(matches), 0)

        # Test Literal matches
        matches = ProceduralMemory.match_trigger("please restart server quickly")
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["id"], pid_literal)

    def test_ocr_and_web_injection_blocking(self):
        steps = json.dumps([{"action": "click"}])
        pid = ProceduralMemory.register_procedure("payment_proc", "pay bill", steps, "SYSTEM_TRUST")
        
        # Allowed from trusted user or system source
        allowed, reason = ProceduralMemory.validate_and_gate(pid, trigger_source="user")
        self.assertTrue(allowed)
        allowed, reason = ProceduralMemory.validate_and_gate(pid, trigger_source="system")
        self.assertTrue(allowed)
        
        # Blocked from OCR source
        allowed, reason = ProceduralMemory.validate_and_gate(pid, trigger_source="ocr")
        self.assertFalse(allowed)
        self.assertEqual(reason, "untrusted_source")
        
        # Blocked from Web source
        allowed, reason = ProceduralMemory.validate_and_gate(pid, trigger_source="web")
        self.assertFalse(allowed)
        self.assertEqual(reason, "untrusted_source")
        
        # Blocked from untrusted memory
        allowed, reason = ProceduralMemory.validate_and_gate(pid, trigger_source="untrusted_memory")
        self.assertFalse(allowed)
        self.assertEqual(reason, "untrusted_source")

    def test_replay_attack_protection(self):
        steps = json.dumps([{"action": "test"}])
        
        # Register Version 1
        pid_v1 = ProceduralMemory.register_procedure(
            skill_name="secured_skill",
            trigger_phrase="secure action",
            steps_json=steps,
            trust_level="SYSTEM_TRUST",
            procedure_version=1
        )
        
        # Register Version 2 (newer safer version)
        pid_v2 = ProceduralMemory.register_procedure(
            skill_name="secured_skill",
            trigger_phrase="secure action",
            steps_json=steps,
            trust_level="SYSTEM_TRUST",
            procedure_version=2
        )
        
        # Executing Version 2 -> Allowed
        allowed, reason = ProceduralMemory.validate_and_gate(pid_v2, "user")
        self.assertTrue(allowed)
        
        # Executing Version 1 -> Replay Blocked! (since latest registered version is 2)
        allowed, reason = ProceduralMemory.validate_and_gate(pid_v1, "user")
        self.assertFalse(allowed)
        self.assertEqual(reason, "version_replay_blocked")

    def test_revocation(self):
        steps = json.dumps([{"action": "test"}])
        pid = ProceduralMemory.register_procedure("revoked_skill", "action", steps, "SYSTEM_TRUST")
        
        # Initial -> allowed
        allowed, reason = ProceduralMemory.validate_and_gate(pid, "user")
        self.assertTrue(allowed)
        
        # Revoke it
        success = ProceduralMemory.revoke_procedure(pid)
        self.assertTrue(success)
        
        # Attempt Execution -> blocked
        allowed, reason = ProceduralMemory.validate_and_gate(pid, "user")
        self.assertFalse(allowed)
        self.assertEqual(reason, "procedure_revoked")

    def test_audit_logging(self):
        steps = json.dumps([{"action": "test"}])
        pid = ProceduralMemory.register_procedure("audit_skill", "audit action", steps, "SYSTEM_TRUST")
        
        # 1. Trigger successful execution
        allowed, reason = ProceduralMemory.validate_and_gate(pid, trigger_source="user")
        self.assertTrue(allowed)
        
        # 2. Trigger blocked execution (e.g. from web)
        allowed, reason = ProceduralMemory.validate_and_gate(pid, trigger_source="web")
        self.assertFalse(allowed)
        
        # Check audit trail contents
        trail = ProceduralMemory.get_audit_trail(pid)
        self.assertEqual(len(trail), 2)
        
        # Trail order is descending by timestamp (newest first)
        self.assertEqual(trail[0]["action"], "execute_attempt")
        self.assertEqual(trail[0]["result"], "BLOCKED_UNTRUSTED_SOURCE")
        self.assertEqual(trail[0]["source"], "web")
        
        self.assertEqual(trail[1]["action"], "execute_attempt")
        self.assertEqual(trail[1]["result"], "SUCCESS")
        self.assertEqual(trail[1]["source"], "user")

    def test_derived_from_nodes_untrusted_gate(self):
        """Registering a procedure derived from untrusted episodes must raise ValueError for SYSTEM_TRUST/USER_APPROVED."""
        # 1. Create untrusted episode and promote it to semantic fact
        from backend.core.memory_governance import MemoryGovernance
        from backend.core.semantic_memory import SemanticMemory
        
        MemoryGovernance.set_trust("ep-untrusted-p1", "memory", "TRUST_UNTRUSTED")
        
        # We manually insert semantic node since we don't have Chroma mocked here
        nid = "sem-untrusted-node-1"
        self.__class__._shared_conn.execute(
            """
            INSERT INTO hm_semantic_nodes (
                id, concept, description, confidence, evidence_count,
                source_episode_ids, provenance, created_at, updated_at
            ) VALUES (?, 'Unsafe Concept', 'Unsafe description.', 0.5, 2, ?, 'web', 0, 0)
            """,
            (nid, json.dumps(["ep-untrusted-p1"]))
        )
        self.__class__._shared_conn.commit()
        
        # 2. Attempt to register procedure derived from this node as SYSTEM_TRUST -> must fail
        steps = json.dumps([{"action": "exec", "cmd": "bad"}])
        with self.assertRaises(ValueError):
            ProceduralMemory.register_procedure(
                skill_name="unsafe_skill",
                trigger_phrase="run unsafe",
                steps_json=steps,
                trust_level="SYSTEM_TRUST",
                derived_from_nodes=[nid]
            )
            
        # 3. Registering as DRAFT should succeed without raising, since it's not trusted
        pid = ProceduralMemory.register_procedure(
            skill_name="unsafe_skill",
            trigger_phrase="run unsafe",
            steps_json=steps,
            trust_level="DRAFT",
            derived_from_nodes=[nid]
        )
        self.assertIsNotNone(pid)

    def test_procedural_provenance_logging(self):
        """Registering a procedure must log its provenance in governance."""
        steps = json.dumps([{"action": "print"}])
        pid = ProceduralMemory.register_procedure(
            skill_name="provenance_skill",
            trigger_phrase="test provenance",
            steps_json=steps,
            trust_level="SYSTEM_TRUST",
            derived_from_nodes=["sem-node-1", "sem-node-2"]
        )
        
        from backend.core.memory_governance import MemoryGovernance
        prov = MemoryGovernance.get_provenance(pid)
        self.assertIsNotNone(prov)
        self.assertEqual(prov["memory_type"], "procedural")
        self.assertEqual(prov["source"], "system")
        self.assertIn("sem-node-1", prov["derived_from"])
        self.assertIn("sem-node-2", prov["derived_from"])
