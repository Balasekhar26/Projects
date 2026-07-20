from backend.core.action.ui_controller import UIController
from backend.core.action.safety_guard import SafetyGuard
from backend.core.action.action_verifier import ActionVerifier

class ActionExecutor:
    def __init__(self):
        self.controller = UIController()

    def execute_action(
        self, 
        command: str, 
        x: int, 
        y: int, 
        pre_snapshot: bytes | None = None, 
        post_snapshot: bytes | None = None
    ) -> str:
        """Runs security checks, triggers UI controls, verifies results, and performs rollbacks on failure."""
        # 1. Safety Guard Check
        if not SafetyGuard.validate_action(command):
            return "BLOCKED"
            
        # Record pre-action cursor coords
        old_x, old_y = self.controller.mouse_x, self.controller.mouse_y
        
        # 2. Simulate mouse move and click action
        self.controller.move_to(x, y)
        self.controller.click()
        self.controller.type_text(command)
        
        # 3. Action Verification
        if pre_snapshot is not None and post_snapshot is not None:
            if not ActionVerifier.verify_state_change(pre_snapshot, post_snapshot):
                # Rollback mouse position
                self.controller.move_to(old_x, old_y)
                return "FAILED_ROLLBACK"
                
        return "SUCCESS"
