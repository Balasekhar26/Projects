# Kattappa AI System

A portable local-first AI workspace for Windows, macOS, and Linux.

It gives you:

- Chatbot mode.
- Local AI through Ollama.
- Optional hosted NVIDIA NIM mode when an API key is present.
- Separate assistant, coder, reviewer, and search-summarizer model roles.
- Multi-agent simulation.
- Internet search through DuckDuckGo-compatible packages.
- A coding agent that can read and edit only `workspace/`.
- Automatic backups before coding-agent overwrites/deletes.
- Workspace secret scanning.
- Context budget estimates before large coding tasks.
- Persistent memory notes stored in `memory/`.
- Diagnostics through `doctor`.

## Recommended Models

For your Lenovo B590 style machine with 12 GB RAM:

```text
mistral
phi3
```

For a stronger Mac or desktop, you can edit `config.json` and use heavier Ollama models later.

## Install Requirements

Install Python 3.10+ and Ollama first:

```text
https://www.python.org/downloads/
https://ollama.com/download
```

Then run setup from this folder:

```powershell
cd C:\Users\balu\Projects\projects\kattappa-ai-system
python kattappa_ai_system.py --setup
```

On macOS/Linux:

```bash
cd /path/to/kattappa-ai-system
python3 kattappa_ai_system.py --setup
```

The setup installs Python search packages and pulls the configured Ollama models.

## Start The App

Windows PowerShell:

```powershell
.\bin\run.ps1
```

Any OS:

```bash
python kattappa_ai_system.py
```

macOS/Linux launcher:

```bash
./bin/run.sh
```

## Commands Inside The App

```text
help                       Show commands
doctor                     Check Python, Ollama, models, search, paths
models                     Show configured models
pull                       Pull configured Ollama models
files                      List workspace files
read: path/to/file         Read a workspace file
budget                     Estimate workspace context size
scan                       Scan workspace for likely secrets
memory                     Show saved memory notes
remember: fact             Save a persistent note
forget memory              Clear saved memory
search: query              Search the internet and answer
code: task                 Let the coding agent edit workspace files
simulate: task             Run planner/builder/reviewer/final agents
exit                       Quit
```

## One-Shot Commands

```bash
python kattappa_ai_system.py --doctor
python kattappa_ai_system.py --budget
python kattappa_ai_system.py --scan
python kattappa_ai_system.py --once "explain embedded systems basics"
python kattappa_ai_system.py --search "latest local AI tools"
python kattappa_ai_system.py --simulate "3 agents deciding a startup idea"
python kattappa_ai_system.py --code "create a C program for LED blinking"
python kattappa_ai_system.py --remember "My laptop has 12 GB RAM."
```

## Coding Workflow

Put files here:

```text
workspace/
```

Examples:

```text
workspace/app.py
workspace/main.c
workspace/index.html
```

Then ask:

```text
code: fix errors in app.py
code: create a calculator in python
code: optimize main.c and explain the changes
```

The coding agent blocks absolute paths and `..` traversal, so it cannot write outside `workspace/`.

Existing files are copied to `backups/` before the coding agent overwrites or deletes them.

Before asking for edits, run:

```text
scan
budget
```

`scan` helps catch likely API keys or passwords before they get sent into model context. `budget` shows roughly how much workspace context the model will receive.

## Internet Search

Use:

```text
search: python websocket example
search: latest electric vehicle trends
```

The system first tries the modern `ddgs` package, then falls back to `duckduckgo-search`, then falls back to the DuckDuckGo instant-answer API.

## NVIDIA NIM Optional Mode

If you set `NVIDIA_NIM_API_KEY`, `llm_provider: "auto"` uses NVIDIA NIM. Without it, the system uses local Ollama.

Windows PowerShell:

```powershell
$env:NVIDIA_NIM_API_KEY="nvapi-..."
```

macOS/Linux:

```bash
export NVIDIA_NIM_API_KEY="nvapi-..."
```

Use `config.json` to force a provider:

```json
{
  "llm_provider": "ollama"
}
```

Valid values are `auto`, `ollama`, and `nvidia`.

## Test

Windows:

```powershell
.\tests_smoke.ps1
```

macOS/Linux:

```bash
./tests_smoke.sh
```

The smoke test checks safety boundaries, config loading, memory, and diagnostics without requiring Ollama or internet.

## Audit Untrusted ZIPs

Use the archive auditor before extracting unknown code:

```powershell
python .\tools\audit_archives.py C:\Users\balu\Projects
```

It reads ZIP metadata only. It does not extract files, run scripts, install packages, or inspect source contents.

The Claude ZIP metadata report from this machine is saved at:

```text
docs/claude-zip-analysis.md
```

## Reality Check

This is a capable local AI workspace, not a magic replacement for a developer. It can make mistakes, so review generated code before trusting it. Keep important projects backed up, and keep risky experiments inside `workspace/`.
