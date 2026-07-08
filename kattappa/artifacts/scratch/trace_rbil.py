import os
os.environ["PYTEST_CURRENT_TEST"] = "1"
from backend.agents.planner import route_task

r = route_task("Remember the project codename bluefalcon42 for this history test.")
print("ROUTED AGENT:", r.get("agent"))
print("ROUTED PAYLOAD:", r)
