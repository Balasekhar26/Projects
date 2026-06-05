# PCB Doctor

PCB Doctor is planned as a practical diagnostic assistant for electronics repair.

## MVP Scope

- Manual measurement input first: voltage, resistance, current, symptoms, board area.
- Rule-based diagnosis before AI.
- Guided repair checks that ask the user to measure again after each step.
- Fault history database for repeat patterns.

## First Software Modules

```text
pcb_doctor/
  data.py            Parse board models and measurements
  engine.py          Deterministic diagnostic and backward tracing logic
  models.py          Data contracts for nodes, measurements, findings
data/
  fault-patterns.json
tests/
```

## Tiny GPU Lab

The first HDL learning integration is scaffolded under:

```text
modules/tiny_gpu_lab/
```

Reference project:

```text
C:\Users\balu\Projects\external-projects\tiny-gpu
```

This module discovers the SystemVerilog files, exposes architecture assets, and builds commands for the upstream matrix-add and matrix-multiply simulations. It is for learning, simulation, and HDL debugging, not for accelerating AI models.

## Safety Boundary

The first version should not require live hardware control. It should guide safe manual measurements and assume the user is responsible for proper tools, isolation, and discharge.

## Run The Prototype

```bash
python -m pcb_doctor.cli
python -m pcb_doctor.cli --json
```

## Data Shape

Board models live in `data/sample-board.json`. Measurements live in `data/sample-measurements.json`.

The core loop is:

```text
measure -> compare expected vs observed -> classify fault -> trace upstream -> suggest next measurement
```
