# Projects Workspace

This workspace contains seven canonical projects plus this `bin` holding/tooling folder.
Each project is intended to run independently from its own folder.

| Project | Folder | Main launch | Verification |
| --- | --- | --- | --- |
| Universal AI / Sekhar AI OS | `universal-ai` | `setup.bat`, `run.exe` | core compile and app checks |
| PCB Doctor | `pcb-doctor` | `setup.bat`, `run.exe` | unittest and dashboard build |
| AI Cyber Shield | `ai-cyber-shield` | `setup.bat`, `run.exe` | unittest and dashboard build |
| Universal Translator | `universal-translator` | `setup.bat`, `run.exe` | tests and typecheck |
| Musical Keyboard | `musical-keyboard` | `setup.bat`, `run.exe` | typecheck and web build |
| DEWS | `dews` | `setup.bat`, `run.exe` | unittest and dashboard build |
| NeuroSeed | `07-NeuroSeed` | `setup.bat`, `run.exe` | local static prototype check |

## Master Architecture Rule

These are seven standalone products, not one forced ecosystem.

- No project should import executable code from another project.
- No project should require Universal AI or a shared backend to run.
- Each project owns its own config, data, logs, build, test, and installer path.
- Integrations must be optional connectors, exported reports, local events, or launch shortcuts.
- Paid cloud providers are not part of the default architecture. Use free/local/open-source/free-to-use components only.

The workspace standards live in `project-standard/`.

## Quick Check

Run `CHECK_PRODUCTION_READINESS.bat` from this folder to verify the seven projects in one pass.

## Organization Notes

- `universal-ai` is the merged Universal AI + Sekhar AI OS project.
- The older Universal AI app is preserved in `universal-ai/classic-universal-ai-system`.
- `musical-keyboard` is the canonical web/PWA keyboard. The older Flutter variant is preserved in `musical-keyboard/flutter-version`.
- `bin` is reserved for reviewed leftovers, workspace checks, and support files only. Do not delete from it without checking each file against the seven projects first.
