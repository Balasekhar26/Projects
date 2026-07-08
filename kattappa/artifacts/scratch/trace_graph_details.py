import sys
import os
os.environ["PYTEST_CURRENT_TEST"] = "1"

from backend.core.graph import run_graph

# Let's override evaluator's guard_relevance_reply to print args
import backend.agents.evaluator as evaluator_mod
orig_guard = evaluator_mod.guard_relevance_reply

def debug_guard(user_input, draft):
    print("DEBUG GUARD ARGS:")
    print(" - USER_INPUT:", repr(user_input))
    print(" - DRAFT:", repr(draft))
    res = orig_guard(user_input, draft)
    print(" - RETURNED:", repr(res))
    return res

evaluator_mod.guard_relevance_reply = debug_guard

state = run_graph("explain your builder brain and how you work")
print("FINAL RESULT:", repr(state.get("result")))
