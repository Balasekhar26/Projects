import json
import re

# Import tools
from kattappa_runtime.tools.calculator import Calculator
from kattappa_runtime.tools.clock import Clock
from kattappa_runtime.tools.search_mock import SearchMock

class ToolRouter:
    def __init__(self):
        self.tools = {}
        # Register default tools
        self.register_tool("calculator", Calculator())
        self.register_tool("clock", Clock())
        self.register_tool("search_mock", SearchMock())

    def register_tool(self, name, tool_instance):
        """Registers a named tool module executor."""
        self.tools[name] = tool_instance

    def extract_json(self, text):
        """Extracts the first valid JSON block from a string, handling markdown markers."""
        clean = text.strip()
        # Look for ```json ... ``` or ``` ... ```
        if "```json" in clean:
            clean = clean.split("```json")[-1].split("```")[0].strip()
        elif "```" in clean:
            clean = clean.split("```")[-1].split("```")[0].strip()
            
        # Try to find a balanced JSON block using regex if raw parsing fails
        try:
            return json.loads(clean)
        except Exception:
            # Fallback regex search for JSON boundaries
            match = re.search(r"(\{.*\})", clean, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(1))
                except Exception:
                    pass
        return None

    def parse_and_execute(self, model_output):
        """Parses model response for tool calls, executes them, and formats outcome."""
        parsed = self.extract_json(model_output)
        if not parsed:
            return None
            
        # Standard schema check: {"tool": "...", "arguments": {...}} or {"call": "...", "args": {...}}
        tool_name = parsed.get("tool") or parsed.get("call")
        arguments = parsed.get("arguments") or parsed.get("args") or {}
        
        if not tool_name:
            return None
            
        if tool_name not in self.tools:
            return {
                "error": f"Tool '{tool_name}' is not registered in Kattappa OS."
            }
            
        print(f"\n[Tool Execution] Routing to: {tool_name} with args {arguments}")
        
        try:
            tool_instance = self.tools[tool_name]
            # Execute clock if takes no arguments, otherwise unpack args
            if tool_name == "clock":
                res = tool_instance.execute()
            else:
                # If arguments is a dict, unpack it, else pass as positional
                if isinstance(arguments, dict):
                    res = tool_instance.execute(**arguments)
                else:
                    res = tool_instance.execute(arguments)
            return {
                "tool": tool_name,
                "result": res
            }
        except Exception as e:
            return {
                "tool": tool_name,
                "error": f"Execution error in {tool_name}: {e}"
            }
