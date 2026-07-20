class SkillOptimizer:
    SHORTCUTS_MAPPING = {
        "click save": "shortcut Ctrl+S",
        "click find": "shortcut Ctrl+F",
        "click copy": "shortcut Ctrl+C"
    }

    @classmethod
    def optimize_steps(cls, steps: list[dict]) -> list[dict]:
        """Compresses action steps, removing redundancies and replacing click paths with keyboard shortcuts."""
        optimized = []
        last_step = None
        
        for step in steps:
            cmd = step.get("cmd", "")
            
            # 1. Substitute click path with keyboard shortcut if mapped
            if cmd in cls.SHORTCUTS_MAPPING:
                optimized.append({
                    "cmd": cls.SHORTCUTS_MAPPING[cmd],
                    "x": 0,
                    "y": 0
                })
                continue
                
            # 2. Filter redundant clicks at identical coordinates
            if last_step and cmd == "click" and last_step.get("cmd") == "click":
                if step.get("x") == last_step.get("x") and step.get("y") == last_step.get("y"):
                    continue
                    
            optimized.append(step)
            last_step = step
            
        return optimized
