# Tools

This folder keeps ULT-specific helper scripts only. Workspace companion projects live as top-level project folders.

## Companion Project Locations

- `../ai-cyber-shield/` - defensive autonomous security agent prototype.
- `../universal-ai/` - local multi-agent AI assistant prototype.
- `../pcb-doctor/` - board diagnostics project.
- `../musical-keyboard/` - instrument keyboard project.

## What Is Tracked

Tracked files are source code, scripts, documentation, policy/config files, test scripts, and placeholder `.gitkeep` files needed to preserve runtime folder structure.

## What Is Not Tracked

Generated runtime output stays out of the repository:

- downloaded Ollama app/model caches
- local install flags
- logs
- memory caches
- incident reports generated during runs
- quarantine and evidence output

Those files are machine-specific and can become very large or sensitive.
