import pytest
from backend.core.action.ui_controller import UIController
from backend.core.action.safety_guard import SafetyGuard
from backend.core.action.action_verifier import ActionVerifier
from backend.core.action.action_executor import ActionExecutor

def test_safety_guard_blacklist() -> None:
    assert SafetyGuard.validate_action("ls -la")
    assert not SafetyGuard.validate_action("rm -rf /")
    assert not SafetyGuard.validate_action("format C:")
    assert not SafetyGuard.validate_action("DROP TABLE users")

def test_ui_controller_mouse_movement() -> None:
    controller = UIController()
    controller.move_to(200, 300)
    assert controller.mouse_x == 200
    assert controller.mouse_y == 300
    
    controller.activate_window("Notepad")
    assert controller.active_window == "Notepad"

def test_action_verifier_screenshot_changes() -> None:
    # No changes
    assert not ActionVerifier.verify_state_change(b"snap1", b"snap1")
    
    # Layout modified
    assert ActionVerifier.verify_state_change(b"snap1", b"snap2")

def test_action_executor_state_machine() -> None:
    executor = ActionExecutor()
    
    # 1. Blocked step
    status_blocked = executor.execute_action("rm -rf /usr", 100, 100)
    assert status_blocked == "BLOCKED"
    
    # 2. Success step
    status_ok = executor.execute_action("echo test", 150, 250, b"s1", b"s2")
    assert status_ok == "SUCCESS"
    assert executor.controller.mouse_x == 150
    assert executor.controller.mouse_y == 250
    
    # 3. Failed rollback step
    # Reset position to 0, 0
    executor.controller.move_to(0, 0)
    # Verification fails (snapshots pre and post match)
    status_fail = executor.execute_action("click button", 400, 400, b"same_state", b"same_state")
    assert status_fail == "FAILED_ROLLBACK"
    # Mouse should roll back to initial position (0, 0)
    assert executor.controller.mouse_x == 0
    assert executor.controller.mouse_y == 0
