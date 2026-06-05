# Quick Start: Live vs Deterministic Replay

## TL;DR

You built a system to **observe nondeterminism in live mode** and **prove stability in replay mode**.

### 30 seconds to understanding

```typescript
// 🟢 LIVE MODE: Real clocks, real nondeterminism
const session1 = new UniversalLiveSession(request);
const manager = new ReplayManager();
session1.on("event", () => manager.recordTimestamps(session1));
const hash1 = session1.getDebugSessionDump().events[0].integrityHash;

// 🔵 DETERMINISTIC MODE: Recorded clocks, proves stability
const clock = manager.createReplayClock();
const session2 = new UniversalLiveSession(request, { clock });
const hash2 = session2.getDebugSessionDump().events[0].integrityHash;

// If hash1 === hash2 → Logic is stable ✅
// If hash1 !== hash2 → Logic is timing-sensitive ⚠️
```

---

## Run the Demo

```bash
cd packages/ult-core
node demo-replay.js
```

This:
1. Creates a live session and records timestamps
2. Replays with deterministic clock
3. Compares hashes
4. Saves results to `./replay-demo-output/`

---

## Three Key Files

### 1. Clock Abstraction
**File:** `packages/ult-core/src/session/clock-source.js`

**What:** Abstraction layer for all timing calls

**Use:** You don't call this directly; it's injected into sessions

```typescript
// Behind the scenes:
const session = new UniversalLiveSession(request, {
  clock: myClockSource  // Optional; defaults to LiveClockSource
});
```

### 2. Replay Manager
**File:** `packages/ult-core/src/session/replay-manager.js`

**What:** Records timestamps from live sessions and creates replay clocks

**Use:**

```typescript
const manager = new ReplayManager();

// Record from live session
session.on("event", () => manager.recordTimestamps(session));

// Create replay clock
const clock = manager.createReplayClock();

// Save for offline analysis
await manager.saveTimestampRecording("./my-timestamps.json");
```

### 3. Session Dump
**File:** Updated `packages/ult-core/src/session/live-session.js`

**What:** Get and persist complete session debug data

**Use:**

```typescript
// Get dump (in-memory)
const dump = session.getDebugSessionDump({ mode: "full", limit: 100 });

// Persist to filesystem
await session.persistDebugSessionDump("./debug-dumps");
```

---

## Typical Workflow

### Step 1: Run Live Session

```typescript
import { UniversalLiveSession } from "ult-core";
import { ReplayManager } from "ult-core/session-store";

const request = {
  sourceLanguage: "en",
  targetLanguage: "es",
  // ... other config
};

const session = new UniversalLiveSession(request);
const manager = new ReplayManager();

// Capture timestamps for every event
session.on("event", () => manager.recordTimestamps(session));

await session.start();
await session.enqueueChunk(audioChunk);
await session.stop();

// Get the dump
const dump = session.getDebugSessionDump({ mode: "full" });
console.log(`Captured ${dump.recordCount} events`);
console.log(`First hash:`, dump.events[0].integrityHash);
```

### Step 2: Replay with Recorded Timestamps

```typescript
// Use the same manager to get replay clock
const replayClock = manager.createReplayClock();

// Create new session with deterministic clock
const replaySession = new UniversalLiveSession(request, {
  clock: replayClock
});

await replaySession.start();
await replaySession.enqueueChunk(audioChunk);  // Same input
await replaySession.stop();

// Get the dump
const replayDump = replaySession.getDebugSessionDump({ mode: "full" });
console.log(`First hash:`, replayDump.events[0].integrityHash);
```

### Step 3: Compare

```typescript
const originalHashes = dump.events.map(e => e.integrityHash);
const replayHashes = replayDump.events.map(e => e.integrityHash);

const stable = originalHashes.every((h, i) => h === replayHashes[i]);

if (stable) {
  console.log("✅ STABLE: Logic produces identical outcomes");
} else {
  console.log("⚠️ UNSTABLE: Logic varies with timing");
  
  // Debug: Find first mismatch
  for (let i = 0; i < originalHashes.length; i++) {
    if (originalHashes[i] !== replayHashes[i]) {
      console.log(`Mismatch at event ${i}:`);
      console.log(`  Original:`, dump.events[i].contributions);
      console.log(`  Replay:  `, replayDump.events[i].contributions);
      break;
    }
  }
}
```

---

## Common Patterns

### Pattern 1: Save Live Data for Later Analysis

```typescript
const session = new UniversalLiveSession(request);
const manager = new ReplayManager();

session.on("event", () => manager.recordTimestamps(session));

// ... run session ...

// Save everything
const sessionDir = `./sessions/${session.id}`;
await session.persistDebugSessionDump(sessionDir);
await manager.saveTimestampRecording(`${sessionDir}/timestamps.json`);

console.log(`Session saved to ${sessionDir}`);
```

### Pattern 2: Load Saved Data and Replay Offline

```typescript
// Load timestamps from earlier session
const manager = await ReplayManager.fromSavedRecording(
  "./sessions/550e8400-e29b-41d4-a716-446655440000/timestamps.json"
);

// Create replay clock
const clock = manager.createReplayClock();

// Replay
const replaySession = new UniversalLiveSession(request, { clock });
// ... run input ...
```

### Pattern 3: Test Stability in Test Suite

```typescript
import { UniversalLiveSession } from "ult-core";
import { ReplayManager } from "ult-core/session-store";

describe("Session Stability", () => {
  it("should be deterministic with recorded timing", async () => {
    const request = { /* ... */ };
    const input = { /* ... */ };

    // Live
    const live = new UniversalLiveSession(request);
    const manager = new ReplayManager();
    live.on("event", () => manager.recordTimestamps(live));
    await live.start();
    await live.enqueueChunk(input);
    const liveDump = live.getDebugSessionDump({ mode: "full" });

    // Replay
    const clock = manager.createReplayClock();
    const replay = new UniversalLiveSession(request, { clock });
    await replay.start();
    await replay.enqueueChunk(input);
    const replayDump = replay.getDebugSessionDump({ mode: "full" });

    // Assert
    for (let i = 0; i < liveDump.events.length; i++) {
      expect(liveDump.events[i].integrityHash)
        .toBe(replayDump.events[i].integrityHash);
    }
  });
});
```

---

## Understanding the Output

### Session Dump Event

```json
{
  "id": "550e8400-debug-0",
  "type": "status",
  "sequence": 0,
  "arrivalIndex": 0,
  "rawTime": 1700000000123,
  "sessionTime": 0.456,
  "normalizedTime": 0.456,
  "dominantDomain": "utterance",
  "contributions": {
    "utterance": 45.2,
    "system": 2.1
  },
  "flags": [],
  "timing": {
    "coherenceScore": 0.95,
    "skew": { "utterance": 0.001 }
  },
  "causalityKey": {
    "transformation": "normalize.v2",
    "sourceEventIds": [],
    "dependencyHash": "abc123..."
  },
  "integrityHash": "def456..."
}
```

**Key fields:**
- `arrivalIndex` — Raw insertion order (for stable sorting)
- `sessionTime` — Elapsed milliseconds since session start
- `dominantDomain` — Which timing source won (utterance, system, etc.)
- `contributions` — How much each source contributed to the time
- `flags` — `TIME_REGRESSION`, `BROKEN_CHAIN`, etc.
- `integrityHash` — Hash of this complete record
- `integrityHash` match between live and replay = proof of stability

### Dump Summary

```json
{
  "sessionId": "550e8400-...",
  "mode": "full",
  "recordCount": 47,
  "events": [/* array of events */],
  "state": "healthy",
  "health": {
    "sessionState": "healthy",
    "models": { "stt": "offline", "translation": "offline" }
  }
}
```

---

## Troubleshooting

### "Exhausted X timestamps at index Y"

**Cause:** Replay tried to get more timestamps than were recorded

**Fix:** Make sure replay input matches live input exactly

```typescript
// Live: 5 events
session.publish("event1", {});
session.publish("event2", {});
// ... 3 more ...

// Replay must have same 5 events
replaySession.publish("event1", {});
replaySession.publish("event2", {});
// ... same 3 more ...
```

### Hashes don't match in deterministic mode

**Cause:** Logic is timing-sensitive (or you've found a bug!)

**Debug:**
```typescript
// Compare the actual contributions
const liveEvent = liveDump.events[i];
const replayEvent = replayDump.events[i];

if (liveEvent.integrityHash !== replayEvent.integrityHash) {
  console.log("Live contributions:", liveEvent.contributions);
  console.log("Replay contributions:", replayEvent.contributions);
  console.log("Live dominance:", liveEvent.dominantDomain);
  console.log("Replay dominance:", replayEvent.dominantDomain);
}
```

---

## Next: Running the Real Demo

```bash
cd c:\Users\balu\Projects\ult-translator\packages\ult-core
node demo-replay.js
```

This will:
1. Create a live session
2. Publish events and record timestamps
3. Create a deterministic session with the recorded clock
4. Publish the same events
5. Compare hashes
6. Save results

Look for:
- `replay-demo-output/replay-comparison.json` — Summary of results
- `replay-demo-output/recorded-timestamps.json` — Timestamps for offline replay
- `replay-demo-output/dumps/` — Full session dumps

---

## Key Takeaway

You don't need to eliminate nondeterminism. You need to:

1. **Observe** it in live mode (real clocks)
2. **Prove** stability in replay mode (recorded clocks)
3. **Debug** with actual evidence (session dumps)

This infrastructure gives you all three.
