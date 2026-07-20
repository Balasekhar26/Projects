class FutureStatePredictor:
    @classmethod
    def predict_state_change(cls, current_state: dict, command: str) -> dict:
        """Projects changes to host state descriptors lists based on command instructions."""
        predicted = dict(current_state)
        files = list(predicted.get("files", []))
        
        words = command.lower().strip().split()
        if not words:
            return predicted
            
        action = words[0]
        if action in ("create", "write", "touch") and len(words) > 1:
            target = words[1]
            if target not in files:
                files.append(target)
        elif action in ("delete", "remove", "rm") and len(words) > 1:
            target = words[1]
            if target in files:
                files.remove(target)
                
        predicted["files"] = files
        return predicted
