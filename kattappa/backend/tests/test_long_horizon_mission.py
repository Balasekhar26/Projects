"""Unit tests for Program 24.0: Long-Horizon Mission Execution.

Verifies checkpoint restorations, temporal schedulers, environmental trackers, and decision ledgers.
"""
from __future__ import annotations

import os
import time
import pytest
from unittest.mock import patch, MagicMock

from backend.core.mission_checkpoint import MissionCheckpoint
from backend.core.mission_state import MissionState
from backend.core.mission_interrupt import MissionInterruptHandler
from backend.core.mission_temporal_scheduler import MissionTemporalScheduler
from backend.core.mission_world_tracker import MissionWorldStateTracker
from backend.core.mission_ledger import MissionLedger


@pytest.fixture(autouse=True)
def clean_checkpoints_and_ledgers():
    # Clear checkpoints and ledger lists
    MissionCheckpoint.save_checkpoints([])
    MissionLedger.reset()
    MissionInterruptHandler._active_executions.clear()
    yield
    MissionCheckpoint.save_checkpoints([])
    MissionLedger.reset()
    MissionInterruptHandler._active_executions.clear()


# ── 1. Interrupt and Resumption Tests ─────────────────────────────────────────

class TestMissionInterruptHandler:
    def test_interruption_recovery_flow(self):
        mission_id = "mis_test_01"
        
        # Seed Checkpoints
        state_s0 = {"stage": "Research", "progress": 20.0, "blocked": False}
        chp1 = MissionCheckpoint.create_checkpoint(mission_id, state_s0)
        time.sleep(0.01) # guarantee timestamp increase
        state_s1 = {"stage": "Design", "progress": 40.0, "blocked": False}
        chp2 = MissionCheckpoint.create_checkpoint(mission_id, state_s1)

        # Register running start -> simulates active execution block
        MissionInterruptHandler.register_execution_start(mission_id, "Testing")

        # System interruption! (simulate crash by calling detect_and_handle_interruption)
        res = MissionInterruptHandler.detect_and_handle_interruption(mission_id)
        
        assert res["status"] == "resumed"
        assert res["checkpoint_id"] == chp2["checkpoint_id"]
        assert res["restored_state"]["stage"] == "Design"
        assert res["restored_state"]["progress"] == 40.0

        # Run success register
        MissionInterruptHandler.register_execution_start(mission_id, "Documentation")
        MissionInterruptHandler.register_execution_success(mission_id)
        # Verify clean check
        clean_res = MissionInterruptHandler.detect_and_handle_interruption(mission_id)
        assert clean_res["status"] == "clean"


# ── 2. Temporal Scheduler Tests ───────────────────────────────────────────────

class TestMissionTemporalScheduler:
    def test_delayed_task_execution(self):
        scheduler = MissionTemporalScheduler()
        execution_count = 0

        def action():
            nonlocal execution_count
            execution_count += 1
            return "ok"

        # Schedule task with 1s delay
        task_id = scheduler.schedule_delay("mis_01", 1.0, action)
        
        # Tick immediately -> should not run
        ticks_immediate = scheduler.tick()
        assert len(ticks_immediate) == 0
        assert execution_count == 0

        # Mock time forward by 2 seconds
        with patch("time.time", return_value=time.time() + 2.0):
            ticks_later = scheduler.tick()
            assert len(ticks_later) == 1
            assert ticks_later[0]["task_id"] == task_id
            assert ticks_later[0]["result"] == "ok"
            assert execution_count == 1

    def test_periodic_task_execution(self):
        scheduler = MissionTemporalScheduler()
        execution_count = 0

        def action():
            nonlocal execution_count
            execution_count += 1
            return "run"

        # Run check every 2 seconds
        task_id = scheduler.schedule_periodic("mis_01", 2.0, action)
        
        # Mock time forward by 3s -> triggers execution
        with patch("time.time", return_value=time.time() + 3.0):
            ticks = scheduler.tick()
            assert len(ticks) == 1
            assert execution_count == 1

        # Mock time forward by another 3s -> triggers second run
        with patch("time.time", return_value=time.time() + 6.0):
            ticks_2 = scheduler.tick()
            assert len(ticks_2) == 1
            assert execution_count == 2


# ── 3. World State Assumption Verifier Tests ──────────────────────────────────

class TestMissionWorldStateTracker:
    def test_verify_file_exists(self):
        temp_file = "temp_assumption_check.txt"
        
        # False initially
        assert MissionWorldStateTracker.verify_assumption("FILE_EXISTS", temp_file) is False

        # Create file
        with open(temp_file, "w") as f:
            f.write("test")

        try:
            assert MissionWorldStateTracker.verify_assumption("FILE_EXISTS", temp_file) is True
        finally:
            if os.path.exists(temp_file):
                os.remove(temp_file)

    def test_verify_all_assumptions_passed(self):
        assumptions = [
            {"type": "ENV_VAR", "param": "PATH"}
        ]
        res = MissionWorldStateTracker.verify_all_assumptions(assumptions)
        assert res["passed"] is True

    def test_verify_all_assumptions_failed(self):
        assumptions = [
            {"type": "ENV_VAR", "param": "PATH"},
            {"type": "FILE_EXISTS", "param": "non_existent_folder_xyz"}
        ]
        res = MissionWorldStateTracker.verify_all_assumptions(assumptions)
        assert res["passed"] is False
        assert len(res["invalid_assumptions"]) == 1
        assert res["invalid_assumptions"][0]["param"] == "non_existent_folder_xyz"


# ── 4. Mission Ledger Database Tests ──────────────────────────────────────────

class TestMissionLedger:
    def test_record_and_retrieve_decisions(self):
        mission_id = "mis_ledger_100"
        
        MissionLedger.record_decision(
            mission_id=mission_id,
            stage="Research",
            decision="Select STM32 MCU",
            rationale="stm32 has better DMA support"
        )
        
        history = MissionLedger.get_mission_history(mission_id)
        assert len(history) == 1
        assert history[0]["stage"] == "Research"
        assert history[0]["decision"] == "Select STM32 MCU"
        assert history[0]["rationale"] == "stm32 has better DMA support"
