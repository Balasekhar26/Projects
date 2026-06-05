from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ai_system.agents.master import MasterAgent
from ai_system.agents.tasks import TaskStore
from ai_system.core.config import load_settings
from ai_system.core.events import EventLog
from ai_system.core.llm import LocalLLM
from ai_system.core.paths import ensure_runtime_dirs
from ai_system.memory.store import MemoryStore


class AskRequest(BaseModel):
    prompt: str
    mode: str = "planner"


class RememberRequest(BaseModel):
    text: str
    kind: str = "user_note"


class TaskRequest(BaseModel):
    goal: str
    execute_tools: bool = False


def build_agent() -> MasterAgent:
    settings = load_settings()
    return MasterAgent(LocalLLM(settings), MemoryStore(settings))


ensure_runtime_dirs()
settings = load_settings()
app = FastAPI(title="AI_System", version="1.0.0")
web_dir = settings.root / "web"
if web_dir.exists():
    app.mount("/static", StaticFiles(directory=str(web_dir)), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(web_dir / "index.html")


@app.get("/api/status")
def status() -> dict[str, object]:
    llm = LocalLLM(settings)
    ok, message = llm.health()
    memory = MemoryStore(settings)
    return {
        "name": "AI_System",
        "version": "1.0.0",
        "ollama_ok": ok,
        "ollama_message": message,
        "models": {
            "planner": settings.planner_model,
            "coder": settings.coder_model,
            "fast": settings.fast_model,
            "installed": llm.list_models(),
        },
        "memory_count": memory.count(),
        "memory_dir": str(settings.memory_dir),
        "shell_enabled": settings.allow_shell,
        "browser_enabled": settings.allow_browser_control,
        "desktop_enabled": settings.allow_desktop_control,
    }


@app.post("/api/ask")
def ask(request: AskRequest) -> dict[str, str]:
    answer = build_agent().ask(request.prompt, mode=request.mode)
    return {"answer": answer}


@app.post("/api/task")
def task(request: TaskRequest) -> dict[str, object]:
    run = build_agent().run_task(request.goal, execute_tools=request.execute_tools)
    return {"task": run}


@app.post("/api/memory")
def remember(request: RememberRequest) -> dict[str, str]:
    memory = MemoryStore(settings)
    return {"id": memory.remember(request.text, kind=request.kind)}


@app.get("/api/memory/search")
def recall(q: str, limit: int = 5) -> dict[str, object]:
    memory = MemoryStore(settings)
    return {"items": memory.recall(q, limit=limit)}


@app.get("/api/tasks")
def tasks(limit: int = 10) -> dict[str, object]:
    return {"tasks": TaskStore().latest(limit=limit)}


@app.get("/api/events")
def events(limit: int = 50) -> dict[str, object]:
    return {"events": EventLog().tail(limit=limit)}


@app.get("/api/files/readme")
def readme() -> dict[str, str]:
    path = settings.root / "README.md"
    return {"content": path.read_text(encoding="utf-8") if path.exists() else ""}
