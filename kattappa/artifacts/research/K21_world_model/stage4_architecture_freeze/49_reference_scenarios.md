# K21-49: Reference Scenarios Specification

This document defines the concrete, end-to-end scenario sequences used to evaluate the World Model's capabilities.

---

## 1. Scenario 1: Object Permanence under Deletion
- **Goal**: Verify that entity properties are preserved in historical records even when deleted from active state.
- **Steps**:
  1. Register `DigitalEntity` representing `config.json` with canonical ID `digital.filesystem.config_json`.
  2. Emit observation `deleted = True`.
  3. Query `get_entity("digital", "digital.filesystem.config_json")`.
- **Assertion**:
  - The entity must be retrieved.
  - Its property `exists` must be `False` (with $Confidence \ge 0.95$).
  - Its history logs must contain the deletion event.

---

## 2. Scenario 2: Cross-Domain Causal Cascades
- **Goal**: Verify that a digital event triggers appropriate states updates across other domains.
- **Steps**:
  1. Emit observation event `digital.exec.compile_file` on `digital.repo.kattappa`.
  2. Causal Engine catches event, evaluates causal rule `law_cpu_load_spike`.
  3. Causal Engine publishes secondary event `self.hardware.cpu_load_modified` with delta $+45\%$.
- **Assertion**:
  - Querying `self.hardware.cpu` returns `cpu_load` value updated by $+45\%$.
  - The event log registers the chain of custody.
