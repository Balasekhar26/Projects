---
name: autonomous-coding
description: Instruction set for autonomous coding, refactoring, and codebase refinement in Kattappa.
---

# Skill: Autonomous Coding

Use this skill when you need to refactor code, write tests, optimize backend performance, or implement new features in Kattappa.

## Guidelines
1. **Preserve Architecture Lock**: Keep all core modules (Consensus, Graph, Identity, Safety, Memory Bus) structured as per `ARCHITECTURE_LOCK_v1.md`.
2. **Deterministic Adaptation**: Prefer configuration-driven changes over ad-hoc code edits. Keep LLM prompts isolated in `model_router.py` or agent configs.
3. **No Placeholders**: Always write production-ready code with complete type annotations, docstrings, and robust exception handling.
4. **Regression Protection**: Run full unit tests (`pytest`) before committing any changes.
