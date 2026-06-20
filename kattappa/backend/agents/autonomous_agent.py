import time
import re
import os
import tempfile
import pyautogui
from backend.core.config import load_config
from backend.core.obsidian_memory import ObsidianMemory
from backend.agents.vision_agent import VisionAgent
from backend.tools.computer_control import ComputerControl

class AutonomousAgent:
    def __init__(self, model: str = None, max_steps: int = 5) -> None:
        config = load_config()
        self.model = model or config.model_map.get("general", "qwen3:4b")
        self.max_steps = max_steps
        self.memory = ObsidianMemory()
        self.vision = VisionAgent()
        self.control = ComputerControl()
        
    def execute_task(self, goal: str) -> str:
        self.memory.write_daily_note(content=f"Starting autonomous task: '{goal}'", category="autonomous-agent")
        
        step = 0
        state = "running"
        temp_dir = tempfile.gettempdir()
        
        while state == "running" and step < self.max_steps:
            step += 1
            screenshot_path = os.path.join(temp_dir, f"kattappa_step_{step}.png")
            
            try:
                pyautogui.screenshot(screenshot_path)
            except Exception as e:
                return f"Failed to take screenshot: {e}"
                
            try:
                x_norm, y_norm, description = self.vision.locate_element(screenshot_path, f"next step for: {goal}")
                action = self._determine_action(description, x_norm, y_norm)
                
                self.memory.write_daily_note(
                    content=f"Step {step}: Action determined -> {action}", 
                    category="autonomous-agent"
                )
                
                if action.startswith("DONE"):
                    state = "done"
                    break
                
                self._run_action(action)
                time.sleep(1.0)
            except Exception as e:
                error_msg = f"Autonomous loop step {step} error: {e}"
                self.memory.write_daily_note(content=error_msg, category="error")
                return error_msg
                
        self.memory.write_daily_note(
            content=f"Finished autonomous task. Status: {state}", 
            category="autonomous-agent"
        )
        return f"Task execution finished. Status: {state}"

    def _determine_action(self, description: str, x: float, y: float) -> str:
        clean_desc = description.upper()
        if "DONE" in clean_desc or "COMPLETE" in clean_desc:
            return "DONE"
        if "TYPE" in clean_desc:
            match = re.search(r'TYPE\((["\'])(.*?)\1\)', description, re.IGNORECASE)
            if match:
                return f'TYPE("{match.group(2)}")'
            return f'CLICK({x}, {y})'
        if "PRESS" in clean_desc:
            match = re.search(r'PRESS\((["\'])(.*?)\1\)', description, re.IGNORECASE)
            if match:
                return f'PRESS("{match.group(2)}")'
        if "HOTKEY" in clean_desc:
            match = re.search(r'HOTKEY\((.*?)\)', description, re.IGNORECASE)
            if match:
                return f'HOTKEY({match.group(1)})'
                
        return f"CLICK({x}, {y})"

    def _run_action(self, action: str) -> None:
        if action.startswith("CLICK"):
            match = re.search(r'CLICK\(\s*([\d\.]+)\s*,\s*([\d\.]+)\s*\)', action)
            if match:
                self.control.click(float(match.group(1)), float(match.group(2)))
        elif action.startswith("TYPE"):
            match = re.search(r'TYPE\((["\'])(.*?)\1\)', action)
            if match:
                self.control.type_text(match.group(2))
        elif action.startswith("PRESS"):
            match = re.search(r'PRESS\((["\'])(.*?)\1\)', action)
            if match:
                self.control.press_key(match.group(2))
        elif action.startswith("HOTKEY"):
            match = re.search(r'HOTKEY\((.*?)\)', action)
            if match:
                args = [arg.strip(' "\'') for arg in match.group(1).split(',')]
                self.control.hotkey(*args)
