# 🎯 REAL USAGE EXAMPLES — Copy & Paste Ready

## START THE SYSTEM

### Windows
```powershell
cd C:\Users\balu\Projects\projects\kattappa-ai-system
python kattappa_ai_system.py
```

### macOS/Linux
```bash
cd ~/Projects/projects/kattappa-ai-system
python3 kattappa_ai_system.py
```

---

## 📝 EXAMPLE 1: CHATBOT MODE

```
>> what is machine learning
[AI explains in detail]

>> explain deep learning like I'm 5
[AI simplifies]

>> give me tips for productivity
[AI gives useful tips]
```

---

## 👨‍💻 EXAMPLE 2: CODING TASKS

### Create a new Python file
```
>> code: create a python function that checks if a number is prime
```

Creates `workspace/prime.py` with working code + backup

### Fix errors
```
>> code: fix errors in my_script.py and explain what was wrong
```

Reads `workspace/my_script.py` → Fixes it → Backs up original → Explains changes

### Optimize code
```
>> code: optimize this C program for speed and explain the changes
```

### Generate API
```
>> code: create a REST API in Python using Flask with GET and POST endpoints
```

---

## 🌐 EXAMPLE 3: INTERNET SEARCH

### Technical research
```
>> search: best practices for MySQL database optimization 2026
```

### Product research
```
>> search: cheapest cloud hosting for startups
```

### News/Trends
```
>> search: latest developments in quantum computing
```

### Learning
```
>> search: how to learn Rust programming basics
```

---

## 🧠 EXAMPLE 4: MULTI-AGENT SIMULATION

### Business decision
```
>> simulate: should I freelance or work as an employee?
```

**What happens**:
1. Planner → outlines pros/cons of each
2. Builder → develops case for freelancing
3. Reviewer → challenges assumptions
4. Final → synthesizes best answer

### Technical choice
```
>> simulate: React vs Vue.js for my startup in 2026
```

### Career advice
```
>> simulate: learn AI/ML or Web Development first?
```

### Project planning
```
>> simulate: microservices or monolith architecture for my app?
```

---

## 💾 EXAMPLE 5: MEMORY & PERSISTENCE

### Save project context
```
>> remember: Building e-commerce app with React, Node.js, PostgreSQL
>> remember: Client is startup, tight budget, needs MVP in 3 months
>> remember: Database has 1M+ product catalog
```

Later sessions will include this context:
```
>> code: create the product search API
[AI knows: Node.js, PostgreSQL, 1M+ products, startup budget]
```

### Check memory
```
>> memory
```

Output:
```
- 2026-05-11 10:30:45 Building e-commerce app with React, Node.js, PostgreSQL
- 2026-05-11 10:35:12 Client is startup, tight budget, needs MVP in 3 months
- 2026-05-11 10:40:22 Database has 1M+ product catalog
```

---

## 🔍 EXAMPLE 6: SYSTEM DIAGNOSTICS

### Check everything is working
```
>> doctor
```

Output shows:
- ✅ Python version
- ✅ Ollama status
- ✅ Installed models
- ✅ Search capabilities
- ✅ Workspace size
- ✅ Memory notes

### Check current status
```
>> status
```

Output:
```json
{
  "provider": "ollama",
  "active_models": {
    "assistant": "mistral",
    "coder": "mistral",
    "reviewer": "phi3",
    "search_summarizer": "mistral"
  },
  "workspace_files": 5,
  "memory_notes": 3
}
```

### Check configuration
```
>> config
```

Shows what settings are active.

---

## 🚀 EXAMPLE 7: REAL WORKFLOW (BUILDING AN APP)

### Step 1: Plan
```
>> remember: Building a simple weather app
>> search: best free weather API 2026
>> simulate: REST API vs GraphQL for weather data
```

### Step 2: Build
```
>> code: create a Python Flask app that fetches weather from free API
>> code: add error handling to weather API calls
>> code: create an HTML frontend for the weather app
```

### Step 3: Review & Improve
```
>> code: add caching to reduce API calls and improve performance
>> code: optimize the database queries for faster response
```

### Step 4: Document
```
>> code: create a README.md with setup instructions
```

### Step 5: Save for later
```
>> remember: Weather app complete, uses OpenWeatherMap API, stored in workspace/
>> memory
```

---

## 🎓 EXAMPLE 8: LEARNING A NEW SKILL

### Learn Rust
```
>> search: Rust programming language basics 2026
>> code: create hello world in Rust
>> code: create a Rust function that processes a list
>> simulate: Rust vs Go for backend services
>> remember: Rust has great error handling, learning curve steep
```

### Learn React
```
>> search: React 18 best practices 2026
>> code: create a React counter component
>> code: add React hooks to manage state
>> code: optimize React component performance
```

---

## 🔧 EXAMPLE 9: ONE-SHOT COMMANDS (No Loop)

### Just chat
```powershell
python kattappa_ai_system.py --once "explain quantum computing"
```

### Just code
```powershell
python kattappa_ai_system.py --code "create a Python calculator with GUI"
```

### Just search
```powershell
python kattappa_ai_system.py --search "latest AI models 2026"
```

### Multi-agent
```powershell
python kattappa_ai_system.py --simulate "best programming language for beginners"
```

### Save note
```powershell
python kattappa_ai_system.py --remember "Completed React course, next is Node.js"
```

---

## 💡 EXAMPLE 10: ADVANCED COMBINATIONS

### Search + Simulate + Code
```
>> search: latest blockchain frameworks 2026
[Get current info]

>> simulate: Should I use Solidity or Rust for smart contracts?
[Get multi-perspective analysis]

>> code: create a simple Solidity smart contract for token transfer
[Generate actual code]
```

### Memory + Code + Multi-Agent
```
>> remember: Building scalable backend for 1M users
>> code: design database schema for high traffic
>> simulate: PostgreSQL vs MongoDB for this scale
```

---

## 🎯 QUICK REFERENCE

| Goal | Command |
|------|---------|
| Ask a question | `>> your question here` |
| Create file | `>> code: create app.py that does X` |
| Edit file | `>> code: fix errors in app.py` |
| Search web | `>> search: your query` |
| Multi-agent debate | `>> simulate: question here` |
| Save memory | `>> remember: important fact` |
| View memory | `>> memory` |
| List files | `>> files` |
| Check system | `>> doctor` |
| Exit | `>> exit` |

---

## ⚡ PERFORMANCE EXPECTATIONS (Your Laptop)

| Task | Time |
|------|------|
| Simple chat | 5–10 sec |
| Code generation | 10–15 sec |
| Web search | 15–20 sec |
| Multi-agent | 20–30 sec |
| File editing | 5–10 sec |

---

## 🔒 IMPORTANT RULES

✅ Files are ONLY edited in `workspace/`
✅ Old files are backed up automatically
✅ Secrets are scanned before sending to AI
✅ Memory is stored locally
✅ Internet is only used for `search:` command

---

## 🆘 TROUBLESHOOTING

### System won't start
```powershell
python kattappa_ai_system.py --doctor
```

### Ollama not working
```powershell
ollama --version
ollama pull mistral
```

### Forgot commands
```
>> help
```

### Want to reset everything
```powershell
rm config.json
rm memory/notes.json
python kattappa_ai_system.py --setup
```

---

**Your system is ready. Start using it now.**
