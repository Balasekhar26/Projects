# 🔥 UNIVERSAL AI SYSTEM — FINAL SETUP GUIDE

## ✅ SYSTEM VERIFICATION

Your system **WORKS** and has been tested. It includes:

✔ **Chatbot** — Ask anything, get intelligent local responses
✔ **Coding Agent** — Create, edit, fix code files in `workspace/`
✔ **Multi-Agent System** — Planner + Builder + Reviewer working together
✔ **Multi-Model Intelligence** — Different models for different roles
✔ **Internet Access** — Free web search using DuckDuckGo
✔ **Persistent Memory** — Remembers your notes across sessions
✔ **Safe File Control** — Can only edit inside `workspace/` folder
✔ **Cross-Platform** — Windows, macOS, Linux

---

## 🖥️ YOUR MACHINE SPECS

- **Laptop**: Lenovo B590
- **OS**: Windows 10
- **CPU**: Intel i5 3rd gen
- **RAM**: 12 GB
- **Storage**: 2.5 TB

**Result**: Your system can comfortably run this AI engine. Expected response time: **5–20 seconds per task**.

---

## 📦 ONE-TIME INSTALLATION

### Step 1: Install Ollama (REQUIRED)

This is the **only manual download** needed.

👉 **Download**: [https://ollama.com/download](https://ollama.com/download)

Select **Windows** → Run installer → Follow prompts.

Verify it installed:
```powershell
ollama --version
```

### Step 2: Install Python Dependencies

Open PowerShell in the `universal-ai-system` folder and run:

```powershell
python -m pip install --upgrade pip
python -m pip install duckduckgo-search
```

**Done.** Your system is ready.

---

## 🚀 LAUNCHING THE SYSTEM

### Option 1: Quick Start (Easiest)

Double-click this file:
```
universal-ai-system/RUN_DESKTOP_APP.bat
```

Or from PowerShell:
```powershell
cd C:\Users\balu\Projects\projects\universal-ai-system
python ai_universal_system.py
```

### Option 2: Full Setup + Run

First time only:
```powershell
python ai_universal_system.py --setup
```

Then anytime:
```powershell
python ai_universal_system.py
```

### Option 3: One-Shot Commands (No Interactive Loop)

Ask one question and exit:
```powershell
python ai_universal_system.py --once "explain quantum computing basics"
```

Run one coding task:
```powershell
python ai_universal_system.py --code "create a python calculator"
```

Search the web:
```powershell
python ai_universal_system.py --search "latest AI trends 2026"
```

---

## 💬 HOW TO USE (REAL WORKFLOWS)

### 1️⃣ NORMAL CHAT

```
>> explain python loops
>> what is machine learning
>> how do I learn Rust
```

**Result**: Get clear, local AI answers instantly.

---

### 2️⃣ CODING TASKS

Create a new file:
```
>> code: create a python function that calculates fibonacci numbers
```

Edit existing file:
```
>> code: fix errors in app.py
>> code: optimize main.c for performance
```

The AI will:
- ✅ Create/edit files inside `workspace/`
- ✅ Backup old versions automatically
- ✅ Explain what changed
- ✅ Have a reviewer check the code

---

### 3️⃣ MULTI-AGENT SIMULATION

Let 3 AI minds debate and solve problems:

```
>> simulate: should I start a SaaS business or freelance?
>> simulate: best programming language to learn in 2026
>> simulate: how to optimize my laptop performance
```

**What happens**:
1. Planner → designs the approach
2. Builder → implements the idea
3. Reviewer → finds flaws and suggests fixes
4. Final Agent → synthesizes best answer

---

### 4️⃣ INTERNET SEARCH

Search and get answers grounded in real info:

```
>> search: latest electric vehicle models 2026
>> search: python websocket best practices
>> search: cheapest cloud hosting for startups
```

**How it works**:
- Searches the web using DuckDuckGo (free)
- Fetches top 3–5 results
- AI synthesizes them into one clear answer
- Cites where info came from

---

### 5️⃣ MEMORY & NOTES

Save important facts for future sessions:

```
>> remember: My project uses React 18 and needs PostgreSQL support
>> remember: Client prefers AWS over GCP
```

Check saved memory:
```
>> memory
```

Clear memory:
```
>> forget memory
```

---

### 6️⃣ DIAGNOSTICS

Check system health:
```
>> doctor
```

Shows:
- Python version ✓
- Ollama status ✓
- Installed models ✓
- Internet search package ✓
- Workspace files ✓

Get current config:
```
>> config
```

Get system status:
```
>> status
```

---

## 📂 FOLDER STRUCTURE

```
universal-ai-system/
├── ai_universal_system.py       ← Main program (DO NOT EDIT)
├── config.json                  ← Settings (safe to edit)
├── workspace/                   ← PUT YOUR FILES HERE
│   ├── app.py                   ← AI can read/edit
│   ├── main.c                   ← AI can read/edit
│   └── notes.txt
├── memory/                      ← Persistent notes
├── backups/                     ← Auto-backups (safe)
├── logs/                        ← Event logs
└── tests_smoke.py              ← Validation script
```

---

## 🎯 TYPICAL WORKFLOW

### Day 1: Setup
```powershell
python ai_universal_system.py --setup
```

### Day 2: Use It
```powershell
python ai_universal_system.py
```

```
>> explain my project architecture
>> code: create a REST API in Python
>> search: best practices for authentication
>> simulate: API security vs performance tradeoff
>> remember: API needs CORS support
>> exit
```

---

## ⚡ PERFORMANCE TIPS (YOUR LAPTOP)

✅ **Good Practices**:
- Ask focused questions (not vague)
- Use workspace for code (not outside)
- Save memory notes for important facts
- Restart if system feels slow

❌ **Avoid**:
- Asking 10 questions at once
- Editing huge files (>300KB)
- Running web search every 5 seconds
- Multiple simultaneous agents (stick to 2–3 max)

**Expected Speeds**:
- Simple chat: 5–10 seconds
- Code generation: 10–15 seconds
- Multi-agent simulation: 20–30 seconds
- Web search: 15–25 seconds

---

## 🔒 SAFETY GUARANTEES

Your system **CANNOT**:
- ❌ Access files outside `workspace/`
- ❌ Delete files without backup
- ❌ Access internet except through search
- ❌ Install random packages
- ❌ Run malicious code
- ❌ Store your passwords

Your system **CAN**:
- ✅ Read/write inside `workspace/`
- ✅ Search public web info
- ✅ Remember facts you tell it
- ✅ Simulate multi-agent scenarios
- ✅ Scan for secrets (helps you)

---

## 🛠️ ADVANCED OPTIONS

### Override the Model Provider

Force use of Ollama (ignore NVIDIA):
```powershell
python ai_universal_system.py --provider ollama
```

### Debug Mode

See all API requests:
```powershell
python ai_universal_system.py --debug
```

### Customize Models

Edit `config.json`:

```json
{
  "models": {
    "assistant": "mistral",
    "coder": "mistral",
    "reviewer": "phi3",
    "search_summarizer": "mistral"
  }
}
```

Pull new models:
```powershell
ollama pull llama2
ollama pull neural-chat
```

Then update `config.json` and restart.

---

## 📊 WHAT EACH MODEL DOES (YOUR SETUP)

| Model | Role | What It's Good At |
|-------|------|------------------|
| **Mistral** | Assistant + Coder | General chat, code generation, logic |
| **Phi3** | Reviewer | Careful analysis, finding flaws |

**Why this combo**:
- Mistral: Creative, fast, good for generating ideas
- Phi3: Analytical, catches bugs, questions assumptions

---

## ❓ COMMON QUESTIONS

### Q: Do I need internet?
**A**: Yes, but only for:
- Web search (optional)
- First-time model download via Ollama
- Using `search:` command

Everything else is local.

### Q: Can I use ChatGPT instead?
**A**: Yes, edit `config.json` to add OpenAI:
```json
{
  "llm_provider": "openai",
  "openai_api_key": "sk-..."
}
```

### Q: How do I update models?
**A**:
```powershell
ollama pull mistral
ollama pull phi3
```

### Q: Can I backup my work?
**A**: Yes! All your code backups are in `backups/` folder.

---

## 🔥 FINAL COMMANDS CHEAT SHEET

| Command | What It Does |
|---------|------------|
| `help` | Show all commands |
| `exit` | Quit the system |
| `doctor` | Check system health |
| `config` | Show settings |
| `status` | Show current state |
| `models` | List active models |
| `files` | Show workspace files |
| `read: path.py` | Read a file |
| `budget` | Check context size |
| `scan` | Find secrets in workspace |
| `memory` | Show saved notes |
| `remember: fact` | Save a note |
| `forget memory` | Clear all notes |
| `search: query` | Search web + answer |
| `code: task` | Create/edit files |
| `simulate: task` | 3-agent debate |
| *anything else* | Normal chat |

---

## 🎓 EXAMPLE SESSION

```
>> status
{
  "provider": "ollama",
  "active_models": {
    "assistant": "mistral",
    "coder": "mistral",
    "reviewer": "phi3",
    "search_summarizer": "mistral"
  },
  "workspace_files": 0,
  "memory_notes": 0
}

>> search: rust programming language 2026
[AI searches web, returns latest info about Rust]

>> code: create a rust hello world program
[AI creates workspace/hello.rs with code + backup]

>> simulate: should I learn Rust or Go?
[Planner → Builder → Reviewer → Final answer]

>> remember: Rust is memory-safe and has great tooling
Memory saved.

>> files
hello.rs

>> exit
```

---

## 🚨 IF SOMETHING BREAKS

**Problem**: System won't start
```powershell
python ai_universal_system.py --doctor
```

**Problem**: Ollama not found
```powershell
ollama --version
```
If fails, reinstall from https://ollama.com

**Problem**: Models not downloading
```powershell
ollama pull mistral
ollama pull phi3
```

**Problem**: Old config corrupted
```powershell
rm config.json
python ai_universal_system.py --setup
```

---

## ✨ YOU NOW HAVE

✔ A local AI that thinks
✔ A coding agent that edits your files
✔ 3 minds debating problems
✔ Free internet access
✔ Safe, sandboxed workspace
✔ Persistent memory
✔ Works on your Lenovo B590

**This is not a toy.**

It's a thinking engine that runs on your machine.

Use it. Improve your code. Solve real problems.

---

**Date**: May 11, 2026
**System**: Universal AI v1.0
**Status**: ✅ Production Ready
