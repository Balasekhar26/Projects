# Clock Abstraction & Deterministic Replay

## Problem Statement

Your system exhibits **run-to-run nondeterminism** in `sessionHash` even with identical input:

```
Run 1: sessionHash = "abc123..."
Run 2: sessionHash = "def456..."
Same conversation. Different hashes.
```

Root causes:
1. **Session time origin drift** — `start` timing varies slightly between runs
2. **Async arrival order** — STT, translation, audio chunks don't arrive in guaranteed order
3. **Floating-point instability** — Timing-dependent calculations can flip outcomes
4. **Compaction timing** — Decisions depend on what's been seen vs what arrives next

## The Solution: Two Modes of Reality

### Live Mode 🟢

```typescript
const session = new UniversalLiveSession(request);
// Uses real clocks:
// - process.hrtime.bigint() for microsecond precision
// - Date.now() for wall-clock time
// - Real async events in real order
```

**Purpose:** Observe the system in the wild. Nondeterminism is expected and documented.

### Deterministic Mode 🔵

```typescript
const replayManager = new ReplayManager();
// [Record live session timestamps during Run 1]
const clock = replayManager.createReplayClock();

const replaySession = new UniversalLiveSession(request, { clock });
// Uses pre-recorded timestamps
// Same order, same times → same outcomes
```

**Purpose:** Prove the logic is stable independent of timing noise.

---

## Architecture

### ClockSource Interface

All timing calls flow through a single abstraction:

```ts
interface ClockSource {
  getHighResTimeMs(): number      // Monotonic elapsed time (microsecond precision)
  getNow(): number                 // Wall-clock time (milliseconds since epoch)
  enforceMonotonic(newTime): number // Guarantee time never goes backward
}
```

### LiveClockSource

Real system timers:

```typescript
const clock = new LiveClockSource();

clock.getHighResTimeMs() // process.hrtime.bigint() → elapsed ms
clock.getNow()           // Date.now() → wall-clock ms
```

### DeterministicClockSource

Pre-recorded timestamps (for replay):

```typescript
const clock = new DeterministicClockSource({
  timestamps: [1700000000000, 1700000001234, ...],
  highResTimestamps: [0, 123.456, 456.789, ...],
});

clock.getHighResTimeMs() // Returns next prerecorded elapsed ms
clock.getNow()           // Returns next prerecorded wall-clock ms
```

---

## Usage: Live → Deterministic Workflow

### Step 1: Record Live Session

```typescript
const session = new UniversalLiveSession(request);
const replayManager = new ReplayManager();

// Hook event recording to capture timestamps
session.on("event", (event) => {
  replayManager.recordTimestamps(session);
});

await session.start();
// ... run your session ...
await session.stop();

// Get stats about recorded timeline
const stats = replayManager.getStatistics();
console.log(`Recorded ${stats.eventCount} events over ${stats.totalElapsed}ms`);

// Save for offline replay
await replayManager.saveTimestampRecording("./session-timestamps.json");
```

### Step 2: Replay with Deterministic Clock

```typescript
// Option A: From recorded manager
const replayClock = replayManager.createReplayClock();

// Option B: From saved file
const replayManager2 = await ReplayManager.fromSavedRecording(
  "./session-timestamps.json"
);
const replayClock = replayManager2.createReplayClock();

// Create session with deterministic clock
const replaySession = new UniversalLiveSession(request, {
  clock: replayClock,
});

await replaySession.start();
// ... run exact same input ...
await replaySession.stop();
```

### Step 3: Compare

```typescript
const liveDump = session.getDebugSessionDump({ mode: "full" });
const replayDump = replaySession.getDebugSessionDump({ mode: "full" });

// Compare hashes
let matches = 0;
for (let i = 0; i < liveDump.events.length; i++) {
  if (liveDump.events[i].integrityHash === replayDump.events[i].integrityHash) {
    matches++;
  }
}

if (matches === liveDump.events.length) {
  console.log("✅ STABLE: Logic produces identical outcomes with recorded timing");
} else {
  console.log("⚠️ UNSTABLE: Logic varies even with identical timing");
}
```

---

## Session Data Capture

### Arrival Order

Each debug event now includes `arrivalIndex`:

```typescript
{
  id: "session-debug-42",
  sequence: 3,
  arrivalIndex: 3,        // ← Raw insertion order
  rawTime: 1700000000123,
  sessionTime: 123.456,
  normalizedTime: 120.5,
  // ...
}
```

This enables **stable sorting** during replay:

```typescript
records.sort((a, b) => {
  if (a.sessionTime !== b.sessionTime) return a.sessionTime - b.sessionTime;
  return a.arrivalIndex - b.arrivalIndex;  // Tiebreaker
});
```

### Session Dumps

Get a complete dump at any time:

```typescript
// Full dump with all events
const dump = session.getDebugSessionDump({ mode: "full", limit: 100 });

// Dump structure:
{
  sessionId: "550e8400-e29b-41d4-a716-446655440000",
  createdAt: "2025-04-16T12:34:56.000Z",
  mode: "full",
  recordCount: 47,
  events: [
    {
      id: "...",
      type: "status",
      arrivalIndex: 0,
      rawTime: 1700000000000,
      sessionTime: 0.123,
      dominantDomain: "utterance",
      contributions: { utterance: 50.5, ... },
      flags: ["TIME_REGRESSION"],
      integrityHash: "abc123def456...",
    },
    // ... more events
  ]
}
```

### Persistence

Save dumps to disk automatically:

```typescript
// Persist to filesystem
const result = await session.persistDebugSessionDump("./debug-dumps");

// Returns:
{
  filepath: "./debug-dumps/550e8400-e29b-41d4-a716-446655440000_full_1700000000000.json",
  filename: "550e8400...json",
  size: 245682,
  events: 47,
}
```

---

## API Endpoints (Session Store)

```typescript
import {
  getSessionDebugEvents,
  getSessionDebugDump,
  persistSessionDebugDump,
} from "./session-store";

// Get specific mode events
const events = getSessionDebugEvents(sessionId, "full", 50);

// Get complete dump
const dump = getSessionDebugDump(sessionId, { mode: "compact", limit: 20 });

// Save to disk
const result = await persistSessionDebugDump(sessionId, "./dumps");
```

---

## Practical Workflow

### Scenario 1: Live Session with Automatic Dump

```typescript
const session = await createSession(request);
const manager = new ReplayManager();

// Auto-record timestamps
session.on("event", () => manager.recordTimestamps(session));

// ... user does something ...

await session.stop();

// Auto-save both
const timestamps = await manager.saveTimestampRecording(
  `./sessions/${session.id}/timestamps.json`
);
const dump = await session.persistDebugSessionDump(
  `./sessions/${session.id}/dumps`
);

console.log(`Session ${session.id}:`);
console.log(`  - Timestamps: ${timestamps.eventCount} events`);
console.log(`  - Dump: ${dump.events} records`);
```

### Scenario 2: Verify Stability (Test Suite)

```typescript
async function testSessionStability(request, inputSequence) {
  // Run 1: Live
  const session1 = new UniversalLiveSession(request);
  const manager1 = new ReplayManager();
  session1.on("event", () => manager1.recordTimestamps(session1));
  await session1.start();
  for (const input of inputSequence) {
    await session1.enqueueChunk(input);
  }
  await session1.stop();

  // Run 2: Deterministic replay
  const clock = manager1.createReplayClock();
  const session2 = new UniversalLiveSession(request, { clock });
  await session2.start();
  for (const input of inputSequence) {
    await session2.enqueueChunk(input);
  }
  await session2.stop();

  // Compare
  const dump1 = session1.getDebugSessionDump({ mode: "full" });
  const dump2 = session2.getDebugSessionDump({ mode: "full" });

  let matches = 0;
  for (let i = 0; i < dump1.events.length; i++) {
    if (dump1.events[i].integrityHash === dump2.events[i].integrityHash) {
      matches++;
    }
  }

  return {
    totalEvents: dump1.events.length,
    matchingHashes: matches,
    stable: matches === dump1.events.length,
  };
}
```

---

## FAQ

### Q: What if deterministic replay still produces different hashes?

Then the problem runs deeper than timing:

1. **Nondeterministic logic** — Code that branches on timestamps or randomness
2. **Floating-point instability** — Math operations with floating decimals
3. **Hidden mutation** — Objects being modified after creation
4. **Hash collision** — Extremely unlikely but check your hash function

Use `getDebugSessionDump()` to inspect the actual event timings, contributions, and flags.

### Q: How much overhead does the clock abstraction add?

Negligible. One function call per timing operation instead of inline code.

```typescript
// Before: 1 call to process.hrtime.bigint()
const elapsed = Number(process.hrtime.bigint() - start) / 1e6;

// After: 1 call to clock.getHighResTimeMs()
const elapsed = this.clock.getHighResTimeMs();
```

### Q: Can I mix live and deterministic in the same process?

Yes! Each session has its own clock. You can have:

```typescript
const liveSession = new UniversalLiveSession(request);
const replaySession = new UniversalLiveSession(request, { clock: replayClock });
// They run independently
```

### Q: What if I want to replay with slightly different parameters?

Create a new deterministic clock with the same timestamps but pass different options:

```typescript
const clock = replayManager.createReplayClock();

const variant1 = new UniversalLiveSession(request, { clock });
// vs
const clock2 = replayManager.createReplayClock(); // Fresh copy
const variant2 = new UniversalLiveSession({ ...request, sourceLanguage: "fr" }, { clock: clock2 });
```

Each gets a fresh copy of the timestamp sequence.

---

## Next Steps

1. **Run demo**: `node demo-replay.js`
   - Creates live and replay sessions
   - Compares their hashes
   - Saves artifacts for analysis

2. **Integrate with test suite**:
   - Call `testSessionStability()` for each feature
   - Assert `stable === true`

3. **Hook into CI/CD**:
   - On every commit, run stability tests
   - If any session becomes unstable, alert

4. **Analyze real sessions**:
   - Use `persistDebugSessionDump()` to save production sessions
   - Compare with deterministic replay to identify timing-driven divergence

---

## Files

- `clock-source.js` — ClockSource interface & implementations
- `live-session.js` — Updated with clock injection (Phase 1 ✓)
- `replay-manager.js` — Timestamp recording & replay management
- `session-store.js` — Updated with dump/persistence helpers
- `demo-replay.js` — Runnable demo of live vs deterministic

---

## Philosophy

> **The difference between "working" and "repeatable"**

A system can work beautifully in one run and drift subtly in another. By splitting **Live Mode** (observe reality) from **Deterministic Mode** (prove stability), you gain the power to:

- **Observe** nondeterminism without trying to eliminate it
- **Isolate** which parts of your logic are timing-sensitive
- **Prove** that your algorithm is sound independent of the noise

You're not building a perfect deterministic system. You're building one that **understands its own nondeterminism** and can **prove it works anyway**.
