# Universal Translator Setup

This project has one setup file and one run executable at the project root.

## Setup

```bat
setup.bat
```

`setup.bat` installs Node dependencies, bootstraps runtime folders, and creates
`.env` from `.env.example` when needed.

## Run

```bat
run.exe
```

`run.exe` starts the Electron desktop app. If dependencies are missing, run
`setup.bat` first.

## Verification

Use package scripts rather than extra root batch files:

```bat
npm test
npm run typecheck
npm run build
```

The workspace-wide production gate is available from the repository root:

```bat
..\bin\CHECK_PRODUCTION_READINESS.bat
```
