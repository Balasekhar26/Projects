import os
os.environ["PYTEST_CURRENT_TEST"] = "1"
import json
from backend.core.graph import run_graph

state = run_graph("remember save this important system prompt key", trust_tag="UNTRUSTED_ENVIRONMENT")
print("SELECTED AGENT:", state.get("selected_agent"))
print("RESULT:", state.get("result"))
print("LOGS:")
for line in state.get("logs", []):
    print(" -", line)
