from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any

from backend.core.config import runtime_data_root


def _path() -> Path:
    return runtime_data_root() / "backend" / "data" / "resource_governance.json"


class ResourceGovernor:
    _lock = threading.Lock()
    
    # Quota Limits
    CPU_LIMIT_PERCENT = 90.0
    RAM_LIMIT_MIN_AVAILABLE_MB = 500.0
    DISK_LIMIT_BYTES = 100 * 1024 * 1024  # 100 MB
    NETWORK_LIMIT_DOWNLOAD_BYTES = 50 * 1024 * 1024  # 50 MB
    NETWORK_LIMIT_REQUESTS = 100
    TOKENS_LIMIT = 50000
    CONCURRENT_TASKS_LIMIT = 5
    AUDIO_DURATION_LIMIT_SECONDS = 30.0
    AUDIO_SIZE_LIMIT_BYTES = 5 * 1024 * 1024  # 5 MB
    CONCURRENT_VOICE_SESSIONS_LIMIT = 2

    # Human Attention Budget — finite interrupt budget per rolling hour.
    # Prevents the scheduler from overwhelming the user with escalations.
    ATTENTION_TOKEN_LIMIT: int = 10          # max attention-requiring actions per hour
    ATTENTION_TOKEN_WINDOW_SECS: float = 3600.0  # rolling window (1 hour)

    MEMORY_MAX_RECORDS = 10_000
    MEMORY_MAX_BYTES_PER_AGENT = 5 * 1024 * 1024  # 5 MB
    MEMORY_MAX_WRITES_PER_MINUTE = 60

    @classmethod
    def _load(cls) -> dict[str, Any]:
        try:
            p = _path()
            if p.exists():
                data = json.loads(p.read_text(encoding="utf-8"))
                if "concurrent_voice_sessions" not in data:
                    data["concurrent_voice_sessions"] = 0
                if "memory_records" not in data:
                    data["memory_records"] = 0
                if "memory_bytes_used" not in data:
                    data["memory_bytes_used"] = {}
                if "memory_writes_this_minute" not in data:
                    data["memory_writes_this_minute"] = 0
                if "memory_write_window_start" not in data:
                    data["memory_write_window_start"] = 0.0
                if "attention_tokens_reserved" not in data:
                    data["attention_tokens_reserved"] = 0
                if "attention_tokens_consumed" not in data:
                    data["attention_tokens_consumed"] = 0
                if "reserved_cpu_percent" not in data:
                    data["reserved_cpu_percent"] = 0.0
                if "reserved_ram_mb" not in data:
                    data["reserved_ram_mb"] = 0.0
                return data
        except Exception:
            pass
        return {
            "disk_used_bytes": 0,
            "network_download_bytes": 0,
            "network_requests": 0,
            "tokens_used": 0,
            "concurrent_tasks": 0,
            "concurrent_voice_sessions": 0,
            "memory_records": 0,
            "memory_bytes_used": {},
            "memory_writes_this_minute": 0,
            "memory_write_window_start": 0.0,
            "attention_tokens_used": 0,
            "attention_tokens_reserved": 0,
            "attention_tokens_consumed": 0,
            "attention_window_start": 0.0,
            "reserved_cpu_percent": 0.0,
            "reserved_ram_mb": 0.0,
        }

    @classmethod
    def _save(cls, data: dict[str, Any]) -> None:
        try:
            p = _path()
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception:
            pass

    @classmethod
    def reset(cls) -> None:
        with cls._lock:
            cls._save({
                "disk_used_bytes": 0,
                "network_download_bytes": 0,
                "network_requests": 0,
                "tokens_used": 0,
                "concurrent_tasks": 0,
                "concurrent_voice_sessions": 0,
                "memory_records": 0,
                "memory_bytes_used": {},
                "memory_writes_this_minute": 0,
                "memory_write_window_start": 0.0,
                "attention_tokens_used": 0,
                "attention_tokens_reserved": 0,
                "attention_tokens_consumed": 0,
                "attention_window_start": 0.0,
                "reserved_cpu_percent": 0.0,
                "reserved_ram_mb": 0.0,
            })

    @classmethod
    def get_status(cls) -> dict[str, Any]:
        """Returns the current resource governor status."""
        import psutil
        with cls._lock:
            data = cls._load()
            
        cpu_usage = psutil.cpu_percent(interval=None)
        ram_available = psutil.virtual_memory().available / (1024 * 1024)
        
        consumed_attn = int(data.get("attention_tokens_consumed", 0))
        reserved_attn = int(data.get("attention_tokens_reserved", 0))
        available_attn = max(0, cls.ATTENTION_TOKEN_LIMIT - consumed_attn - reserved_attn)

        return {
            "system_cpu_percent": cpu_usage,
            "system_cpu_limit": cls.CPU_LIMIT_PERCENT,
            "system_ram_available_mb": round(ram_available, 1),
            "system_ram_limit_min_mb": cls.RAM_LIMIT_MIN_AVAILABLE_MB,
            "disk_used_bytes": data["disk_used_bytes"],
            "disk_limit_bytes": cls.DISK_LIMIT_BYTES,
            "network_download_bytes": data["network_download_bytes"],
            "network_limit_download_bytes": cls.NETWORK_LIMIT_DOWNLOAD_BYTES,
            "network_requests": data["network_requests"],
            "network_limit_requests": cls.NETWORK_LIMIT_REQUESTS,
            "tokens_used": data["tokens_used"],
            "tokens_limit": cls.TOKENS_LIMIT,
            "concurrent_tasks": data["concurrent_tasks"],
            "concurrent_tasks_limit": cls.CONCURRENT_TASKS_LIMIT,
            "concurrent_voice_sessions": data.get("concurrent_voice_sessions", 0),
            "concurrent_voice_sessions_limit": cls.CONCURRENT_VOICE_SESSIONS_LIMIT,
            "memory_records": data.get("memory_records", 0),
            "memory_limit_records": cls.MEMORY_MAX_RECORDS,
            "memory_bytes_used": data.get("memory_bytes_used", {}),
            "memory_limit_bytes_per_agent": cls.MEMORY_MAX_BYTES_PER_AGENT,
            "memory_writes_this_minute": data.get("memory_writes_this_minute", 0),
            "memory_limit_writes_per_minute": cls.MEMORY_MAX_WRITES_PER_MINUTE,
            "attention_tokens_used": consumed_attn,
            "attention_tokens_reserved": reserved_attn,
            "attention_tokens_consumed": consumed_attn,
            "attention_token_limit": cls.ATTENTION_TOKEN_LIMIT,
            "attention_tokens_remaining": available_attn,
            "attention_tokens_available": available_attn,
            "reserved_cpu_percent": data.get("reserved_cpu_percent", 0.0),
            "reserved_ram_mb": data.get("reserved_ram_mb", 0.0),
        }

    @classmethod
    def check_and_charge_resources(cls, agent_name: str, action: str, params: dict[str, Any]) -> dict[str, Any]:
        """Checks if executing the action is within limits. Charges request counts early."""
        if agent_name == "monitoring":
            return {"success": True}

        import psutil
        action_upper = action.upper()
        
        # 1. CPU check
        cpu_usage = psutil.cpu_percent(interval=None)
        # Handle cases where psutil returns 0 initially
        if cpu_usage > cls.CPU_LIMIT_PERCENT:
            return {"success": False, "error": f"CPU usage is too high ({cpu_usage}% > {cls.CPU_LIMIT_PERCENT}%)"}

        # 2. RAM check
        ram_available = psutil.virtual_memory().available / (1024 * 1024)
        if ram_available < cls.RAM_LIMIT_MIN_AVAILABLE_MB:
            return {"success": False, "error": f"Available RAM is too low ({ram_available:.1f}MB < {cls.RAM_LIMIT_MIN_AVAILABLE_MB}MB)"}

        with cls._lock:
            data = cls._load()

            # 3. Disk Quota pre-check (estimate content/code size if writing)
            if action_upper in ("CREATE_FILE", "WRITE_FILE", "FILE_WRITE", "FILE_MODIFY", "PATCH_CODE"):
                content = params.get("code") or params.get("content") or ""
                target_file = params.get("target") or params.get("path")
                old_size = 0
                if target_file and os.path.exists(target_file):
                    try:
                        old_size = os.path.getsize(target_file)
                    except Exception:
                        pass
                proposed_delta = max(0, len(content) - old_size)
                if data["disk_used_bytes"] + proposed_delta > cls.DISK_LIMIT_BYTES:
                    return {"success": False, "error": f"Disk quota exceeded (cannot write additional {proposed_delta} bytes)"}

            # 4. Network download pre-check
            if action_upper == "BROWSER_DOWNLOAD_FILE":
                if data["network_download_bytes"] >= cls.NETWORK_LIMIT_DOWNLOAD_BYTES:
                    return {"success": False, "error": "Network download quota exceeded"}

            # 5. Network requests check (e.g. search, read, outbound)
            if action_upper in ("BROWSER_SEARCH", "BROWSER_READ", "BROWSER_NAVIGATE", "BROWSER_MAP_LINKS", "BROWSER_EXTRACT_INFO", "BROWSER_FILL_FORM", "BROWSER_CLICK_SUBMIT", "BROWSER_LOGIN", "NETWORK_REQUEST", "SEND_EMAIL"):
                if data["network_requests"] >= cls.NETWORK_LIMIT_REQUESTS:
                    return {"success": False, "error": "Network requests limit reached"}
                # Charge request count early
                data["network_requests"] += 1

            # 6. Concurrent task limits check
            if action_upper in ("RUN_SHELL", "DEPLOY", "PATCH_CODE"):
                if data["concurrent_tasks"] >= cls.CONCURRENT_TASKS_LIMIT:
                    return {"success": False, "error": f"Concurrent task limit reached ({data['concurrent_tasks']} active)"}
                # Charge active task count
                data["concurrent_tasks"] += 1

            # 7. Voice limits check
            if action_upper in ("VOICE_MICROPHONE_READ", "VOICE_SPEAKER_OUTPUT", "VOICE_STT", "VOICE_TTS", "VOICE_WAKE_WORD_DETECTION"):
                if data.get("concurrent_voice_sessions", 0) >= cls.CONCURRENT_VOICE_SESSIONS_LIMIT:
                    return {"success": False, "error": f"Concurrent voice session limit reached ({data.get('concurrent_voice_sessions', 0)} active)"}
                
                # Charge voice session early
                data["concurrent_voice_sessions"] = data.get("concurrent_voice_sessions", 0) + 1

            # 8. Audio file checks (duration and size)
            audio_size = params.get("audio_size_bytes")
            if audio_size is not None and audio_size > cls.AUDIO_SIZE_LIMIT_BYTES:
                return {"success": False, "error": f"Audio file size exceeds quota ({audio_size} bytes > {cls.AUDIO_SIZE_LIMIT_BYTES} bytes)"}

            audio_duration = params.get("audio_duration_seconds")
            if audio_duration is not None and audio_duration > cls.AUDIO_DURATION_LIMIT_SECONDS:
                return {"success": False, "error": f"Audio duration exceeds quota ({audio_duration}s > {cls.AUDIO_DURATION_LIMIT_SECONDS}s)"}

            # 9. Memory limits check
            if action_upper == "COMMIT_MEMORY_DELTA":
                content = params.get("content") or ""
                write_bytes = len(content.encode("utf-8"))
                
                # Check rate limiting
                now = time.time()
                window_start = data.get("memory_write_window_start", 0.0)
                if now - window_start > 60.0:
                    data["memory_write_window_start"] = now
                    data["memory_writes_this_minute"] = 0
                    
                if data.get("memory_writes_this_minute", 0) >= cls.MEMORY_MAX_WRITES_PER_MINUTE:
                    return {"success": False, "error": "Memory write rate limit exceeded"}
                    
                # Check global record limit
                if data.get("memory_records", 0) >= cls.MEMORY_MAX_RECORDS:
                    return {"success": False, "error": "Memory global record quota exceeded"}
                    
                # Check per-agent byte limit
                agent_bytes_dict = data.get("memory_bytes_used")
                if not isinstance(agent_bytes_dict, dict):
                    agent_bytes_dict = {}
                agent_used = agent_bytes_dict.get(agent_name, 0)
                if agent_used + write_bytes > cls.MEMORY_MAX_BYTES_PER_AGENT:
                    return {"success": False, "error": f"Memory byte quota exceeded for agent {agent_name} (cannot write additional {write_bytes} bytes)"}
                    
                # Charge write rate limit count early
                data["memory_writes_this_minute"] = data.get("memory_writes_this_minute", 0) + 1

            cls._save(data)

        return {"success": True}

    @classmethod
    def record_execution_usage(cls, agent_name: str, action: str, params: dict[str, Any], result: Any) -> None:
        """Updates resource usage figures after action execution completes."""
        action_upper = action.upper()
        
        with cls._lock:
            data = cls._load()

            # 1. Update disk usage on file mutations
            if action_upper in ("CREATE_FILE", "WRITE_FILE", "FILE_WRITE", "FILE_MODIFY", "PATCH_CODE"):
                target_file = params.get("target") or params.get("path")
                content = params.get("code") or params.get("content") or ""
                old_size = 0
                if target_file and os.path.exists(target_file):
                    try:
                        old_size = os.path.getsize(target_file)
                    except Exception:
                        pass
                proposed_delta = max(0, len(content) - old_size)
                data["disk_used_bytes"] += proposed_delta

            # 2. Update network download usage on downloads
            if action_upper == "BROWSER_DOWNLOAD_FILE" and isinstance(result, dict) and result.get("success"):
                dl_size = result.get("size_bytes", 0)
                data["network_download_bytes"] += dl_size

            # 3. Decrement active concurrent task when completed
            if action_upper in ("RUN_SHELL", "DEPLOY", "PATCH_CODE"):
                data["concurrent_tasks"] = max(0, data["concurrent_tasks"] - 1)

            # 4. Decrement active concurrent voice session when completed
            if action_upper in ("VOICE_MICROPHONE_READ", "VOICE_SPEAKER_OUTPUT", "VOICE_STT", "VOICE_TTS", "VOICE_WAKE_WORD_DETECTION"):
                data["concurrent_voice_sessions"] = max(0, data.get("concurrent_voice_sessions", 0) - 1)

            # 5. Update memory records and bytes on COMMIT_MEMORY_DELTA success
            if action_upper == "COMMIT_MEMORY_DELTA" and isinstance(result, dict) and result.get("success"):
                content = params.get("content") or ""
                write_bytes = len(content.encode("utf-8"))
                data["memory_records"] = data.get("memory_records", 0) + 1
                
                agent_bytes_dict = data.get("memory_bytes_used")
                if not isinstance(agent_bytes_dict, dict):
                    agent_bytes_dict = {}
                agent_bytes_dict[agent_name] = agent_bytes_dict.get(agent_name, 0) + write_bytes
                data["memory_bytes_used"] = agent_bytes_dict

            # 6. Update memory records on DELETE_MEMORY success
            if action_upper == "DELETE_MEMORY" and isinstance(result, dict) and result.get("success"):
                data["memory_records"] = max(0, data.get("memory_records", 0) - 1)

            cls._save(data)

    @classmethod
    def check_token_budget(cls, estimated_tokens: int) -> bool:
        """Determines if the estimated tokens will fit within the remaining limit."""
        with cls._lock:
            data = cls._load()
        return data["tokens_used"] + estimated_tokens <= cls.TOKENS_LIMIT

    @classmethod
    def charge_tokens(cls, token_count: int) -> None:
        """Accrues consumed tokens to the budget tracker."""
        with cls._lock:
            data = cls._load()
            data["tokens_used"] += token_count
            cls._save(data)

    @classmethod
    def decrement_active_tasks(cls) -> None:
        """Decrements the count of active concurrent tasks manually (e.g. background task ended)."""
        with cls._lock:
            data = cls._load()
            data["concurrent_tasks"] = max(0, data["concurrent_tasks"] - 1)
            cls._save(data)

    @classmethod
    def start_voice_session(cls) -> dict[str, Any]:
        with cls._lock:
            data = cls._load()
            if data.get("concurrent_voice_sessions", 0) >= cls.CONCURRENT_VOICE_SESSIONS_LIMIT:
                return {"success": False, "error": "Concurrent voice sessions limit reached"}
            data["concurrent_voice_sessions"] = data.get("concurrent_voice_sessions", 0) + 1
            cls._save(data)
            return {"success": True}

    @classmethod
    def end_voice_session(cls) -> None:
        with cls._lock:
            data = cls._load()
            data["concurrent_voice_sessions"] = max(0, data.get("concurrent_voice_sessions", 0) - 1)
            cls._save(data)

    # ------------------------------------------------------------------
    # Resource Reservations
    # ------------------------------------------------------------------

    @classmethod
    def reserve_resources(cls, cpu_percent: float, ram_mb: float) -> None:
        with cls._lock:
            data = cls._load()
            data["reserved_cpu_percent"] = data.get("reserved_cpu_percent", 0.0) + cpu_percent
            data["reserved_ram_mb"] = data.get("reserved_ram_mb", 0.0) + ram_mb
            cls._save(data)

    @classmethod
    def release_resources(cls, cpu_percent: float, ram_mb: float) -> None:
        with cls._lock:
            data = cls._load()
            data["reserved_cpu_percent"] = max(0.0, data.get("reserved_cpu_percent", 0.0) - cpu_percent)
            data["reserved_ram_mb"] = max(0.0, data.get("reserved_ram_mb", 0.0) - ram_mb)
            cls._save(data)

    @classmethod
    def sync_reservations(cls, cpu_percent: float, ram_mb: float) -> None:
        with cls._lock:
            data = cls._load()
            data["reserved_cpu_percent"] = cpu_percent
            data["reserved_ram_mb"] = ram_mb
            cls._save(data)

    # ------------------------------------------------------------------
    # Human Attention Token Budget
    # ------------------------------------------------------------------

    @classmethod
    def _refresh_attention_window(cls, data: dict) -> dict:
        """Reset the attention token counter if the rolling window has expired."""
        now = time.time()
        window_start = data.get("attention_window_start", 0.0)
        if now - window_start >= cls.ATTENTION_TOKEN_WINDOW_SECS:
            data["attention_tokens_consumed"] = 0
            data["attention_tokens_used"] = 0
            data["attention_window_start"] = now
        return data

    @classmethod
    def check_attention_budget(cls, cost: int = 1) -> bool:
        """Return True if the attention budget can absorb ``cost`` more tokens.

        Automatically resets the counter if the rolling window has expired.
        Thread-safe.
        """
        with cls._lock:
            data = cls._refresh_attention_window(cls._load())
            consumed = int(data.get("attention_tokens_consumed", 0))
            reserved = int(data.get("attention_tokens_reserved", 0))
            return (consumed + reserved + cost) <= cls.ATTENTION_TOKEN_LIMIT

    @classmethod
    def reserve_attention_tokens(cls, cost: int = 1) -> bool:
        """Reserve ``cost`` attention tokens for an in-flight action."""
        with cls._lock:
            data = cls._refresh_attention_window(cls._load())
            consumed = int(data.get("attention_tokens_consumed", 0))
            reserved = int(data.get("attention_tokens_reserved", 0))
            if consumed + reserved + cost > cls.ATTENTION_TOKEN_LIMIT:
                return False
            data["attention_tokens_reserved"] = reserved + cost
            cls._save(data)
            return True

    @classmethod
    def charge_attention_tokens(cls, cost: int = 1) -> bool:
        """Deduct ``cost`` attention tokens directly (Compatibility/fallback)."""
        with cls._lock:
            data = cls._refresh_attention_window(cls._load())
            consumed = int(data.get("attention_tokens_consumed", 0))
            if consumed + cost > cls.ATTENTION_TOKEN_LIMIT:
                return False
            data["attention_tokens_consumed"] = consumed + cost
            data["attention_tokens_used"] = consumed + cost
            cls._save(data)
            return True

    @classmethod
    def release_and_consume_attention_tokens(cls, cost: int, consume: bool = True) -> None:
        """Release reserved attention tokens, and optionally mark them consumed."""
        with cls._lock:
            data = cls._load()
            reserved = int(data.get("attention_tokens_reserved", 0))
            data["attention_tokens_reserved"] = max(0, reserved - cost)
            if consume:
                consumed = int(data.get("attention_tokens_consumed", 0))
                data["attention_tokens_consumed"] = consumed + cost
                data["attention_tokens_used"] = consumed + cost
            cls._save(data)

    @classmethod
    def sync_attention_reservations(cls, tokens: int) -> None:
        with cls._lock:
            data = cls._load()
            data["attention_tokens_reserved"] = tokens
            cls._save(data)

    @classmethod
    def reset_attention_tokens(cls) -> None:
        """Force-reset the attention token counter (e.g. on session start or admin override)."""
        with cls._lock:
            data = cls._load()
            data["attention_tokens_used"] = 0
            data["attention_tokens_consumed"] = 0
            data["attention_tokens_reserved"] = 0
            data["attention_window_start"] = time.time()
            cls._save(data)
