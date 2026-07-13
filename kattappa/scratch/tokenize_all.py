import tokenize
import os

files = [
    'backend/planner/world_state.py',
    'backend/planner/task_decomposer.py',
    'backend/planner/gtpyhop_adapter.py',
    'backend/planner/belief_store.py',
    'backend/planner/utility_engine.py',
    'backend/planner/checkpoint_store.py',
    'backend/planner/goal_stack.py',
    'backend/planner/constraint_solver.py',
    'backend/planner/planner_interface.py',
    'backend/core/operator.py'
]

print("=== START DIAGNOSTIC ===")
for file in files:
    filepath = os.path.join("c:/Users/balu/Projects/kattappa", file)
    if not os.path.exists(filepath):
        print(f"File not found: {filepath}")
        continue
        
    print(f"=== FILE ===\n{file}")
    with open(filepath, 'rb') as f:
        try:
            tokens = list(tokenize.tokenize(f.readline))
            found_any = False
            for tok in tokens:
                if tok.type == tokenize.STRING:
                    # Look for \P or \p escape sequences
                    # A raw escape sequence in a raw literal will have \P, or in normal literal it might be unescaped
                    if '\\P' in tok.string or '\\p' in tok.string or '\\' in tok.string:
                        print(f"Line: {tok.start[0]}")
                        print(f"String: {repr(tok.string)}")
                        print()
                        found_any = True
            if not found_any:
                print("No string tokens containing backslashes found.")
        except Exception as e:
            print(f"Tokenize error: {e}")
    print("-" * 50)
