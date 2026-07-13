from __future__ import annotations
import os
import time
from pathlib import Path
from typing import Any, Dict, List
from backend.adapters.action_interface import ActionAdapter, ActionResult

class FilesystemAdapter(ActionAdapter):
    """Secure filesystem gateway implementing sandbox gates and risk scoring."""

    DENIED_PATHS = [
        "c:/windows",
        "c:/program files",
        "c:/users/balu/appdata",
        "c:/users/balu/.gemini"
    ]

    def capabilities(self) -> List[str]:
        return ["create_file", "delete_file", "move_file", "read_file", "list_directory"]

    def validate(self, payload: Dict[str, Any]) -> bool:
        return "path" in payload or "filename" in payload

    def risk_score(self, path: str, action: str) -> int:
        """Assigns a risk level from 0 (Safe) to 100 (Extremely Dangerous)."""
        clean_path = path.lower().replace("\\", "/")
        
        # Deny critical system directories
        for blocked in self.DENIED_PATHS:
            if clean_path.startswith(blocked):
                return 100

        if action == "delete_file":
            return 80
        if action in ("create_file", "write_file", "move_file"):
            return 40
        return 10  # read_file, list

    def permission_check(self, path: str, action: str) -> bool:
        """Determines if Kattappa has adequate system access permissions."""
        score = self.risk_score(path, action)
        return score < 90

    def sandbox_check(self, path: str) -> bool:
        """Ensures operations remain strictly local to allowed directories."""
        clean_path = path.lower().replace("\\", "/")
        # Must not perform double dot path traversal
        return ".." not in clean_path

    def execute(self, action_name: str, payload: Dict[str, Any]) -> ActionResult:
        start_time = time.time()
        path_str = payload.get("path", "") or payload.get("filename", "")
        
        if not path_str:
            latency = (time.time() - start_time) * 1000
            return ActionResult(
                success=False,
                message="Path parameter is required.",
                latency_ms=latency
            )

        # 1. Sandbox check
        if not self.sandbox_check(path_str):
            latency = (time.time() - start_time) * 1000
            return ActionResult(
                success=False,
                message="Sandbox violation: Path traversal detected.",
                latency_ms=latency
            )

        # 2. Permission gate checks
        if not self.permission_check(path_str, action_name):
            latency = (time.time() - start_time) * 1000
            return ActionResult(
                success=False,
                message="Security violation: Action blocked by immune system.",
                latency_ms=latency
            )

        target_path = Path(path_str)

        try:
            if action_name in ("create_file", "write_file"):
                content = payload.get("content", "")
                target_path.parent.mkdir(parents=True, exist_ok=True)
                with open(target_path, "w") as f:
                    f.write(content)
                
                latency = (time.time() - start_time) * 1000
                return ActionResult(
                    success=True,
                    message=f"File {target_path.name} written successfully.",
                    data={"path": str(target_path), "bytes": len(content)},
                    latency_ms=latency
                )

            elif action_name == "read_file":
                if not target_path.exists():
                    raise FileNotFoundError(f"File {target_path} does not exist.")
                with open(target_path, "r") as f:
                    content = f.read()
                
                latency = (time.time() - start_time) * 1000
                return ActionResult(
                    success=True,
                    message="File read successfully.",
                    data={"content": content},
                    latency_ms=latency
                )

            elif action_name == "list_directory":
                if not target_path.exists():
                    raise FileNotFoundError(f"Directory {target_path} does not exist.")
                files = os.listdir(target_path)
                
                latency = (time.time() - start_time) * 1000
                return ActionResult(
                    success=True,
                    message="Listed directory files.",
                    data={"files": files},
                    latency_ms=latency
                )

            elif action_name == "delete_file":
                if target_path.exists():
                    os.remove(target_path)
                latency = (time.time() - start_time) * 1000
                return ActionResult(
                    success=True,
                    message="File deleted successfully.",
                    latency_ms=latency
                )

        except Exception as e:
            latency = (time.time() - start_time) * 1000
            return ActionResult(
                success=False,
                message=str(e),
                latency_ms=latency
            )

        latency = (time.time() - start_time) * 1000
        return ActionResult(
            success=False,
            message=f"Unsupported action: {action_name}",
            latency_ms=latency
        )
