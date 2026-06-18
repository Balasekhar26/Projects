# Project Setup

Each project in this repository is designed to set up and run independently.
After downloading the repo, open the project folder you want and double-click:

```text
setup.bat
```

`setup.bat` prepares that project and starts it. After the first setup,
double-click:

```text
run.exe
```

`run.exe` also checks whether setup is missing and runs the project setup first
when needed.

## Projects

```text
kattappa/setup.bat
ai-cyber-shield/setup.bat
dews/setup.bat
musical-keyboard/setup.bat
pcb-doctor/setup.bat
universal-translator/setup.bat
07-NeuroSeed/setup.bat
```

## Setup-Only Mode

For installing without launching:

```bat
setup.bat --setup-only
```

## Requirements

- Node.js is required for AI Cyber Shield, DEWS, Musical Keyboard, PCB Doctor,
  and Universal Translator.
- Python 3 is required for Kattappa and NeuroSeed.
- Kattappa also uses Node.js for its desktop UI and optional Tauri build path.

No project setup file should require a sibling project folder to run.
