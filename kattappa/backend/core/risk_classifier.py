import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, Tuple

class RiskClassifier:
    def __init__(self, db_conn=None):
        self.db = db_conn
        from backend.core.config import load_security_config
        sec_config = load_security_config()
        
        self.PROTECTED_CORE = sec_config.get("protected_core") or [
            "execution_policy.py",
            "approval_engine.py",
            "risk_classifier.py",
            "audit_ledger.py",
            "action_scheduler.py",
            "action_broker.py",
            "validators.py",
            "capability_broker.py",
            "security_config.yaml"
        ]
        # Static risk map
        self.STATIC_RISK_MAP = sec_config.get("static_risk_map") or {
            # Level 0: Safe
            "READ_FILE": 0,
            "LIST_DIR": 0,
            "SEARCH_MEMORY": 0,
            "RECALL_MEMORY": 0,
            "GET_STATUS": 0,
            "RUN_TESTS": 0,
            "RUN_BENCHMARKS": 0,
            "ANALYZE_CODE": 0,
            "GENERATE_CODE": 0,
            "CREATE_PROPOSAL": 0,
            "ANALYZE_REPO": 0,
            "FILE_PARSE": 0,
            
            # Level 1: Low Risk
            "DESKTOP_READ_SCREEN": 1,
            "DESKTOP_SCREENSHOT": 1,
            "DESKTOP_OPEN_APP": 1,
            "DESKTOP_MOUSE_MOVE": 1,
            "DESKTOP_MOUSE_CLICK": 1,
            "DESKTOP_KEYBOARD_TYPING": 1,
            "DESKTOP_CLOSE_APP": 1,
            "DESKTOP_KILL_PROCESS": 1,
            "VOICE_MICROPHONE_READ": 1,
            "VOICE_SPEAKER_OUTPUT": 1,
            "VOICE_STT": 1,
            "VOICE_TTS": 1,
            "VOICE_WAKE_WORD_DETECTION": 1,
            "BROWSER_READ": 1,
            "BROWSER_NAVIGATE": 1,
            "BROWSER_SEARCH": 1,
            
            # Level 2: Moderate Risk
            "CREATE_FILE": 2,
            "WRITE_FILE": 2,
            "EDIT_FILE": 2,
            "MOVE_FILE": 2,
            "BROWSER_DOWNLOAD_FILE": 2,
            "COMMIT_MEMORY_DELTA": 2,
            "PIN_MEMORY": 2,
            "UNPIN_MEMORY": 2,
            "EXPIRE_MEMORY": 2,
            "CONSOLIDATE_MEMORY": 2,
            "AGING_MEMORY": 2,
            "FILE_WRITE": 2,
            "FILE_MODIFY": 2,
            "BROWSER_FILL_FORM": 2,
            "BROWSER_CLICK_SUBMIT": 2,
            "BROWSER_LOGIN": 2,
            
            # Level 3: High Risk
            "PATCH_CODE": 3,
            "GIT_COMMIT": 3,
            "GIT_PUSH": 3,
            "RUN_SHELL": 3,
            "INSTALL_PACKAGE": 3,
            "NETWORK_REQUEST": 3,
            "SEND_EMAIL": 3,
            "DELETE_MEMORY": 3,
            "ROLLBACK_MEMORY": 3,
            
            # Level 4: Critical
            "DELETE_FILE": 4,
            "DESKTOP_DELETE_FILE": 4,
            "DESKTOP_SHUTDOWN": 4,
            "DESKTOP_SETTINGS": 4,
            "DEPLOY": 4,
            "FILE_DELETE": 4,
            
            # Level 5: Dangerous / Prohibited
            "FORMAT_DRIVE": 5,
            "DISABLE_SECURITY": 5,
            "TRANSFER_MONEY": 5,
            "EXFILTRATE_DATA": 5,
        }

    def canonicalize_path(self, path_str: str) -> str:
        # Resolves symlinks and removes relative directory traversal escapes
        try:
            p = Path(path_str).expanduser()
            return str(p.resolve())
        except Exception:
            return str(Path(path_str).absolute())

    def is_contained_in_any(self, path_str: str, allowed_dirs: list[Path]) -> bool:
        try:
            target = Path(self.canonicalize_path(path_str))
            for allowed in allowed_dirs:
                try:
                    resolved_allowed = allowed.resolve()
                    if resolved_allowed in target.parents or target == resolved_allowed:
                        return True
                except Exception:
                    continue
        except Exception:
            pass
        return False

    def calculate_action_hash(self, tool: str, payload: Dict[str, Any], context: Dict[str, Any]) -> str:
        # Serialize the action payload + session state + environment metadata
        data_to_hash = {
            "tool": tool.upper(),
            "payload": payload,
            "context": context
        }
        serialized = json.dumps(data_to_hash, sort_keys=True, default=str)
        return hashlib.sha256(serialized.encode('utf-8')).hexdigest()

    def assess_risk(self, session_id: str, tool: str, payload: Dict[str, Any]) -> Tuple[int, str]:
        """
        Computes risk score on the (Action x Target x Session Context) tuple.
        Deny-by-default: Unknown configurations default directly to Level 5.
        """
        tool_upper = tool.upper()
        # Supply Chain check for INSTALL_PACKAGE
        if tool_upper == "INSTALL_PACKAGE":
            package_name = payload.get("package_name") or payload.get("package")
            version = payload.get("version")
            package_hash = payload.get("hash") or payload.get("package_hash")
            source = payload.get("source") or payload.get("package_source")
            
            # If it's a raw CLI installation command without structured metadata (e.g. from coder_node),
            # allow it to proceed to human approval (base level 3). Enforce strict supply chain checks
            # only if structured metadata payload is supplied.
            if not package_name and not version and not package_hash and not source and "command" in payload:
                pass
            else:
                if not package_name or not version or not package_hash or not source:
                    return 5, "CRITICAL: Missing package verification details (package_name, version, hash, or source)."
                    
                if "==" not in version:
                    return 5, "CRITICAL: Package version is not pinned (must use '==' syntax)."
                    
                if not (source.startswith("http://") or source.startswith("https://")):
                    return 5, f"CRITICAL: Untrusted/undefined package source: {source}"

        # 1. Base Tool Class Determination - default to 5 if unknown
        base_level = self.STATIC_RISK_MAP.get(tool_upper, 5)
        
        # 2. Fetch Session Taint Status
        taint_level = 0
        if self.db:
            try:
                cursor = self.db.cursor()
                cursor.execute("SELECT taint_level FROM security_sessions WHERE session_id = ?", (session_id,))
                row = cursor.fetchone()
                if row:
                    taint_level = row[0]
            except Exception:
                pass

        # 3. Path/Target Validation (CD1/Bypass Prevention)
        from backend.core.config import load_config
        config = load_config()
        allowed_dirs = [config.workspace_dir, config.root]
        if os.getenv("KATTAPPA_ENV") == "test":
            allowed_dirs.append(Path(os.getcwd()))
        
        paths_to_check = []
        if "path" in payload:
            paths_to_check.append(payload["path"])
        if "target" in payload:
            paths_to_check.append(payload["target"])
        if "filepath" in payload:
            paths_to_check.append(payload["filepath"])
        if "src" in payload:
            paths_to_check.append(payload["src"])
        if "dest" in payload:
            paths_to_check.append(payload["dest"])
            
        # Check command string for common shell chaining and path traversal attempts
        if tool_upper == "RUN_SHELL" and "command" in payload:
            cmd = payload["command"]
            if any(escape in cmd for escape in ["..", "/etc", "C:\\Windows", ".ssh", "shadow", "kattappa_ai_os.db"]):
                return 5, f"CRITICAL: Protected path or traversal detected in shell command: {cmd}"
            
            # Supply chain check: Block raw package install commands in RUN_SHELL
            install_patterns = [
                r"\bpip\s+install\b",
                r"\bpip3\s+install\b",
                r"\bnpm\s+install\b",
                r"\bnpm\s+i\b",
                r"\byarn\s+add\b",
                r"\bpnpm\s+add\b",
                r"\bapt-get\s+install\b",
                r"\bapt\s+install\b",
                r"\bcargo\s+install\b",
                r"\bgem\s+install\b",
                r"\bbrew\s+install\b"
            ]
            if any(re.search(pattern, cmd) for pattern in install_patterns):
                return 5, f"CRITICAL: Raw package installation detected in RUN_SHELL command. Must use INSTALL_PACKAGE tool."

        for p_str in paths_to_check:
            if not p_str:
                continue
            canonical = self.canonicalize_path(p_str)
            # Check traversal or system/protected paths
            if any(protected in canonical for protected in [
                "/etc", "C:\\Windows", ".ssh", "shadow", "kattappa_ai_os.db"
            ]):
                return 5, f"CRITICAL: Access to protected system path attempted: {p_str}"
                
            # If we are writing/mutating (Level >= 2), we MUST be inside workspace_dir or root
            if base_level >= 2:
                basename = os.path.basename(canonical)
                if basename in self.PROTECTED_CORE or "backend/core" in canonical:
                    return 5, f"CRITICAL: Attempt to mutate protected core constitution file: {p_str}"
                
                if not self.is_contained_in_any(canonical, allowed_dirs):
                    return 5, f"CRITICAL: Path is outside the allowed workspace: {p_str}"
        
        # 4. Contextual Escalation (Trifecta Breaker)
        effective_risk = base_level
        if taint_level > 0:
            effective_risk = base_level + taint_level
            
        effective_risk = max(0, min(5, effective_risk))
        
        cwd = payload.get("cwd", os.getcwd())
        if os.getenv("KATTAPPA_ENV") == "test":
            cwd = "test_cwd"
            
        context_metadata = {
            "session_taint_level": taint_level,
            "cwd": cwd,
            "env_keys": sorted(list(os.environ.keys()))
        }
        action_hash = self.calculate_action_hash(tool, payload, context_metadata)
        
        return effective_risk, action_hash
