from __future__ import annotations

import time
import re
from typing import Any, Dict, List, Optional
from backend.core.memory_broker import MemoryBroker
from backend.core.logger import log_event


class ReasoningEngine:
    """Reasoning Engine (Phase 3 Core).
    
    Analyzes objectives before planning to extract assumptions, identify risks,
    detect missing information, and formulate clarifying questions.
    """

    @classmethod
    def analyze(
        cls,
        goal_title: str,
        goal_description: str,
        session_id: str = "primary"
    ) -> dict[str, Any]:
        """Analyzes a goal or user query to produce a reasoning context structure."""
        now = time.time()
        text = f"{goal_title} {goal_description}".lower()
        
        # 1. Goal Understanding
        domain = "General"
        if any(w in text for w in ["rust", "python", "compile", "code", "file"]):
            domain = "Software Development"
        elif any(w in text for w in ["deploy", "server", "cloud", "docker"]):
            domain = "DevOps/Infrastructure"
        elif any(w in text for w in ["drone", "fly", "hardware", "iot"]):
            domain = "Hardware/IoT"

        # 2. Context Retrieval via Memory Broker
        context_data = {}
        try:
            context_data = MemoryBroker.retrieve(query=goal_title, session_id=session_id)
        except Exception as e:
            log_event(f"ReasoningEngine analyze: memory retrieval failed: {e}")

        # 3. Assumption Extraction
        assumptions = []
        if domain == "Software Development":
            assumptions.append("Implicit dependency: compiler or interpreter is installed locally.")
            assumptions.append("Target file paths are relative to the active workspace folder.")
        elif domain == "DevOps/Infrastructure":
            assumptions.append("Implicit dependency: target cloud egress endpoints are whitelisted.")
            assumptions.append("Proper configuration files (.env, docker-compose) are present.")
        elif domain == "Hardware/IoT":
            assumptions.append("Physical limitation: route distances must respect battery and wind speeds.")
        else:
            assumptions.append("Assumes environment context is clean and permissions are pre-authorized.")

        # 4. Missing Information Detection
        missing_info = []
        clarification_questions = []

        if domain == "Software Development":
            # Check if language is specified
            if not any(w in text for w in ["rust", "python", "javascript", "c++", "go", "java"]):
                missing_info.append("Programming language choice is unspecified.")
                clarification_questions.append("Which programming language or runtime environment should be used?")
            # Check if output file path is specified
            has_path_ref = "file" in text or "path" in text or any(ext in text for ext in [".py", ".rs", ".js", ".cpp", ".go", ".java", ".json", ".c", ".h"])
            if not has_path_ref:
                missing_info.append("Target path or output filename is unspecified.")
                clarification_questions.append("What is the target filename or output path for the compilation?")

        if domain == "DevOps/Infrastructure":
            # Check if host target or port is specified
            if "port" not in text and "host" not in text and "url" not in text:
                missing_info.append("Target server host, port, or environment URL is missing.")
                clarification_questions.append("What is the destination host IP, target port, or environment URL?")

        # 5. Risk Assessment
        risks = []
        if "delete" in text or "remove" in text or "clean" in text:
            risks.append({
                "category": "REVERSIBILITY_RISK",
                "severity": "high",
                "message": "Destructive operations (delete/clean) are highly irreversible. Rollback checkpoints must be created."
            })
        if "sudo" in text or "root" in text or "admin" in text:
            risks.append({
                "category": "PRIVILEGE_RISK",
                "severity": "critical",
                "message": "Elevated privileges requested. Violates minimum-security privilege bounds."
            })

        # 6. Resolve final status
        status = "READY_TO_PLAN"
        if clarification_questions:
            status = "REQUIRES_CLARIFICATION"

        return {
            "status": status,
            "domain": domain,
            "assumptions": assumptions,
            "missing_information": missing_info,
            "clarification_questions": clarification_questions,
            "risks": risks,
            "memory_context": context_data.get("unified_context_string", "No matching historical memory found."),
            "analyzed_at": now
        }
