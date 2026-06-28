from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import threading

from backend.api.v1.common import *

app = FastAPI(title="Kattappa AI OS Backend", version="10.0.0")

from backend.api.v1.chat import chat_router
from backend.api.v1.voice import voice_router
from backend.api.v1.memory import memory_router
from backend.api.v1.planner import planner_router
from backend.api.v1.safety import safety_router
from backend.api.v1.models import models_router

app.include_router(chat_router, prefix="/api/v1")
app.include_router(chat_router)

app.include_router(voice_router, prefix="/api/v1")
app.include_router(voice_router)

app.include_router(memory_router, prefix="/api/v1")
app.include_router(memory_router)

app.include_router(planner_router, prefix="/api/v1")
app.include_router(planner_router)

app.include_router(safety_router, prefix="/api/v1")
app.include_router(safety_router)

app.include_router(models_router, prefix="/api/v1")
app.include_router(models_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:8000",
        "http://localhost:8000",
        "http://tauri.localhost",
        "https://tauri.localhost",
        "tauri://localhost",
        "null",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def start_startup_tasks():
    from backend.core.cluster_runtime import internet_hub_worker_poll_loop
    thread = threading.Thread(target=internet_hub_worker_poll_loop, daemon=True)
    thread.start()

    # Start Step 9.0 Daily Research Loop
    try:
        from backend.core.research_scheduler import ResearchScheduler
        ResearchScheduler.start()
    except Exception:
        pass

    # Run Experiment Sandbox startup orphan cleanup scan
    try:
        from backend.core.experiment_sandbox import ExperimentManager
        ExperimentManager.cleanup_orphans()
    except Exception:
        pass

    # Warm up default fast and coder models in the background on startup
    from backend.core.config import load_config
    from backend.core.adaptive_runtime import WarmupManager
    try:
        cfg = load_config()
        WarmupManager.warm_model_background(cfg.model_map["fast"], cfg.ollama_host)
    except Exception:
        pass

@app.on_event("shutdown")
def stop_shutdown_tasks():
    """Stop background scheduler threads on shutdown."""
    try:
        ResearchScheduler.stop()
    except Exception:
        pass
