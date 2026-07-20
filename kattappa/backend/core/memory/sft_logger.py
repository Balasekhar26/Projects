import os
import json
import time
from typing import Any

def save_sft_training_pair(state: dict[str, Any], rating: int = 5) -> None:
    """
    Saves a successful task execution context into a JSONL format 
    suitable for fine-tuning Kattappa models.
    """
    try:
        # Create output directory if it doesn't exist
        os.makedirs(os.path.join("backend", "data", "training"), exist_ok=True)
        
        # Extract fields
        instruction = state.get("user_input") or ""
        
        # Format the plan: could be list or string
        raw_plan = state.get("operator_plan")
        if isinstance(raw_plan, list):
            plan = raw_plan
        elif isinstance(raw_plan, str):
            plan = [raw_plan]
        else:
            plan = []
            
        # Try to extract used tools from state/logs
        tools = []
        if state.get("selected_agent"):
            tools.append(state["selected_agent"])
        # Also check tool_request
        if state.get("tool_request"):
            tool_req = state["tool_request"]
            if isinstance(tool_req, dict) and tool_req.get("tool"):
                tools.append(tool_req["tool"])
                
        # Result and status
        result = state.get("result") or ""
        
        # Build training pair dict
        pair = {
            "instruction": instruction,
            "plan": plan,
            "tools": list(set(tools)),
            "result": result,
            "rating": rating,
            "timestamp": time.time()
        }
        
        # Append to jsonl file
        file_path = os.path.join("backend", "data", "training", "sft_dataset.jsonl")
        with open(file_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(pair, ensure_ascii=False) + "\n")
            
    except Exception as e:
        # Fail silently to avoid breaking the core chat handler
        pass
