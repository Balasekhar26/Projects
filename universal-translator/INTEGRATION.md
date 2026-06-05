# Integration Guide: Clock Abstraction & Replay

This guide shows how to wire the new clock abstraction and replay infrastructure into your existing API endpoints and session management.

## Quick Integration Checklist

- [x] **Phase 1: Clock Abstraction** — Inject into UniversalLiveSession
- [x] **Phase 2: Arrival Index** — Track raw insertion order
- [x] **Phase 3: Persistence** — Save dumps to filesystem
- [ ] **Phase 4: API Endpoints** — Expose dump endpoints
- [ ] **Phase 5: Replay Testing** — Wire replay manager into test suite

---

## Phase 4: API Endpoints

### Option A: HTTP Endpoints (Express/Next.js)

Add to your API route handler:

```typescript
import express from "express";
import {
  getSession,
  getSessionDebugDump,
  persistSessionDebugDump,
} from "ult-core/session-store";

const router = express.Router();

/**
 * GET /api/debug/sessions/:id/dump
 * Query: ?mode=full|compact&limit=100
 */
router.get("/api/debug/sessions/:id/dump", (req, res) => {
  const { id } = req.params;
  const { mode = "compact", limit } = req.query;

  const dump = getSessionDebugDump(id, {
    mode,
    limit: limit ? parseInt(limit) : undefined,
  });

  if (!dump) {
    return res.status(404).json({ error: "Session not found" });
  }

  res.json(dump);
});

/**
 * POST /api/debug/sessions/:id/dump/persist
 * Save dump to disk
 * Body: { dumpDir: "./debug-dumps" }
 */
router.post("/api/debug/sessions/:id/dump/persist", async (req, res) => {
  const { id } = req.params;
  const { dumpDir = "./debug-dumps" } = req.body;

  const result = await persistSessionDebugDump(id, dumpDir);

  if (!result) {
    return res.status(404).json({ error: "Session not found" });
  }

  res.json({
    success: true,
    ...result,
  });
});

/**
 * GET /api/debug/sessions/:id/events
 * Get specific debug events
 * Query: ?mode=full|compact&limit=50
 */
router.get("/api/debug/sessions/:id/events", (req, res) => {
  const { id } = req.params;
  const { mode = "compact", limit = 50 } = req.query;

  const session = getSession(id);
  if (!session) {
    return res.status(404).json({ error: "Session not found" });
  }

  const events = session.getDebugEvents(mode).slice(-parseInt(limit));

  res.json({
    sessionId: id,
    mode,
    eventCount: events.length,
    events,
  });
});

export default router;
```

### Option B: Direct Session Method Calls

If you're creating sessions from code:

```typescript
import { createSession, ReplayManager } from "ult-core/session-store";

async function runSessionWithDebugCapture(request, inputSequence) {
  const session = await createSession(request);
  const replayManager = new ReplayManager();

  // Record timestamps for each event
  const originalPublish = session.publish.bind(session);
  session.publish = function (type, payload) {
    originalPublish(type, payload);
    replayManager.recordTimestamps(this);
  };

  // Process input
  for (const input of inputSequence) {
    await session.enqueueChunk(input);
  }

  // Capture and persist dumps
  const dump = session.getDebugSessionDump({ mode: "full" });
  await session.persistDebugSessionDump(`./debug-dumps/${session.id}`);

  // Save timestamp recording for replay
  await replayManager.saveTimestampRecording(
    `./debug-dumps/${session.id}/timestamps.json`
  );

  return {
    sessionId: session.id,
    eventCount: dump.recordCount,
    dump,
  };
}
```

---

## Phase 5: Replay Testing

### Integration with Test Framework

```typescript
// jest.config.js
module.exports = {
  testEnvironment: "node",
  setupFilesAfterEnv: ["./test/setup.js"],
};

// test/setup.js
import { ReplayManager } from "ult-core/session-store";

// Make ReplayManager available globally
globalThis.ReplayManager = ReplayManager;
```

### Test Suite Example

```typescript
import {
  UniversalLiveSession,
  SESSION_STATES,
} from "ult-core/session";
import { ReplayManager } from "ult-core/session-store";

describe("Session Stability", () => {
  it("should produce identical hashes in deterministic replay", async () => {
    const request = {
      platform: "test",
      sourceLanguage: "en",
      targetLanguage: "es",
      // ... other fields
    };

    // Phase 1: Live session
    const session1 = new UniversalLiveSession(request);
    const replayManager = new ReplayManager();

    session1.on("event", () => replayManager.recordTimestamps(session1));
    await session1.start();

    // Simulate input
    session1.publish("status", { message: "Processing chunk 1" });
    session1.publish("partial_transcript", { transcript: "Hello world" });
    session1.publish("final_translation", { translatedText: "Hola mundo" });

    const dump1 = session1.getDebugSessionDump({ mode: "full" });
    const hashes1 = dump1.events.map((e) => e.integrityHash);

    // Phase 2: Deterministic replay
    const clock = replayManager.createReplayClock();
    const session2 = new UniversalLiveSession(request, { clock });
    await session2.start();

    // Same input in same order
    session2.publish("status", { message: "Processing chunk 1" });
    session2.publish("partial_transcript", { transcript: "Hello world" });
    session2.publish("final_translation", { translatedText: "Hola mundo" });

    const dump2 = session2.getDebugSessionDump({ mode: "full" });
    const hashes2 = dump2.events.map((e) => e.integrityHash);

    // Assert stability
    expect(hashes1).toEqual(hashes2);
    expect(dump1.recordCount).toBe(dump2.recordCount);
  });

  it("should detect nondeterminism if logic varies with timing", async () => {
    // This test intentionally demonstrates detection
    const request = { /* ... */ };

    const session1 = new UniversalLiveSession(request);
    const replayManager = new ReplayManager();

    session1.on("event", () => replayManager.recordTimestamps(session1));
    await session1.start();
    session1.publish("status", { message: "Test" });
    const dump1 = session1.getDebugSessionDump({ mode: "full" });

    // If you had nondeterministic logic, this would fail
    const clock = replayManager.createReplayClock();
    const session2 = new UniversalLiveSession(request, { clock });
    await session2.start();
    session2.publish("status", { message: "Test" });
    const dump2 = session2.getDebugSessionDump({ mode: "full" });

    // Should match if stable
    expect(dump1.events[0].integrityHash).toBe(dump2.events[0].integrityHash);
  });
});
```

---

## Monitoring & Observability

### Dashboard Integration

```typescript
// Create a status endpoint for monitoring
app.get("/api/debug/stats", (req, res) => {
  const sessions = listSessions();

  const stats = {
    activeSessions: sessions.length,
    sessions: sessions.map((s) => ({
      id: s.id,
      state: s.state,
      eventsCapture: s.debugEventsFull?.length || 0,
      eventsCompact: s.debugEventsCompact?.length || 0,
    })),
  };

  res.json(stats);
});
```

### Real-Time Event Streaming

```typescript
// Server-Sent Events endpoint
app.get("/api/debug/sessions/:id/stream", (req, res) => {
  const { id } = req.params;
  const session = getSession(id);

  if (!session) {
    return res.status(404).send("Session not found");
  }

  res.setHeader("Content-Type", "text/event-stream");
  res.setHeader("Cache-Control", "no-cache");
  res.setHeader("Connection", "keep-alive");

  const onEvent = (event) => {
    const record = session.debugEventsFull[session.debugEventsFull.length - 1];
    res.write(`data: ${JSON.stringify(record)}\n\n`);
  };

  session.on("event", onEvent);

  res.on("close", () => {
    session.removeListener("event", onEvent);
  });
});
```

---

## File Structure After Integration

```
packages/ult-core/
├── src/
│   └── session/
│       ├── clock-source.js        (NEW - Clock abstraction)
│       ├── replay-manager.js       (NEW - Replay infrastructure)
│       ├── live-session.js         (UPDATED - Clock injection)
│       └── session-store.js        (UPDATED - Dump helpers)
├── demo-replay.js                  (NEW - Demo script)
├── CLOCK_AND_REPLAY.md             (NEW - Full documentation)
└── INTEGRATION.md                  (NEW - This file)
```

---

## Deployment Considerations

### Volume/Storage for Dumps

Debug dumps can be large. Plan accordingly:

```typescript
// Option 1: Temporary storage
const tmpDir = path.join(os.tmpdir(), "ult-debug-dumps");
await session.persistDebugSessionDump(tmpDir);

// Option 2: Permanent storage with rotation
const dumpDir = "/var/log/ult-sessions";
const oldestAllowed = Date.now() - 7 * 24 * 60 * 60 * 1000; // 7 days
const files = await fs.readdir(dumpDir);
for (const file of files) {
  const stat = await fs.stat(path.join(dumpDir, file));
  if (stat.mtimeMs < oldestAllowed) {
    await fs.rm(path.join(dumpDir, file));
  }
}
await session.persistDebugSessionDump(dumpDir);
```

### Security

Dumps contain sensitive data (timestamps, audio processing details). Restrict access:

```typescript
// Only allow authenticated admin users
app.get("/api/debug/sessions/:id/dump", requireAdmin, (req, res) => {
  // ... return dump
});
```

### Performance

For production systems, consider:

1. **Conditional capture** — Only dump on error or every N-th session
2. **Compression** — Gzip dumps before storage
3. **Async persistence** — Don't block session on dump writes

```typescript
// Async dump in background
session.on("stopped", async () => {
  try {
    await session.persistDebugSessionDump("./debug-dumps");
  } catch (error) {
    console.error("Dump failed:", error);
    // Don't fail the session
  }
});
```

---

## Troubleshooting

### Timestamps Don't Match

```
Error: DeterministicClockSource: Exhausted 47 timestamps at index 48
```

**Cause:** Recorded session had 47 events but replay tried to create 48.

**Fix:** Ensure same input sequence during replay:

```typescript
// LIVE
session.publish("event1", {});
session.publish("event2", {}); // 2 events recorded

// REPLAY must match
replaySession.publish("event1", {});
replaySession.publish("event2", {}); // Same 2 events
```

### Hashes Don't Match in Deterministic Mode

The logic is timing-sensitive. Debug with:

```typescript
const liveDump = session1.getDebugSessionDump({ mode: "full" });
const replayDump = session2.getDebugSessionDump({ mode: "full" });

for (let i = 0; i < liveDump.events.length; i++) {
  const liveEvent = liveDump.events[i];
  const replayEvent = replayDump.events[i];

  if (liveEvent.integrityHash !== replayEvent.integrityHash) {
    console.log(`Mismatch at event ${i}:`);
    console.log(`  Live contributions:`, liveEvent.contributions);
    console.log(`  Replay contributions:`, replayEvent.contributions);
    console.log(`  Live flags:`, liveEvent.flags);
    console.log(`  Replay flags:`, replayEvent.flags);
  }
}
```

---

## Success Criteria

- [ ] Clock abstraction injected into UniversalLiveSession
- [ ] Arrival index tracked in debug records
- [ ] Session dumps persist to filesystem
- [ ] API endpoints for /debug/sessions/:id/dump
- [ ] Replay manager wired into test suite
- [ ] Stability tests passing
- [ ] Documentation updated with new capabilities

---

## Next: Real-World Testing

Once integrated, run the demo:

```bash
node packages/ult-core/demo-replay.js
```

This will:
1. Create a live session and record timestamps
2. Replay with deterministic clock
3. Compare hashes
4. Save results to `./replay-demo-output/`

If hashes match → **Deterministic by design** ✅
If hashes differ → **Investigate timing sensitivity** ⚠️
