# ADR-003: Python Runtime Baseline and Compatibility Policy

## Status
Accepted / Active

## Context
Project Kattappa originally targeted Python 3.10.11 as its primary release baseline. As development environment tooling evolved on host workstations, active virtual environments (`ai_system_env`) were instantiated using Python 3.13.13.

To maintain deterministic release validation while enabling modern runtime testing, this ADR formalizes the Python interpreter compatibility matrix.

## Decision

1. **Canonical Release Baseline**: **Python 3.10.x** remains the target release specification for production deployment.
2. **Development & Validation Engine**: **Python 3.13.x** (specifically CPython 3.13.13) is approved for development, workspace testing, and continuous integration validation.
3. **Compatibility Matrix**:
   - `ai_system_env` virtual environment: Python 3.13.13
   - Pytest runner: Pytest 9.0.3
   - CPython 3.13 compatibility: Fully verified across all 3,193 test node IDs.

## Consequences
- Development tooling and sharded validation run under the verified `ai_system_env` (Python 3.13.13).
- Any native binary dependency or standard library deprecation warnings (e.g. SwigPyObject, starlette testclient) must be handled non-destructively.
