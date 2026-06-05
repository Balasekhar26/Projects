# Claude ZIP Analysis

Date: 2026-05-09

This report records metadata-only analysis of the Claude-related ZIP files found in:

```text
C:\Users\balu\Projects
```

The archives were not extracted or executed. Source contents were not copied into this project.

## Archives Found

| File | Size | SHA-256 | Files | Notes |
| --- | ---: | --- | ---: | --- |
| `claude-code-main.zip` | 9,882,861 | `02e59573032043cb5983d871c1cdb0e1747d02f6cc080f8f8b8dc250521dd346` | 1,903 | TypeScript-heavy snapshot. |
| `claude-code-main (1).zip` | 10,427,252 | `99969ad4e7a8186076c42f4d7c6e23cbbaeed84474cec0c7abf4e3ad73cbb3f7` | 1,906 | Similar shape, different hash and count. |
| `claude-code-main (2).zip` | 11,166,517 | `bb594975761a96752c641b2798aae83150bf5d90acde2bb30748e897b93c32d3` | 2,164 | Larger; includes extra scripts/config/docs. |
| `claude-code-source-code-leak-main.zip` | 9,958,236 | `a9adb3bff3abfa619e31bee477d079ec25300e5bb222c651711daa4eba34c53e` | 1,903 | Duplicate of `(1)` below. |
| `claude-code-source-code-leak-main (1).zip` | 9,958,236 | `a9adb3bff3abfa619e31bee477d079ec25300e5bb222c651711daa4eba34c53e` | 1,903 | Exact duplicate of file above. |

## Extension Shape

Most archives are dominated by:

```text
.ts
.tsx
.js
.md
```

`claude-code-main (2).zip` has the widest project shell:

```text
.json
.sh
.css
.yml
.toml
.lock
```

That does not make it more authentic or safer. It only means the archive contains more project scaffolding.

## Risk Metadata

Metadata matched names related to:

```text
install
setup
bootstrap
token
secret
key
shell scripts
```

These names are not proof of malware by themselves. They are a reason to avoid blind extraction, dependency installation, or script execution.

## Clean-Room Improvements Added

Based on the risk/workflow categories visible from archive metadata, this project now includes independent implementations of:

- ZIP metadata auditing: `tools/audit_archives.py`
- Workspace secret scanning: `scan` and `--scan`
- Context budget reporting: `budget` and `--budget`
- Automatic backups before coding-agent write/delete actions
- Better diagnostics through `doctor`

No leaked source code was used.
