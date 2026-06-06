# Tools

This folder keeps Universal Translator helper scripts only.

Do not store or reference other project trees here. Universal Translator must
install, run, test, and package from this folder without requiring any sibling
project to exist.

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
