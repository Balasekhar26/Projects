class StatePredictor:
    def __init__(self):
        pass

    def predict_future_state(self, current_state: str, action_command: str) -> str:
        """Models action impact and predicts the next workspace state description."""
        cmd_clean = action_command.lower().strip()
        
        if "save" in cmd_clean:
            return "FILE_SAVED"
        elif "delete" in cmd_clean or "rm" in cmd_clean:
            return "FILE_DELETED"
        elif "click" in cmd_clean:
            return f"CLICKED_{current_state}"
            
        return f"MODIFIED_{current_state}"
