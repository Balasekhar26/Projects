# DEWS Safe Simulation

This folder is reserved for a safe-domain energy/environment awareness and protection simulator.

## Original Motive

DEWS began as a "Weapon Destroyer" / directed-energy weapon-system concept. The original idea was to combine AI cameras, thermal sensing, and other sensors to detect weapons or ammunition at a distance, then use a remote energy or metal-heating mechanism to disable the threat.

That original motive is recorded here for project history only. This repository is not a weapon project and must not provide targeting logic, emitter-control logic, range optimization, ammunition-disabling procedures, or hardware instructions for damaging weapons, ammunition, people, devices, or infrastructure.

## Safe Build Direction

The buildable direction is a Defensive Early Warning System: detect hazards, correlate camera/thermal/sensor evidence, alert humans, preserve evidence, run simulations, and recommend protective action.

## Allowed Scope

- sensor data ingestion
- anomaly detection
- energy/noise/interference simulation
- safety alerts
- shutdown or shielding recommendations

## Out Of Scope

- weaponization
- targeting people, devices, or infrastructure
- instructions for causing interference, damage, or disruption

## First Software Modules

```text
dews_safe_sim/
  data.py            Load safe sample readings
  engine.py          Detect unsafe readings and recommend protective action
  models.py          Data contracts
data/
  sample-readings.json
tests/
```

## MVP Goal

Run a deterministic simulation from sample readings and produce a safety report.

## External Sensor Modules

The first external integrations are scaffolded under:

```text
modules/wifi_sensing/     Adapter for CSI-Sense-Zero Wi-Fi CSI predictions
modules/animal_audio/     Adapter for animal/environment sound detections
```

Reference downloads:

```text
C:\Users\balu\Projects\external-projects\CSI-Sense-Zero
C:\Users\balu\Projects\external-projects\BirdNET-Analyzer
```

These modules only convert detections into safe DEWS findings: log, correlate, alert, preserve evidence, and request human review.

## Run The Prototype

```bash
python -m dews_safe_sim.cli
```

This prototype only detects unsafe readings and recommends protective actions.

For the Windows app flow:

```bat
setup.bat
run.exe
```

For macOS/Linux/Windows development app flow:

```bash
npm run setup
npm run app
```

Native packaging commands:

```bash
npm run build:windows
npm run build:mac
npm run build:linux
```

## Production Gate

- Keep `setup.bat` as the only setup entrypoint and `run.exe` as the only root run executable.
- Keep implementation in the safe simulation and early-warning domain.
- Do not add targeting, engagement, weapon-disabling, or directed-energy control logic.
- Generated dashboards, logs, runtime data, databases, and dependency folders must stay untracked.
