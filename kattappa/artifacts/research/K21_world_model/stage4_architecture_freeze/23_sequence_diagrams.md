# K21-23: Sequence Diagrams Specification

This document contains sequence diagrams mapping component interactions across key pipelines.

---

## 1. Observation Pipeline

```mermaid
sequenceDiagram
    participant Tool as Tool Executor
    participant Kernel as Cognitive Kernel
    participant Coord as WorldModelCoordinator
    participant Belief as BeliefEngine
    participant Consolidator as MemoryConsolidator

    Tool ->> Kernel: publish_observation(domain, data)
    Kernel ->> Coord: route_observation(domain, data)
    Coord ->> Belief: update_belief(entity_id, data)
    Belief ->> Belief: calculate_bayesian_probability()
    Belief ->> Consolidator: buffer_observation(entity_id, significance)
```

---

## 2. Simulation & Branch Merge Pipeline

```mermaid
sequenceDiagram
    participant Planner as Executive Planner
    participant Coord as WorldModelCoordinator
    participant Sim as SimulationEngine
    participant Causal as CausalEngine

    Planner ->> Coord: create_branch(parent_id)
    Coord -->> Planner: return branch_id
    Planner ->> Coord: simulate_step(branch_id, action)
    Coord ->> Sim: evaluate_step(branch_id, action)
    Sim ->> Causal: match_causal_laws(action)
    Causal -->> Sim: transition_deltas
    Sim -->> Planner: TransitionResult (with uncertainty)
    
    Planner ->> Coord: merge_branch(branch_id)
    Coord ->> Coord: validate_candidate_events(branch_id)
    Coord ->> Kernel: publish_candidate_events(events)
```
