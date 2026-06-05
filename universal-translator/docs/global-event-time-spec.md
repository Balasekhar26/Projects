# Global Event Time System (GETS) Specification

## Purpose

The Global Event Time System defines a single temporal contract for the realtime speech pipeline.

GETS exists to prevent coherence failures where:

- STT timing is locally correct but semantically misaligned
- utterance evolution is semantically correct but operationally late
- observer analysis is statistically correct but perceptually wrong
- replay appears valid but cannot reproduce causal decisions

This document is the authoritative source for event timestamp semantics, normalization rules, and deterministic replay invariants.

## Scope

GETS applies to every event that can influence:

- utterance creation, revision, merge, or completion
- arbitration decisions such as `speak`, `wait`, `morph`, `drop`
- playback lifecycle and latency accounting
- observer anomaly detection and suggestion generation
- offline replay and simulation

GETS does not require every subsystem to share a physical clock. It requires every subsystem to emit timestamps that can be normalized onto one canonical decision axis.

## Design Principles

1. Events are immutable once emitted.
2. Raw timestamps are preserved; normalization never overwrites source time.
3. Decisions must reference canonical normalized time, not ad hoc local clocks.
4. Replay must reconstruct temporal causality, not just event order.
5. Quota and backpressure are temporal inputs, not external accidents.

## Clock Domains

Every GETS event may carry values from up to four clock domains.

### 1. `systemTime`

Wall-clock time from the host runtime.

- Source: `Date.now()` or equivalent monotonic bridge
- Units: milliseconds since Unix epoch
- Use: external observability, persistence ordering, cross-process correlation
- Risk: scheduler jitter, clock drift, non-determinism under replay

### 2. `streamTime`

Position of the event relative to the audio stream being processed.

- Source: audio frame index, PCM offset, or stream cursor
- Units: milliseconds from stream start
- Use: low-level capture/playback alignment
- Risk: device buffer drift, resampling mismatch

### 3. `utteranceTime`

Semantic progression time for an utterance lineage.

- Source: utterance manager / arbitration layer
- Units: milliseconds from utterance lineage start
- Use: revision stability, semantic continuity, starvation detection
- Risk: lineage reset ambiguity, merge/split semantics

### 4. `observerTime`

Time at which the observer ingested the event for analysis.

- Source: event collector / observer pipeline
- Units: milliseconds since observer session start or Unix epoch
- Use: analysis windowing, batching, anomaly aggregation
- Risk: delayed ingestion creating phantom anomalies

### 5. `quotaTime`

Execution-capacity timing imposed by APIs, models, queues, or rate limits.

- Source: rate limiter, queue manager, provider response metadata
- Units: milliseconds until next allowed execution slot, or absolute deadline
- Use: explaining stalls, preserving realism in simulation, replay gating
- Risk: invisible fourth-clock drift if omitted from causal analysis

## Canonical Event Schema

All runtime and replayable events that affect system behavior must conform to this logical schema.

```ts
type GetsEvent = {
  id: string;
  type: string;
  sessionId: string;
  lineageId?: string;
  sequence: number;

  time: {
    systemTime?: number;
    streamTime?: number;
    utteranceTime?: number;
    observerTime?: number;
    quotaTime?: {
      readyAt?: number;
      delayMs?: number;
      budgetRemaining?: number;
      source?: string;
    };

    normalizedTime: number;
    normalizationMode: "capture" | "utterance" | "observer" | "quota-constrained" | "replay";
    normalizationWeights: {
      stream: number;
      utterance: number;
      system: number;
      observer: number;
      quota: number;
    };
    coherenceScore: number;
    causalityKey: string;
  };

  payload: Record<string, unknown>;
}
```

## Required Fields By Event Family

### Capture and STT events

Must include:

- `systemTime`
- `streamTime`
- `observerTime`

Should include:

- `quotaTime` when provider or queue pressure delays emission

### Utterance lifecycle events

Must include:

- `systemTime`
- `utteranceTime`
- `observerTime`
- `lineageId`

Should include:

- `streamTime` if traceable to source audio span

### Arbitration events

Must include:

- `systemTime`
- `utteranceTime`
- `observerTime`
- `normalizedTime`

Arbitration decisions are contractually evaluated on normalized time.

### Playback events

Must include:

- `systemTime`
- `streamTime`
- `observerTime`

Should include:

- `utteranceTime` when playback is tied to a specific utterance lineage

### Observer events

Must include:

- `observerTime`
- source event references or `causalityKey`

Observer-only synthetic events must never invent source timestamps they do not possess.

## Normalized Time

`normalizedTime` is the canonical decision time for cross-subsystem reasoning.

It is not a replacement for raw clocks. It is the only timestamp allowed for:

- anomaly window comparisons across subsystems
- arbitration tie-breaking across heterogeneous event families
- deterministic replay equality checks for causal behavior

### Reference Formula

The default normalization model is a weighted merge:

```txt
normalizedTime =
  wStream * streamTime +
  wUtterance * utteranceTime +
  wSystem * systemTimeRelative +
  wObserver * observerTimeRelative +
  wQuota * quotaConstraintTime
```

Notes:

- `systemTimeRelative` and `observerTimeRelative` must be rebased to the session origin before weighting
- weights must sum to `1.0`
- missing clocks receive weight `0`
- normalization mode determines the weight profile

## Weight Profiles

Weights are adaptive by event family and operating mode.

### `capture`

Use when preserving audio causality is primary.

- `stream`: 0.55
- `utterance`: 0.10
- `system`: 0.20
- `observer`: 0.10
- `quota`: 0.05

### `utterance`

Use when semantic continuity is primary.

- `stream`: 0.20
- `utterance`: 0.45
- `system`: 0.20
- `observer`: 0.10
- `quota`: 0.05

### `observer`

Use when evaluating anomaly windows or batch ingestion lag.

- `stream`: 0.20
- `utterance`: 0.20
- `system`: 0.15
- `observer`: 0.35
- `quota`: 0.10

### `quota-constrained`

Use when rate limits, queue backlog, or provider pacing materially affect behavior.

- `stream`: 0.20
- `utterance`: 0.20
- `system`: 0.15
- `observer`: 0.10
- `quota`: 0.35

### `replay`

Use during deterministic replay after all times are rebased to recording origin.

- `stream`: 0.35
- `utterance`: 0.30
- `system`: 0.15
- `observer`: 0.10
- `quota`: 0.10

## Coherence Rules

GETS defines coherence as temporal agreement across available clocks after rebasing.

`coherenceScore` must be in the range `[0, 1]`.

Suggested interpretation:

- `0.90 - 1.00`: excellent
- `0.75 - 0.89`: acceptable
- `0.60 - 0.74`: warning
- `< 0.60`: unreliable for cross-domain inference

When `coherenceScore < 0.60`:

- the observer may record anomalies
- the suggestion engine must lower confidence
- automated tuning proposals must be marked `unsafe-without-replay`

## Causality Contract

Ordering is defined by the tuple:

```txt
(normalizedTime, sequence, id)
```

Rules:

1. `sequence` is strictly monotonic within a session emitter.
2. If two events share `normalizedTime`, `sequence` breaks ties.
3. If two events share `normalizedTime` and `sequence`, `id` breaks ties deterministically.
4. Observer-derived events must reference a prior causal event via `causalityKey` or source event IDs.

## Replay Contract

Replay must reconstruct the same causal behavior from:

```txt
ReplayInput = {
  eventLog,
  configSnapshot,
  randomSeed,
  normalizationProfile,
  quotaModel
}
```

`Replay(eventLog)` is valid only if it reproduces the following stable outputs:

- same utterance IDs
- same utterance lineage structure
- same utterance version sequence
- same arbitration decisions
- same playback start/stop decisions
- same anomaly types and source references

Minor divergence is allowed only for metadata declared cosmetic.

## Determinism Gate

Replay mode must freeze or replace all stochastic and non-deterministic inputs.

Required controls:

- fixed random seed
- fixed normalization profile
- fixed session origin and rebased time sources
- disabled live audio capture
- disabled wall-clock reads inside replayed logic
- deterministic queue scheduling
- deterministic provider/mock responses
- explicit quota model for backoff, retry, and cooldown behavior

If any of the above are missing, replay output must be marked `non-deterministic`.

## Divergence Policy

### Allowed divergence

- human-readable log formatting
- diagnostic text wording
- performance counters that do not affect decisions
- internal object identity not exposed to decisions

### Forbidden divergence

- utterance IDs or lineage membership
- utterance revision count
- arbitration outcomes
- playback boundary decisions
- anomaly type, severity bucket, or source-event mapping
- normalized ordering of causally relevant events

## Failure Modes GETS Must Expose

The system must explicitly surface:

- clock skew drift
- observer ingestion lag
- stream/utterance desynchronization
- quota-induced stalls
- replay non-determinism
- missing timestamp domains on required event families

These are first-class system conditions, not debug-only concerns.

## Integration Requirements

Before new detectors or adaptive logic are added, the runtime should satisfy:

1. All causally relevant events emit GETS-compatible timestamp data.
2. Arbitration logic consumes normalized time for cross-domain comparisons.
3. Observer analysis windows are expressed in normalized time.
4. Replay can run with the determinism gate enabled.
5. Quota/backpressure events are represented as events, not only logs.

## Validation Scenarios

GETS changes must be validated against at least:

1. Fast speech
2. Emotional speech
3. Noisy speech
4. Quota-constrained execution

Each scenario must confirm:

- stable normalized ordering
- acceptable coherence score distribution
- deterministic replay for the same seed and config

## Implementation Notes

The current codebase already contains:

- `src/ai-observer/event-time-normalizer.js`
- `src/ai-observer/deterministic-replay-harness.js`

Related observability contract:

- `docs/normalization-debugger-spec.md`

Those modules should be treated as prototype implementations. If they conflict with this spec, this spec wins.
