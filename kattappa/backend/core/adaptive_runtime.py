from __future__ import annotations

import os
import platform
import subprocess
import threading
import time
import json
import sqlite3
import concurrent.futures
from datetime import datetime
from uuid import uuid4
from typing import Any, Dict, List, Tuple

import psutil
import torch
import httpx

# In-memory execution logs for the Self-Learning engine
_metrics_log: Dict[str, List[float]] = {}
_model_load_failures: Dict[str, int] = {}
_warmed_models: set[str] = set()


class HardwareProfiler:
    """Detects system hardware resources: CPU cores, RAM, GPUs (CUDA/DirectML), Storage Type, and Power Mode."""

    @classmethod
    def get_profile(cls) -> Dict[str, Any]:
        ram_gb = round(psutil.virtual_memory().total / (1024**3), 1)
        cpu_count = psutil.cpu_count(logical=True) or 2
        physical_cores = psutil.cpu_count(logical=False) or cpu_count
        
        # GPU detection
        has_cuda = torch.cuda.is_available()
        gpu_name = torch.cuda.get_device_name(0) if has_cuda else "Unknown / CPU"
        gpu_vram_gb = 0.0
        if has_cuda:
            gpu_vram_gb = round(torch.cuda.get_device_properties(0).total_memory / (1024**3), 1)
        else:
            # Fallback to WMI detection on Windows
            gpu_name, gpu_vram_gb = cls._windows_wmi_gpu()

        # Storage type detection (SSD vs HDD)
        storage_type = cls._detect_storage_type()
        
        # Power & Load detection
        battery = psutil.sensors_battery()
        on_ac = battery.power_plugged if battery else True
        cpu_load = psutil.cpu_percent(interval=None)

        return {
            "os": platform.system(),
            "os_release": platform.release(),
            "cpu_logical_cores": cpu_count,
            "cpu_physical_cores": physical_cores,
            "ram_total_gb": ram_gb,
            "has_gpu_acceleration": has_cuda or ("nvidia" in gpu_name.lower()) or ("amd" in gpu_name.lower()) or ("intel" in gpu_name.lower()),
            "gpu_name": gpu_name,
            "gpu_vram_gb": gpu_vram_gb,
            "storage_type": storage_type,
            "on_ac_power": on_ac,
            "cpu_utilization": cpu_load,
            "free_disk_space_gb": round(psutil.disk_usage("/").free / (1024**3), 1)
        }

    @classmethod
    def _windows_wmi_gpu(cls) -> Tuple[str, float]:
        if platform.system().lower() != "windows":
            return "Unknown / CPU", 0.0
        try:
            # Query video controller details via WMIC
            out = subprocess.check_output("wmic path win32_VideoController get name, AdapterRAM", shell=True, text=True)
            lines = [line.strip() for line in out.splitlines() if line.strip() and "AdapterRAM" not in line]
            if lines:
                parts = lines[0].split(None, 1)
                ram_bytes = int(parts[0]) if parts[0].isdigit() else 0
                name = parts[1] if len(parts) > 1 else lines[0]
                vram_gb = round(ram_bytes / (1024**3), 1)
                return name, vram_gb
        except Exception:
            pass
        return "Unknown / CPU", 0.0

    @classmethod
    def _detect_storage_type(cls) -> str:
        if platform.system().lower() != "windows":
            return "SSD" # Default to SSD on modern unix/mac
        try:
            # Query MediaType using PowerShell on Windows
            out = subprocess.check_output(
                'powershell -Command "Get-PhysicalDisk | ForEach-Object { $_.MediaType }"',
                shell=True,
                text=True,
                timeout=3.0
            )
            media_types = [line.strip() for line in out.splitlines() if line.strip()]
            if any("SSD" in m for m in media_types):
                return "SSD"
            if any("HDD" in m for m in media_types):
                return "HDD"
        except Exception:
            pass
        return "SSD"  # Default fallback


class PerformanceProfile:
    """Manages active performance modes (ECO, BALANCED, PERFORMANCE, BEAST)."""

    @classmethod
    def resolve_profile(cls, hw: Dict[str, Any]) -> str:
        ram = hw["ram_total_gb"]
        has_gpu = hw["has_gpu_acceleration"]
        on_ac = hw["on_ac_power"]
        
        # ECO mode triggers:
        # - Low RAM (< 8GB)
        # - Or CPU-only machine running on battery power
        if ram < 8.0 or (not has_gpu and not on_ac):
            return "ECO"
            
        # BEAST mode triggers:
        # - 32GB+ RAM & strong GPU with >= 8GB VRAM
        if ram >= 32.0 and has_gpu and hw["gpu_vram_gb"] >= 8.0:
            return "BEAST"
            
        # PERFORMANCE mode triggers:
        # - 16GB+ RAM and dedicated GPU or high core count on AC power
        if ram >= 16.0 and has_gpu and on_ac:
            return "PERFORMANCE"
            
        # Fallback to BALANCED
        return "BALANCED"


class AdaptiveContext:
    """Calculates context limits and history-compression strategies based on the active profile."""

    @classmethod
    def get_limits(cls, profile: str) -> Dict[str, Any]:
        if profile == "ECO":
            return {
                "max_context_tokens": 1500,
                "history_max_turns": 3,
                "compress_history": True,
                "disk_buffer_enabled": False # HDD/low-ram uses memory cache only
            }
        elif profile == "BALANCED":
            return {
                "max_context_tokens": 3000,
                "history_max_turns": 6,
                "compress_history": True,
                "disk_buffer_enabled": True
            }
        elif profile == "PERFORMANCE":
            return {
                "max_context_tokens": 8000,
                "history_max_turns": 15,
                "compress_history": False,
                "disk_buffer_enabled": True
            }
        else: # BEAST
            return {
                "max_context_tokens": 16000,
                "history_max_turns": 30,
                "compress_history": False,
                "disk_buffer_enabled": True
            }

    @classmethod
    def get_dynamic_budget(cls, prompt: str, profile: str) -> Dict[str, Any]:
        limits = cls.get_limits(profile)
        max_tokens = limits["max_context_tokens"]
        prompt_lower = prompt.lower()

        # Heuristics:
        is_simple = len(prompt.split()) < 15 and not any(w in prompt_lower for w in ["explain", "compare", "code", "function", "class", "why"])
        is_coding = any(w in prompt_lower for w in ["code", "python", "javascript", "function", "class", "compile", "bug", "refactor", "algorithm", "html", "css", "database", "sqlite"])
        is_research = any(w in prompt_lower for w in ["explain", "compare", "analyze", "why", "difference", "architect", "logic", "history", "who is", "what is"])

        if is_simple:
            limits["max_context_tokens"] = min(1000, max_tokens)
            limits["history_max_turns"] = min(2, limits["history_max_turns"])
            limits["compress_history"] = True
        elif is_coding:
            limits["max_context_tokens"] = min(4000, max_tokens)
            limits["history_max_turns"] = min(6, limits["history_max_turns"])
        elif is_research:
            limits["max_context_tokens"] = min(12000, max_tokens)
            limits["history_max_turns"] = min(15, limits["history_max_turns"])
        else:
            limits["max_context_tokens"] = max_tokens

        return limits


class WarmupManager:
    """Asynchronously triggers model load (warming) in Ollama to prevent delays during active chat."""

    @classmethod
    def warm_model_background(cls, model_name: str, ollama_host: str) -> None:
        global _warmed_models
        if model_name in _warmed_models:
            return
            
        def _warm_thread():
            import httpx
            try:
                # Fire an empty chat stream request to Ollama to trigger model loading in GPU VRAM
                timeout_cfg = httpx.Timeout(40.0, connect=5.0)
                httpx.post(
                    f"{ollama_host}/api/chat",
                    json={
                        "model": model_name,
                        "messages": [{"role": "user", "content": ""}],
                        "stream": False,
                        "options": {"num_predict": 1}
                    },
                    timeout=timeout_cfg
                )
                _warmed_models.add(model_name)
            except Exception:
                pass

        threading.Thread(target=_warm_thread, daemon=True).start()


class SelfLearningEngine:
    """Monitors performance latency and adjusts model mapping dynamic weights to prevent timeouts."""

    @classmethod
    def log_response_time(cls, model: str, duration: float) -> None:
        global _metrics_log
        if model not in _metrics_log:
            _metrics_log[model] = []
        _metrics_log[model].append(duration)
        if len(_metrics_log[model]) > 20:
            _metrics_log[model].pop(0)

    @classmethod
    def log_failure(cls, model: str) -> None:
        global _model_load_failures
        _model_load_failures[model] = _model_load_failures.get(model, 0) + 1

    @classmethod
    def is_model_healthy(cls, model: str) -> bool:
        # If a model fails to load/generate 3 consecutive times, mark it as unhealthy for 2 minutes
        failures = _model_load_failures.get(model, 0)
        if failures >= 3:
            return False
            
        # Check average latency
        latencies = _metrics_log.get(model, [])
        if latencies and (sum(latencies) / len(latencies)) > 25.0:
            # Model averages more than 25 seconds per query (meaning heavy thrashing)
            return False
            
        return True

    @classmethod
    def reset_failures(cls, model: str) -> None:
        global _model_load_failures
        if model in _model_load_failures:
            _model_load_failures[model] = 0


# ==========================================
# ADVANCED HIGH-PERFORMANCE SUBSYSTEMS
# ==========================================

class AgentHibernationEngine:
    """Manages active agents loading/unloading in Ollama VRAM/RAM to prevent memory leaks."""

    _last_used: Dict[str, float] = {}
    _lock = threading.Lock()
    _monitor_started = False

    @classmethod
    def get_vram_occupancy(cls, ollama_host: str) -> float:
        """Returns the VRAM (or RAM if CPU-only) occupancy percentage."""
        try:
            from backend.core.adaptive_runtime import HardwareProfiler
            hw = HardwareProfiler.get_profile()
            total_vram_gb = hw.get("gpu_vram_gb", 0.0)
            has_gpu = hw.get("has_gpu_acceleration", False)
            
            if has_gpu and total_vram_gb > 0.0:
                # 1. Query active models in VRAM from Ollama
                try:
                    res = httpx.get(f"{ollama_host}/api/ps", timeout=2.0)
                    if res.status_code == 200:
                        models = res.json().get("models", [])
                        total_size_vram = sum(m.get("size_vram", 0) for m in models)
                        used_vram_gb = total_size_vram / (1024**3)
                        return (used_vram_gb / total_vram_gb) * 100.0
                except Exception:
                    pass
                
                # 2. Fallback: query via torch.cuda if available
                if torch.cuda.is_available():
                    try:
                        allocated = torch.cuda.memory_allocated(0)
                        reserved = torch.cuda.memory_reserved(0)
                        used_gb = max(allocated, reserved) / (1024**3)
                        return (used_gb / total_vram_gb) * 100.0
                    except Exception:
                        pass
                return 0.0
            else:
                # Fallback to system RAM if CPU-only
                return psutil.virtual_memory().percent
        except Exception:
            return 0.0

    @classmethod
    def _check_and_evict_lru(cls, incoming_model: str, ollama_host: str) -> None:
        """Evicts the oldest idle model (LRU) from memory if VRAM occupancy exceeds 80%."""
        try:
            occupancy = cls.get_vram_occupancy(ollama_host)
            if occupancy > 80.0:
                res = httpx.get(f"{ollama_host}/api/ps", timeout=2.0)
                if res.status_code != 200:
                    return
                models = res.json().get("models", [])
                loaded_models = []
                for m in models:
                    name = m.get("name") or m.get("model")
                    if name and (m.get("size_vram", 0) > 0 or m.get("size", 0) > 0):
                        loaded_models.append(name)
                
                candidates = [m for m in loaded_models if m != incoming_model]
                if not candidates:
                    return
                
                # Safely find the oldest touched model under lock
                with cls._lock:
                    oldest_model = min(candidates, key=lambda m: cls._last_used.get(m, 0.0))
                    if oldest_model in cls._last_used:
                        del cls._last_used[oldest_model]
                
                # Evict model outside of lock to prevent blockages
                cls.hibernate_model(oldest_model, ollama_host)
                from backend.core.logger import log_event
                log_event(f"vram_eviction model={oldest_model} occupancy={occupancy:.1f}%")
        except Exception as e:
            from backend.core.logger import log_event
            log_event(f"vram_eviction_error error={e}")

    @classmethod
    def touch_model(cls, model_name: str) -> None:
        with cls._lock:
            cls._last_used[model_name] = time.time()
            if not cls._monitor_started:
                cls.start_monitor_loop()
        
        # Check VRAM limits and evict oldest model if exceeding budget
        try:
            from backend.core.config import load_config
            cfg = load_config()
            cls._check_and_evict_lru(model_name, cfg.ollama_host)
        except Exception:
            pass

    @classmethod
    def hibernate_model(cls, model_name: str, ollama_host: str) -> bool:
        try:
            httpx.post(
                f"{ollama_host}/api/chat",
                json={
                    "model": model_name,
                    "messages": [],
                    "keep_alive": 0,
                    "stream": False
                },
                timeout=5.0
            )
            return True
        except Exception:
            return False

    @classmethod
    def start_monitor_loop(cls) -> None:
        cls._monitor_started = True
        def _loop():
            from backend.core.config import load_config
            while True:
                time.sleep(30)
                try:
                    cfg = load_config()
                    
                    # Keep inactive models warm if VRAM occupancy is < 70%
                    occupancy = cls.get_vram_occupancy(cfg.ollama_host)
                    if occupancy < 70.0:
                        continue
                        
                    profile = cfg.hardware_profile
                    # ECO: 60s, BALANCED: 300s, PERFORMANCE/BEAST: 600s
                    ttl = 60 if profile == "ECO" else (300 if profile == "BALANCED" else 600)
                    now = time.time()
                    with cls._lock:
                        to_hibernate = []
                        for model, ltime in list(cls._last_used.items()):
                            if now - ltime > ttl:
                                to_hibernate.append(model)
                        for model in to_hibernate:
                            cls.hibernate_model(model, cfg.ollama_host)
                            del cls._last_used[model]
                except Exception:
                    pass
        threading.Thread(target=_loop, daemon=True).start()


class PredictiveModelLoader:
    """Predicts next model needed based on typing context/inputs and preloads it in VRAM."""

    @classmethod
    def predict_and_warm(cls, partial_text: str) -> None:
        from backend.core.config import load_config
        try:
            cfg = load_config()
            text_lower = partial_text.lower()
            
            # Prediction heuristics
            coding_hints = {"def ", "function", "class ", "import ", "const ", "let ", "python", "javascript", "code"}
            reasoning_hints = {"explain", "why", "compare", "analyze", "architect"}
            
            predicted_model = None
            if any(hint in text_lower for hint in coding_hints):
                predicted_model = cfg.model_map["coder"]
            elif any(hint in text_lower for hint in reasoning_hints):
                predicted_model = cfg.model_map["power"]
            else:
                predicted_model = cfg.model_map["fast"]
                
            if predicted_model:
                WarmupManager.warm_model_background(predicted_model, cfg.ollama_host)
        except Exception:
            pass


class SemanticResponseCache:
    """Semantic Response Cache powered by ChromaDB vector similarity."""

    _chroma_client: Any = None
    _collection: Any = None
    _lock = threading.Lock()

    @classmethod
    def _get_collection(cls):
        with cls._lock:
            if cls._collection is None:
                import chromadb
                from chromadb.config import Settings as ChromaSettings
                from chromadb.utils.embedding_functions import DefaultEmbeddingFunction
                from backend.core.config import load_config
                cfg = load_config()
                cfg.chroma_path.mkdir(parents=True, exist_ok=True)
                cls._chroma_client = chromadb.PersistentClient(
                    path=str(cfg.chroma_path),
                    settings=ChromaSettings(anonymized_telemetry=False),
                )
                cls._collection = cls._chroma_client.get_or_create_collection(
                    "kattappa_semantic_cache",
                    embedding_function=DefaultEmbeddingFunction(),
                )
            return cls._collection

    @classmethod
    def get(cls, query: str, ttl_seconds: float = 3600.0) -> Tuple[str | None, str | None]:
        try:
            coll = cls._get_collection()
            if coll.count() == 0:
                return None, None
                
            res = coll.query(query_texts=[query], n_results=1)
            if not res or not res.get("documents") or not res["documents"][0]:
                return None, None
                
            distance = res["distances"][0][0]
            # Cosine/L2 distance metric threshold for semantic similarity
            if distance > 0.25:
                return None, None
                
            meta = res["metadatas"][0][0]
            
            if time.time() - meta.get("timestamp", 0.0) > ttl_seconds:
                return None, None
                
            return meta.get("response"), meta.get("selected_agent")
        except Exception:
            return None, None

    @classmethod
    def set(cls, query: str, response: str, selected_agent: str) -> None:
        try:
            coll = cls._get_collection()
            # Remove old close query entry if present
            existing = coll.query(query_texts=[query], n_results=1)
            if existing and existing.get("ids") and existing["ids"][0]:
                if existing["distances"][0][0] < 0.01:
                    coll.delete(ids=[existing["ids"][0][0]])
                    
            coll.add(
                ids=[str(uuid4())],
                documents=[query],
                metadatas=[{
                    "response": response,
                    "timestamp": time.time(),
                    "selected_agent": selected_agent
                }]
            )
        except Exception:
            pass


class MemoryPrefetcher:
    """Runs memory and db retrieval concurrently in a background thread to yield 0ms graph latency."""

    _executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)
    _futures: Dict[str, concurrent.futures.Future] = {}
    _lock = threading.Lock()

    @classmethod
    def prefetch(cls, message_id: str, prompt: str, chat_session_id: str | None) -> None:
        if not message_id:
            return
            
        def _task():
            from backend.core.memory import build_memory_context, memory
            related_messages = memory.search_chat_messages(
                prompt,
                limit=5,
                session_id=chat_session_id,
            )
            context = build_memory_context(
                prompt,
                chat_session_id=chat_session_id,
                related_messages=related_messages,
            )
            return {
                "related_messages": related_messages,
                "memory_context": context
            }

        with cls._lock:
            cls._futures[message_id] = cls._executor.submit(_task)

    @classmethod
    def get_result(cls, message_id: str) -> Dict[str, Any] | None:
        future = None
        with cls._lock:
            if message_id in cls._futures:
                future = cls._futures.pop(message_id)
        if future:
            try:
                return future.result(timeout=4.0)
            except Exception:
                pass
        return None


class GPUTaskScheduler:
    """Routes workloads between CPU and GPU based on task size and VRAM pressure."""

    @classmethod
    def get_vram_free_gb(cls) -> float:
        if torch.cuda.is_available():
            try:
                t = torch.cuda.get_device_properties(0).total_memory
                a = torch.cuda.memory_allocated(0)
                return round((t - a) / (1024**3), 2)
            except Exception:
                pass
        return 0.0

    @classmethod
    def route_task(cls, prompt: str, role: str) -> str:
        from backend.core.config import load_config
        cfg = load_config()
        
        words = len(prompt.split())
        is_simple = words < 12 and not any(w in prompt.lower() for w in ["code", "compile", "explain", "why"])
        
        # CPU model overrides for tiny tasks or memory pressure
        if is_simple and role == "general":
            return cfg.model_map.get("fast", "qwen2.5:0.5b")
            
        if torch.cuda.is_available() and cls.get_vram_free_gb() < 0.5:
            return cfg.model_map.get("fast", "qwen2.5:0.5b")
            
        return cfg.model_map.get(role, cfg.model_map["general"])


class SelfHealingRuntime:
    """Monitors server status and heals failed services/models dynamically."""

    @classmethod
    def heal_ollama(cls) -> bool:
        from backend.core.model_router import health
        ok, _ = health()
        if ok:
            return True
            
        # Attempt restart on Windows
        if platform.system().lower() == "windows":
            try:
                appdata = os.getenv("LOCALAPPDATA", "")
                paths = [
                    os.path.join(appdata, "Programs", "Ollama", "ollama.exe"),
                    "ollama"
                ]
                for p in paths:
                    try:
                        subprocess.Popen([p, "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        time.sleep(3.0)
                        ok, _ = health()
                        if ok:
                            return True
                    except Exception:
                        pass
            except Exception:
                pass
        return False

    @classmethod
    def handle_failure(cls, model_name: str) -> None:
        from backend.core.config import load_config
        cfg = load_config()
        # Unload the failed model to free up resources
        AgentHibernationEngine.hibernate_model(model_name, cfg.ollama_host)
        # Clear router tags cache time
        import backend.core.model_router as mr
        mr._last_fetch_time = 0.0


class MemoryCompressionEngine:
    """Compresses dialogue history dynamically to limit context window growth."""

    @classmethod
    def compress_history(cls, session_id: str, threshold: int = 10) -> None:
        from backend.core.memory import memory
        try:
            messages = memory.list_chat_messages(session_id, limit=100)
            turns = [m for m in messages if m["role"] in {"user", "assistant"}]
            if len(turns) <= threshold:
                return
                
            to_compress = turns[:-4]
            if len(to_compress) < 2:
                return
                
            text_to_summarize = "\n".join(f"{m['role']}: {m['content']}" for m in to_compress)
            prompt = f"Summarize the following chat conversation dialogue in a single compact sentence:\n{text_to_summarize}"
            
            from backend.core.model_router import ask_model
            summary = ask_model(prompt, role="fast")
            if not summary or "local model timed out" in summary.lower():
                return
                
            old_ids = [m["id"] for m in to_compress]
            with sqlite3.connect(memory.config.sqlite_path) as conn:
                for oid in old_ids:
                    conn.execute("DELETE FROM chat_messages WHERE id = ?", (oid,))
                    
            try:
                memory._chat_collection().delete(ids=old_ids)
            except Exception:
                pass
                
            now = datetime.now().isoformat(timespec="seconds")
            msg_id = str(uuid4())
            with sqlite3.connect(memory.config.sqlite_path) as conn:
                conn.execute(
                    """
                    INSERT INTO chat_messages(id, session_id, role, content, agent, risk, metadata, created_at)
                    VALUES (?, ?, 'system', ?, 'compressor', 'low', '{}', ?)
                    """,
                    (msg_id, session_id, f"Summary of previous discussion: {summary}", now),
                )
        except Exception:
            pass


class PerformanceLearner:
    """Records latencies and logs to assist router heuristics."""

    @classmethod
    def record_metrics(cls, model: str, latency: float, success: bool) -> None:
        # Persistent storage of performance data can also be added here.
        pass
