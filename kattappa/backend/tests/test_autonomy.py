import pytest
import time
from datetime import datetime, timedelta
from backend.core.accessibility.accessibility_engine import AccessibilityEngine
from backend.core.autonomy.goal_manager import GoalManager, Goal
from backend.core.autonomy.scheduler import GoalScheduler
from backend.core.autonomy.autonomy_engine import AutonomyEngine

def test_accessibility_element_mapping() -> None:
    engine = AccessibilityEngine()
    elements = engine.get_visible_elements()
    
    assert len(elements) == 2
    assert elements[0].element_id == "save_btn"
    assert elements[0].confidence == 1.0  # absolute trust
    assert elements[0].pixel_bbox == (800, 600, 950, 640)
    
    # Query elements
    match = engine.query_element_by_name("document")
    assert match is not None
    assert match.element_id == "input_text"

def test_goal_manager_and_persistence_cleanup() -> None:
    manager = GoalManager()
    
    goal_eph = Goal("g_eph", "Ephemeral check", persistence_level="EPHEMERAL")
    goal_session = Goal("g_sess", "Session check", persistence_level="SESSION")
    goal_daily = Goal("g_daily", "Daily check", persistence_level="DAILY")
    
    manager.register_goal(goal_eph)
    manager.register_goal(goal_session)
    manager.register_goal(goal_daily)
    
    # Override created_at times to mock passage of time
    # 1. Ephemeral expired (> 5 minutes)
    goal_eph.created_at = datetime.now() - timedelta(minutes=6)
    # 2. Session active (only 1 hour elapsed, limits is 4 hours)
    goal_session.created_at = datetime.now() - timedelta(hours=1)
    
    manager.cleanup_expired_goals()
    
    # Ephemeral should have been purged, session and daily remain
    assert manager.get_goal("g_eph") is None
    assert manager.get_goal("g_sess") is not None
    assert manager.get_goal("g_daily") is not None

def test_goal_scheduler_retry_evaluation() -> None:
    scheduler = GoalScheduler()
    goal = Goal("g1", "Retry check", retry_interval_sec=1, max_retries=3)
    
    # Pending goals execute immediately
    assert scheduler.should_execute(goal)
    
    # Failed goals check retry cooldown
    goal.current_state = "FAILED"
    goal.updated_at = datetime.now()
    assert not scheduler.should_execute(goal)
    
    # Cooldown elapsed
    goal.updated_at = datetime.now() - timedelta(seconds=2)
    assert scheduler.should_execute(goal)
    
    # Out of retries
    goal.current_retry = 3
    assert not scheduler.should_execute(goal)

def test_autonomy_watchdog_replanning_loop() -> None:
    engine = AutonomyEngine()
    
    # 1. Register a goal that fails and needs retries
    goal = Goal(
        goal_id="g_fail",
        objective="Execute task that will fail",
        retry_interval_sec=1,
        max_retries=3
    )
    engine.manager.register_goal(goal)
    
    # 2. Start the watchdog engine
    engine.start()
    
    # Let watchdog run a couple of tick cycles
    time.sleep(0.3)
    
    # Should have run initial and triggered 1st retry replanner step
    assert goal.current_state == "FAILED"
    assert goal.current_retry >= 1
    assert engine.replans_triggered >= 1
    
    engine.stop()
