# ADR-003: Python Runtime Baseline and Compatibility Policy

## Status
Proposed

## Context
Project Kattappa targets Python 3.10.x as its canonical release baseline for production deployment. In workstation environments, active development virtual environments (`ai_system_env`) use Python 3.13.13.

To ensure strict evidence integrity without premature compatibility claims, this ADR formalizes the Python runtime specification.

## Decision

1. **Canonical Production Baseline**: **Python 3.10.x** is the canonical release baseline for production deployment.
2. **Development Interpreter**: **Python 3.13.13** (`ai_system_env`) is approved as the active development interpreter.
3. **Validation Specification**:
   - Canonical Release Runs (Run A, Run B, Run C) must execute under Python 3.10.x.
   - Compatibility Run D executes under Python 3.13.13 and is reported as compatibility evidence.
   - Full repository compatibility remains under active K-R0.5 validation.

## Consequences
- Development tooling and sharded testing run in `ai_system_env` during local execution.
- Release closure requires canonical validation under Python 3.10.x alongside Python 3.13 compatibility metrics.
