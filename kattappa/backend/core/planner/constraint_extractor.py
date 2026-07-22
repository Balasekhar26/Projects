from __future__ import annotations
import os
import json
from backend.core.model_router import ask_model

class ConstraintExtractor:
    @classmethod
    def extract_constraints(cls, goal: str) -> dict:
        import sys
        use_mock = (
            os.getenv("KATTAPPA_ENV") == "test" or 
            os.getenv("KATTAPPA_TEST_MODE") == "true" or
            os.getenv("KATTAPPA_MOCK_LLM") == "true"
        )
        if use_mock:
            constraints = {
                "offline": False,
                "ram_limit": None,
                "network": True,
                "local_only": False
            }
            lower_goal = goal.lower()
            if "offline" in lower_goal or "no internet" in lower_goal:
                constraints["offline"] = True
                constraints["network"] = False
            if "8gb" in lower_goal:
                constraints["ram_limit"] = "8GB"
            if "local" in lower_goal:
                constraints["local_only"] = True
            return constraints
        else:
            prompt = (
                f"Identify constraints in the task objective: \"{goal}\"\n"
                f"Output ONLY a valid JSON object containing keys:\n"
                f"- offline (boolean)\n"
                f"- ram_limit (string or null)\n"
                f"- network (boolean)\n"
                f"- local_only (boolean)\n"
                f"Example: "
                f'{{"offline": true, "ram_limit": "8GB", "network": false, "local_only": true}}'
            )
            try:
                res = ask_model(prompt, role="planning")
                clean_res = res.strip()
                if clean_res.startswith("```json"):
                    clean_res = clean_res[7:]
                if clean_res.endswith("```"):
                    clean_res = clean_res[:-3]
                clean_res = clean_res.strip()
                return json.loads(clean_res)
            except Exception:
                return {
                    "offline": False,
                    "ram_limit": None,
                    "network": True,
                    "local_only": False
                }
