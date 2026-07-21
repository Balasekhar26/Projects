# K-R0.5 Contaminated Change Inventory & Audit

## Overview
This document records cognitive, planning, council, and simulation architecture changes identified during the K-R0.5 audit. To maintain strict validation isolation, these changes are quarantined from the K-R0.5 release validation baseline and queued for subsequent milestone review (K-SB-1 / K-CAP-1).

## Quarantined Components

| Source File | Original Local Reason | Targeted Test / Feature | Recommended Milestone | Risk of Inclusion in K-R0.5 |
| :--- | :--- | :--- | :--- | :--- |
| `backend/core/cognitive_kernel.py` | Refactored internal dispatch | Cognitive pipeline optimization | K-SB-1 | High (Changes execution graph semantics) |
| `backend/core/cognitive_service.py` | Service wrapper extraction | Modular service architecture | K-SB-1 | High (Unverified service layer) |
| `backend/core/council_session.py` | Council session state handling | Multi-agent debate consensus | K-CAP-1 | High (Modifies consensus thresholds) |
| `backend/core/graph.py` | Graph routing nodes | Node traversal logic | K-SB-1 | High (Affects non-deterministic routing) |
| `backend/core/planner/planner_engine.py` | Multi-step plan routing | Planner step splitting | K-SB-1 | Medium (Interferes with baseline planner tests) |
| `backend/core/simulation_engine.py` | Simulation tick state | K-19 simulation tests | K-SB-1 | Medium (Order-dependent state drift) |

## Audit Verdict
All 6 cognitive components listed above are quarantined from the release validation scope and preserved on backup branch `backup/k-r0.5-contaminated-8490f1d3`.
