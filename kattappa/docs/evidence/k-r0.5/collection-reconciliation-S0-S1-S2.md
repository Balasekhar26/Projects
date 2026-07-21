# K-R0.5 Three-Snapshot Collection Reconciliation & Audit

## 1. Snapshot Evidence Audit

### Snapshot S0 (Original K-R0.5.1 Candidate)
- **Artifact Commit**: `d315ec1daece26a9389ad6fdcdedfcc02ade730f`
- **Environment Commit**: `unknown`
- **Status**: `VALID`
- **Collector Blob SHA**: ``
- **Pytest Ini Blob SHA**: ``
- **Total Count**: `3187`
- **Prefix Counts**:
  - `backend/tests`: 3102
  - `kattappa_native/tests`: 11
  - `kattappa_data_engine/tests`: 21
  - `kattappa_runtime/resource_governor`: 53

### Snapshot S1 (Attempt A2 Candidate)
- **Artifact Commit**: `478b27148f5020f300f31ee9cd4a101032633cd7`
- **Environment Commit**: `unknown`
- **Status**: `VALID` (Stale because the runner changes in `478b27148` were committed without executing the updated collector, leaving the K-R0.5.1 collection artifact unchanged)
- **Collector Blob SHA**: ``
- **Pytest Ini Blob SHA**: ``
- **Total Count**: `3187`
- **Prefix Counts**:
  - `backend/tests`: 3102
  - `kattappa_native/tests`: 11
  - `kattappa_data_engine/tests`: 21
  - `kattappa_runtime/resource_governor`: 53

### Snapshot S2 (Current Candidate)
- **Artifact Commit**: `1ee6bdb25ba0475a2122afdacec0497f29272b06`
- **Environment Commit**: `b4b33f0e009d12117019e45336f9cb9839a2520d`
- **Status**: `STALE_COLLECTION_ARTIFACT`
- **Collector Blob SHA**: ``
- **Pytest Ini Blob SHA**: ``
- **Total Count**: `3200`
- **Prefix Counts**:
  - `backend/tests`: 3115
  - `kattappa_native/tests`: 11
  - `kattappa_data_engine/tests`: 21
  - `kattappa_runtime/resource_governor`: 53

---

## 2. Transition Set Differences

### S0 -> S1 (Transition S0_to_S1)
- **Added (0)**:

- **Removed (0)**:

### S1 -> S2 (Transition S1_to_S2)
- **Added (15)**:
  - `backend/tests/test_rbil.py::test_archetype_engine_general`
  - `backend/tests/test_rbil.py::test_archetype_engine_profile`
  - `backend/tests/test_rbil.py::test_escalation_classification`
  - `backend/tests/test_rbil.py::test_intent_calculator`
  - `backend/tests/test_rbil.py::test_intent_faqs_and_projects`
  - `backend/tests/test_rbil.py::test_intent_greeting_and_farewell`
  - `backend/tests/test_rbil.py::test_intent_time_and_date`
  - `backend/tests/test_rbil.py::test_intent_unit_conversion`
  - `backend/tests/test_rbil.py::test_metrics_tracker`
  - `backend/tests/test_sharded_validation.py::test_aggregator_writes_only_test_verdict_json`
  - `backend/tests/test_sharded_validation.py::test_canonical_testpaths_loader`
  - `backend/tests/test_sharded_validation.py::test_policy_hash_changes_with_content`
  - `backend/tests/test_sharded_validation.py::test_policy_yaml_controls_classification`
  - `backend/tests/test_sharded_validation.py::test_scope_policy_allowlist_matching`
  - `backend/tests/test_sharded_validation.py::test_unknown_test_defaults_to_isolated_stateful`

- **Removed (2)**:
  - `backend/tests/test_sharded_validation.py::test_inventory_node_classification`
  - `backend/tests/test_sharded_validation.py::test_policy_hash_computation`

### S0 -> S2 (Transition S0_to_S2)
- **Added (15)**:
  - `backend/tests/test_rbil.py::test_archetype_engine_general`
  - `backend/tests/test_rbil.py::test_archetype_engine_profile`
  - `backend/tests/test_rbil.py::test_escalation_classification`
  - `backend/tests/test_rbil.py::test_intent_calculator`
  - `backend/tests/test_rbil.py::test_intent_faqs_and_projects`
  - `backend/tests/test_rbil.py::test_intent_greeting_and_farewell`
  - `backend/tests/test_rbil.py::test_intent_time_and_date`
  - `backend/tests/test_rbil.py::test_intent_unit_conversion`
  - `backend/tests/test_rbil.py::test_metrics_tracker`
  - `backend/tests/test_sharded_validation.py::test_aggregator_writes_only_test_verdict_json`
  - `backend/tests/test_sharded_validation.py::test_canonical_testpaths_loader`
  - `backend/tests/test_sharded_validation.py::test_policy_hash_changes_with_content`
  - `backend/tests/test_sharded_validation.py::test_policy_yaml_controls_classification`
  - `backend/tests/test_sharded_validation.py::test_scope_policy_allowlist_matching`
  - `backend/tests/test_sharded_validation.py::test_unknown_test_defaults_to_isolated_stateful`

- **Removed (2)**:
  - `backend/tests/test_sharded_validation.py::test_inventory_node_classification`
  - `backend/tests/test_sharded_validation.py::test_policy_hash_computation`
