import re

class Calculator:
    def __init__(self):
        # Strict whitelist of allowed math characters to prevent arbitrary script execution
        self.allowed = re.compile(r"^[0-9\+\-\*\/\(\)\.\s]+$")

    def execute(self, expression):
        """Safely evaluates basic arithmetic expressions."""
        clean_expr = str(expression).strip()
        if not self.allowed.match(clean_expr):
            return {"error": "Invalid characters detected in math expression."}
            
        try:
            # Safe evaluation utilizing restricted globals/locals
            res = eval(clean_expr, {"__builtins__": None}, {})
            return {"result": str(res)}
        except Exception as e:
            return {"error": f"Evaluation error: {e}"}
