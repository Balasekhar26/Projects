import warnings
import ast

warnings.filterwarnings("error", category=SyntaxWarning)

with open("backend/planner/world_state.py", "r", encoding="utf-8") as f:
    source = f.read()

try:
    ast.parse(source)
    print("AST Parse OK")
except Exception as e:
    print(type(e), e)
