# Double-Click Launch Guide

Now you can run any project by simply **double-clicking** the batch files!

## Individual Project Launchers

### 🚀 Double-Click These Files to Run Projects:

1. **ULT Translator Web UI**
   - File: `projects/universal-translator/web-ui/RUN_ULT_TRANSLATOR.bat`
   - Double-click to start the translation interface

2. **Balu Cyber Shield Dashboard**
   - File: `projects/balu-cyber-shield/web-dashboard/RUN_CYBER_SHIELD.bat`
   - Double-click to start the security dashboard

3. **Kattappa AI System Assistant**
   - File: `projects/kattappa-ai-system/ai-assistant/RUN_AI_SYSTEM.bat`
   - Double-click to start the AI assistant with multi-agent coordination

4. **PCB Doctor Diagnostic System**
   - File: `projects/future/pcb-doctor/pcb-diagnostic/RUN_PCB_DOCTOR.bat`
   - Double-click to start the PCB diagnostic tools

5. **DEWS Safe-Domain Simulation**
   - File: `projects/future/dews-safe-sim/safety-simulation/RUN_DEWS_SIMULATION.bat`
   - Double-click to start the safety simulation system

### 🎯 Launch All Projects at Once:

**Master Launcher:**
- File: `RUN_ALL_PROJECTS.bat` (in main Projects folder)
- Double-click to launch ALL 5 projects simultaneously

## What Each Batch File Does Automatically:

✅ **Checks Node.js installation**
✅ **Installs all dependencies** (`npm install`)
✅ **Starts the development server** (`npm run dev`)
✅ **Opens in your default browser**
✅ **Shows colored terminal output**

## Features:

- **Auto-install**: First run installs dependencies automatically
- **Error checking**: Validates Node.js installation
- **Color-coded**: Each project has unique terminal colors
- **Browser auto-open**: Applications open automatically in browser
- **Port management**: Each project uses different ports (5173-5177)

## Quick Start:

1. **Single Project**: Double-click any `RUN_*.bat` file
2. **All Projects**: Double-click `RUN_ALL_PROJECTS.bat`
3. **Stop**: Press `Ctrl+C` in the terminal window

## Terminal Colors:

- 🟢 **Green**: ULT Translator
- 🔴 **Red**: Balu Cyber Shield
- 🔵 **Blue**: Kattappa AI System
- 🟡 **Yellow**: PCB Doctor
- 🟣 **Purple**: DEWS Simulation

## Important Notes:

- **First run**: May take longer due to dependency installation
- **Node.js required**: Batch files will alert you if Node.js is missing
- **Independent**: Each project runs completely separately
- **No conflicts**: Projects use different ports to avoid conflicts

That's it! Just double-click and run! 🎉
