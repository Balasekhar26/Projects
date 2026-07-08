from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel

from ai_system.agents.master import MasterAgent
from ai_system.agents.tasks import TaskStore
from ai_system.core.config import load_settings
from ai_system.core.events import EventLog
from ai_system.core.llm import LocalLLM
from ai_system.core.paths import ensure_runtime_dirs
from ai_system.memory.store import MemoryStore
from ai_system.tools.browser import BrowserTool
from ai_system.vision.screen import ScreenVision
from ai_system.voice.speech import VoiceIO


app = typer.Typer(help="Local-first AI_System command center.")
console = Console()


def build_agent() -> MasterAgent:
    ensure_runtime_dirs()
    settings = load_settings()
    return MasterAgent(llm=LocalLLM(settings), memory=MemoryStore(settings))


@app.command()
def status() -> None:
    """Check local services and configured models."""
    ensure_runtime_dirs()
    settings = load_settings()
    llm = LocalLLM(settings)
    ok, message = llm.health()
    memory = MemoryStore(settings)
    console.print(Panel.fit("AI_System Final", title="Status"))
    console.print(f"Ollama: {'OK' if ok else 'NOT READY'} - {message}")
    console.print(f"Planner model: {settings.planner_model}")
    console.print(f"Coder model: {settings.coder_model}")
    console.print(f"Fast model: {settings.fast_model}")
    console.print(f"Installed Ollama models: {', '.join(llm.list_models()) or 'none detected'}")
    console.print(f"Memory items: {memory.count()}")
    console.print(f"Memory dir: {settings.memory_dir}")


@app.command()
def chat(mode: str = typer.Option("planner", help="planner, coder, or fast")) -> None:
    """Start an interactive local chat with long-term memory."""
    agent = build_agent()
    console.print(Panel("Type /exit to stop, /remember TEXT to store memory.", title="AI_System Chat"))
    while True:
        user_input = console.input("[bold cyan]you> [/]")
        if user_input.strip().lower() in {"/exit", "exit", "quit"}:
            break
        if user_input.startswith("/remember "):
            memory_id = agent.memory.remember(user_input.removeprefix("/remember ").strip(), kind="user_note")
            console.print(f"[green]remembered[/] {memory_id}")
            continue
        answer = agent.ask(user_input, mode=mode)
        console.print(Panel(answer, title="AI_System"))


@app.command()
def ask(prompt: str, mode: str = typer.Option("planner", help="planner, coder, or fast")) -> None:
    """Ask one question and exit."""
    console.print(build_agent().ask(prompt, mode=mode))


@app.command()
def task(
    goal: str,
    execute_tools: bool = typer.Option(False, help="Allow the planner to call safe registered tools."),
) -> None:
    """Plan and run a multi-step local task."""
    run = build_agent().run_task(goal, execute_tools=execute_tools)
    console.print(Panel(run.final_answer or "Task completed.", title=f"Task {run.id}"))
    for step in run.steps:
        console.print(f"[green]{step.status}[/] {step.title}")


@app.command("tasks")
def list_tasks(limit: int = 10) -> None:
    """Show recent task runs."""
    for run in TaskStore().latest(limit=limit):
        console.print(Panel(f"{run.status}\n{run.goal}\n\n{run.final_answer}", title=run.id))


@app.command()
def remember(text: str, kind: str = "user_note") -> None:
    """Store a memory item in ChromaDB."""
    memory_id = MemoryStore(load_settings()).remember(text, kind=kind)
    console.print(f"Stored memory: {memory_id}")


@app.command()
def recall(query: str, limit: int = 5) -> None:
    """Search long-term memory."""
    items = MemoryStore(load_settings()).recall(query, limit=limit)
    for item in items:
        console.print(Panel(item))


@app.command()
def events(limit: int = 30) -> None:
    """Show recent runtime events."""
    for event in EventLog().tail(limit=limit):
        console.print(f"{event.timestamp} [{event.kind}] {event.message}")


@app.command()
def dashboard() -> None:
    """Print the local dashboard launch command."""
    console.print("Run: run.exe ui")
    console.print("Then open: http://127.0.0.1:5173")


@app.command()
def browse(url: str) -> None:
    """Read a webpage through Playwright."""
    console.print(BrowserTool(load_settings()).read_page(url))


@app.command()
def screen_ocr() -> None:
    """Capture the screen and run OCR."""
    console.print(ScreenVision(load_settings()).ocr_latest_screen())


@app.command()
def speak(text: str) -> None:
    """Speak text through the Windows speech engine."""
    VoiceIO().speak(text)


@app.command()
def transcribe(audio_file: Path) -> None:
    """Transcribe an audio file with local faster-whisper."""
    console.print(VoiceIO().transcribe_file(audio_file))


if __name__ == "__main__":
    app()
