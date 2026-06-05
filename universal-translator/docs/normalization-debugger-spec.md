# Normalization Debugger Specification

## Purpose

The normalization debugger is a read-only inspection surface for GETS decisions.

It exists to answer:

- Why did this event receive this `normalizedTime`?
- Which clock domains were trusted or ignored?
- Was the result driven by confidence collapse, skew, or missing data?
- Did replay preserve the same temporal reasoning?

It must never mutate runtime state, apply tuning, or alter arbitration.

## Non-Goals

The normalization debugger is not:

- an auto-tuner
- a config editor
- a runtime optimizer
- a hidden control plane for observer logic

It may explain time. It may not change time.

## Primary Users

1. Engineers debugging temporal incoherence
2. Operators validating observer trust during live sessions
3. Replay investigators diagnosing divergence

## Core Views

### 1. Event List

Shows normalized events in causal order.

Each row must include:

- `sequence`
- `type`
- `sessionId`
- `lineageId`
- `causalityKey`
- `normalizedTime`
- `normalizationMode`
- `coherenceScore`
- warning badge if confidence or coherence is low

Default sort:

```txt
(normalizedTime, sequence, id)
```

### 2. Event Detail

Shows one event’s complete temporal explanation.

Required sections:

- raw times
- rebased times
- domain confidences
- mode profile weights
- effective weights
- ignored domains and reasons
- denominator
- final `normalizedTime`
- skew summary

### 3. Timeline Compare

Compares raw vs normalized placement.

Tracks:

- `systemTime`
- `streamTime`
- `utteranceTime`
- `observerTime`
- `quotaTime`
- `normalizedTime`

The debugger should make drift visually obvious, not merely textual.

### 4. Replay Compare

Shows baseline vs replay for the same event or event family.

Required outputs:

- baseline `normalizedTime`
- replay `normalizedTime`
- drift in ms
- causality key match or mismatch
- divergence result
- playback timing tolerance status

### 5. Session Health Summary

Aggregates temporal trust signals for the selected session.

Must include:

- coherence distribution
- ignored-domain counts
- quota-pressure frequency
- top mismatch categories
- replay determinism status

## Canonical Debugger Data Model

The debugger consumes normalized events without requiring a second normalization pass.

```ts
type NormalizationDebuggerRecord = {
  id: string;
  type: string;
  sessionId: string;
  lineageId?: string;
  sequence: number;

  timing: {
    normalizedTime: number;
    normalizationMode: string;
    coherenceScore: number;
    causalityKey: string;
    skew: Record<string, number | undefined>;
    rawTimes: {
      system?: number;
      stream?: number;
      utterance?: number;
      observer?: number;
      quota?: number | { readyAt?: number; delayMs?: number };
    };
    rebasedTimes: {
      system?: number;
      stream?: number;
      utterance?: number;
      observer?: number;
      quota?: number;
    };
    confidences: {
      system: number;
      stream: number;
      utterance: number;
      observer: number;
      quota: number;
    };
    normalizationWeights: {
      system: number;
      stream: number;
      utterance: number;
      observer: number;
      quota: number;
    };
    normalizationTrace: {
      mode: string;
      origins: Record<string, number | null>;
      denominator: number;
      contributingDomains: Array<{
        domain: string;
        rawTime: number;
        rebasedTime: number;
        baseWeight: number;
        confidence: number;
        effectiveWeight: number;
      }>;
      ignoredDomains: Array<{
        domain: string;
        reason: "missing-time" | "zero-effective-weight";
        baseWeight: number;
        confidence: number;
      }>;
    };
  };

  payload: Record<string, unknown>;
};
```

## Derived Debugger Metrics

The UI may compute:

- `dominantDomain`: domain with highest effective weight
- `confidenceCollapse`: true if any required domain confidence `< 0.4`
- `highSkew`: true if any absolute skew `> 120ms`
- `quotaConstrained`: true if quota contributed materially
- `traceCompleteness`: ratio of available domains to expected domains

These are diagnostic labels only.

## Required Runtime Inputs

The debugger depends on:

1. `event.timing.rawTimes`
2. `event.timing.rebasedTimes`
3. `event.timing.confidences`
4. `event.timing.normalizationWeights`
5. `event.timing.normalizationTrace`
6. `event.timing.causalityKey`

If any are missing, the debugger must show the event as `trace-incomplete`.

## Required API Shape

If exposed over HTTP or IPC, the minimum contract should be:

```txt
GET /api/debug/normalization/sessions
GET /api/debug/normalization/sessions/:sessionId/events
GET /api/debug/normalization/sessions/:sessionId/events/:eventId
GET /api/debug/normalization/sessions/:sessionId/replay
```

Suggested response semantics:

- sessions: summary only
- events: paginated normalized event list
- event detail: full trace object
- replay: baseline vs replay comparison view model

## Filtering

The debugger should support filters for:

- event type
- utterance or lineage id
- low coherence only
- quota-influenced only
- ignored-domain only
- replay mismatch only

These filters must be read-only and client-side safe.

## Visual Language

The UI should make temporal reasoning legible at a glance.

Suggested encodings:

- raw clocks: distinct lane colors
- normalized time: high-contrast canonical marker
- ignored domains: faded or struck-through chips
- dominant domain: highlighted badge
- low confidence: amber
- determinism failure: red

Avoid decorative complexity. This is an instrument panel, not a dashboard toy.

## Safety Rules

The debugger must not:

- trigger simulation automatically
- modify config
- acknowledge or dismiss anomalies as system truth
- hide missing data behind inferred values

If data is absent, display absence explicitly.

## Implementation Phases

### Phase 1: Data Visibility

- expose normalized event list
- expose event detail trace
- add low-coherence and ignored-domain flags

### Phase 2: Timeline Visualization

- render multi-lane raw clock view
- overlay normalized time markers
- support event selection and scrub

### Phase 3: Replay Comparison

- show baseline vs replay event alignment
- surface drift and strict mismatch categories
- link mismatches back to source events

### Phase 4: Session Summary

- aggregate coherence and confidence metrics
- show quota pressure and replay verdicts

## Recommended File Boundaries

If implemented in the current repo, keep write scopes separated:

- API shaping: `app/api/debug/...`
- UI state and types: `app/components/ult-dashboard/types.ts`
- debugger panel UI: `app/components/ult-dashboard/...`
- observer serialization helpers: `src/ai-observer/...`

The normalizer and replay harness should remain pure producers of trace data, not UI-aware modules.

## Acceptance Criteria

The debugger is ready when an engineer can:

1. select any event
2. see exactly which domains contributed to `normalizedTime`
3. understand why a domain was ignored
4. compare baseline vs replay for the same event lineage
5. identify whether a mismatch came from confidence collapse, skew, missing timestamps, or replay divergence

## Architectural Rule

The normalization debugger is an observability surface for GETS.

It strengthens trust only if it stays read-only.
