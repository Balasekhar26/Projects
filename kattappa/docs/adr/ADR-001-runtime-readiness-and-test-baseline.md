# ADR-001: Runtime Readiness and Reproducible Test Baselines

Status: accepted  
Date: 2026-07-16

## Context

Kattappa has reported several valid but non-equivalent test counts. The 208
count described one historical backend selection. Counts of 3,068 and 3,153
were produced by broader configured collections in different working-tree
states. The 309 count described a bounded engineering selection spanning the
backend, native infrastructure, data engine, and resource governor.

A count alone cannot establish that two runs selected the same tests. Dirty
working-tree changes, marker expressions, configuration, parameterization, and
module resolution can all change collection.

Runtime validation also exposed unsafe operational guidance: a listener must
not be terminated merely because it is a Python process using port 8000.

## Decision

1. Every official test baseline includes the Git commit, dirty status, Python
   and pytest versions, selected paths, sorted node IDs, marker counts, result
   counts, duration, and warnings.
2. Generated manifests are written under `artifacts/test-manifests/` and are
   not committed unless an artifact-retention policy is separately approved.
3. `/ready` is the canonical infrastructure-readiness contract.
   `/api/v1/ready` is an intentional compatibility alias and delegates to the
   same readiness service.
4. Readiness checks package availability only. They do not load Kronos weights
   or enable financial execution.
5. Development-server termination requires recorded PID metadata plus matching
   process start time, command line, working directory, port, and checkout.
6. New crawler, workspace, voice, design, desktop, and finance integrations
   remain frozen until the stabilization acceptance criteria pass.

## Adaptive-runtime evidence

The contradictory adaptive-runtime outcomes were observed across different
source states, not a single reproducible state. The current implementation uses
an `<8 GB` ECO threshold, while the earlier failure was captured with a modified
`<16 GB` threshold before checkout restoration.

The first instrumented audit was invalidated when
`backend/tests/test_adaptive_runtime.py` changed between repetitions six and
seven. Its SHA-256 changed from `3400ae6b...` to `7c9db172...` while the module
path, production hash, 12 node IDs, profile outputs, and selected test outcome
remained unchanged. The edit added deterministic cache reset and future
synchronization logic.

After the edit stopped, ten fresh-process repetitions completed with one
signature: 12 identical node IDs, production hash `e01ea65e...`, test hash
`7c9db172...`, and canonical results `ECO`, `ECO`, and `BALANCED`. The selected
performance-profile test passed in every repetition. The historical five-item
collection cannot be reconstructed without its node IDs and exact source hash;
it is not an authoritative baseline.

## Consequences

- CI and release reports become auditable at node-ID level.
- Readiness remains fast in intent and side-effect free.
- Unknown listeners are never killed automatically.
- Startup performance is measured by wall-clock bind/readiness time rather
  than inferred solely from accumulated import-time output.
- Capability growth pauses while execution and validation evidence stabilizes.
