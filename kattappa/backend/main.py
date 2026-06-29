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
from backend.api.v1.telemetry import telemetry_router
from backend.api.v1.knowledge_graph import knowledge_graph_router
from backend.api.v1.ecl import ecl_router
from backend.api.v1.mce import router as mce_router
from backend.api.v1.wse import router as wse_router
from backend.api.v1.provenance import router as provenance_router
from backend.api.v1.beliefs import router as beliefs_router
from backend.api.v1.planning import router as core_planning_router
from backend.api.v1.execution import router as execution_router
from backend.api.v1.reflection import router as reflection_router
from backend.api.v1.learning import router as learning_router
from backend.api.v1.integration import router as integration_router





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

app.include_router(telemetry_router, prefix="/api/v1")
app.include_router(telemetry_router)

app.include_router(knowledge_graph_router, prefix="/api/v1")
app.include_router(knowledge_graph_router)

app.include_router(ecl_router, prefix="/api/v1")
app.include_router(ecl_router)

app.include_router(mce_router, prefix="/api/v1")
app.include_router(mce_router)

app.include_router(wse_router, prefix="/api/v1")
app.include_router(wse_router)

app.include_router(provenance_router, prefix="/api/v1")
app.include_router(provenance_router)

app.include_router(beliefs_router, prefix="/api/v1")
app.include_router(beliefs_router)

app.include_router(core_planning_router, prefix="/api/v1")
app.include_router(core_planning_router)

app.include_router(execution_router, prefix="/api/v1")
app.include_router(execution_router)

app.include_router(reflection_router, prefix="/api/v1")
app.include_router(reflection_router)

app.include_router(learning_router, prefix="/api/v1")
app.include_router(learning_router)

app.include_router(integration_router, prefix="/api/v1")
app.include_router(integration_router)









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

    # Start Phase K13 KG Sync Scheduler
    try:
        from backend.core.kg_scheduler import start_kg_scheduler

        start_kg_scheduler()
    except Exception:
        pass

    # Run Experiment Sandbox startup orphan cleanup scan
    try:
        from backend.core.experiment_sandbox import ExperimentManager

        ExperimentManager.cleanup_orphans()
    except Exception:
        pass

    # Start Program 3 Memory Consolidation Engine Scheduler
    try:
        from backend.core.mce.scheduler import MCEScheduler

        MCEScheduler.get_instance().start()
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
        from backend.core.research_scheduler import ResearchScheduler

        ResearchScheduler.stop()
    except Exception:
        pass

    try:
        from backend.core.kg_scheduler import stop_kg_scheduler

        stop_kg_scheduler()
    except Exception:
        pass

    try:
        from backend.core.mce.scheduler import MCEScheduler

        MCEScheduler.get_instance().stop()
    except Exception:
        pass
