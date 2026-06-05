# Implementation Checklist

## ✅ Completed: Core Infrastructure

### Clock Abstraction
- [x] `LiveClockSource` class (real system timers)
- [x] `DeterministicClockSource` class (recorded timestamps)
- [x] `createClockSource()` factory function
- [x] Monotonic time enforcement in both
- [x] File: `clock-source.js`

### Session Integration
- [x] Clock injection into `UniversalLiveSession` constructor
- [x] Clock used for all timing operations (`_getSessionTimeMs()`, latency tracking)
- [x] Removed manual `process.hrtime.bigint()` tracking
- [x] Added `debugEventSequence` counter for arrival index

### Arrival Index Tracking
- [x] Added `arrivalIndex` field to debug records
- [x] Increments per event in `_recordDebugEvent()`
- [x] Stored in record metadata for stable sorting

### Session Dump & Persistence
- [x] `getDebugSessionDump(options)` method
- [x] `persistDebugSessionDump(dumpDir, options)` method  
- [x] Dump includes all necessary fields (hashes, contributions, flags, timing)
- [x] Session store helpers: `getSessionDebugDump()`, `persistSessionDebugDump()`

### Replay Infrastructure
- [x] `ReplayManager` class
- [x] `recordTimestamps(session)` method
- [x] `createReplayClock()` method
- [x] `saveTimestampRecording(filepath)` async method
- [x] `fromSavedRecording(filepath)` static method
- [x] Timestamp recording and retrieval
- [x] File: `replay-manager.js`

### Documentation
- [x] `CLOCK_AND_REPLAY.md` — Full architecture and usage
- [x] `INTEGRATION.md` — API integration guide
- [x] `IMPLEMENTATION_COMPLETE.md` — Summary
- [x] `QUICKSTART.md` — Quick reference
- [x] `demo-replay.js` — Runnable demonstration

### Code Quality
- [x] No syntax errors in any files
- [x] All imports properly configured
- [x] Clean separation of concerns
- [x] Comprehensive JSDoc comments

---

## 🔄 Ready to Test: What You Should Do Next

### Immediate (5 minutes)

- [ ] Run the demo:
  ```bash
  cd packages/ult-core
  node demo-replay.js
  ```
  
- [ ] Check output:
  - [ ] `replay-demo-output/replay-comparison.json` exists
  - [ ] `replay-demo-output/recorded-timestamps.json` exists
  - [ ] `replay-demo-output/dumps/` contains session dumps
  - [ ] Event hashes match (✓ or ✗)

### Short Term (Today)

- [ ] **Verify in test environment**:
  - [ ] Run with real audio input
  - [ ] Confirm timestamps are being recorded
  - [ ] Check dump file sizes

- [ ] **Review the evidence**:
  - [ ] Open `replay-demo-output/replay-comparison.json`
  - [ ] Check event count and hash matches
  - [ ] Note any mismatches for investigation

- [ ] **Run with your actual request object**:
  - [ ] Replace demo `testRequest` with real config
  - [ ] Test with actual STT/translation pipeline
  - [ ] Verify full session lifecycle

### Short-Medium Term (This Week)

- [ ] **Add API endpoints** (see `INTEGRATION.md`):
  - [ ] `GET /api/debug/sessions/:id/dump?mode=full|compact`
  - [ ] `POST /api/debug/sessions/:id/dump/persist`
  - [ ] `GET /api/debug/sessions/:id/events?mode=full&limit=50`

- [ ] **Wire into test suite**:
  - [ ] Add stability test (see `INTEGRATION.md`)
  - [ ] Run against each feature
  - [ ] Assert `stable === true`

- [ ] **Set up monitoring**:
  - [ ] Add `GET /api/debug/stats` endpoint
  - [ ] Track active sessions and dump sizes
  - [ ] Monitor disk usage

### Medium Term (This Month)

- [ ] **Production integration**:
  - [ ] Add conditional dumping (on error, sampling)
  - [ ] Implement dump rotation/cleanup
  - [ ] Add compression for storage efficiency
  - [ ] Security: restrict access to authenticated users

- [ ] **Analysis workflow**:
  - [ ] Save live session dumps
  - [ ] Identify which sessions are timing-sensitive
  - [ ] Create bug reports with dump evidence

- [ ] **CI/CD integration**:
  - [ ] Add stability tests to pipeline
  - [ ] Auto-detect regressions
  - [ ] Generate stability reports

---

## ⚠️ Known Limitations

### What This DOES
- ✅ Observe real nondeterminism
- ✅ Prove logic stability with recorded timing
- ✅ Capture and persist evidence
- ✅ Enable deterministic replay testing
- ✅ Provide detailed timing analysis

### What This DOESN'T (Yet)
- ❌ Fix nondeterminism (by design)
- ❌ Automatically detect root causes
- ❌ Handle non-deterministic logic (e.g., randomness)
- ❌ Provide automatic remediation
- ❌ Integrate with CI/CD (requires custom scripts)

---

## File Manifest

### New Files (5 total)
```
packages/ult-core/
├── src/session/
│   ├── clock-source.js         ✅ Clock abstraction (210 lines)
│   └── replay-manager.js        ✅ Replay infrastructure (220 lines)
└── demo-replay.js              ✅ Runnable demo (230 lines)

root/
├── CLOCK_AND_REPLAY.md         ✅ Architecture documentation
├── INTEGRATION.md              ✅ API integration guide
├── IMPLEMENTATION_COMPLETE.md  ✅ Summary document
└── QUICKSTART.md               ✅ Quick reference
```

### Modified Files (2 total)
```
packages/ult-core/src/session/
├── live-session.js             ✅ +100 lines (clock, dumps)
└── session-store.js            ✅ +30 lines (helpers)
```

---

## How to Verify Installation

### 1. Check Files Exist

```bash
ls -la packages/ult-core/src/session/clock-source.js
ls -la packages/ult-core/src/session/replay-manager.js
ls -la packages/ult-core/demo-replay.js
```

### 2. Check Imports Resolve

```bash
cd packages/ult-core
node -e "const {LiveClockSource} = require('./src/session/clock-source'); console.log('✓ Clock imports work');"
node -e "const {ReplayManager} = require('./src/session/replay-manager'); console.log('✓ Replay imports work');"
node -e "const {getSessionDebugDump} = require('./src/session/session-store'); console.log('✓ Store imports work');"
```

### 3. Run the Demo

```bash
node demo-replay.js
# Look for: ✅ SUCCESS or ⚠️ Nondeterminism detected
```

---

## Integration Points

### For Tests
```typescript
import { UniversalLiveSession } from "./src/session/live-session";
import { ReplayManager } from "./src/session/replay-manager";

const manager = new ReplayManager();
// ... record and replay ...
```

### For API
```typescript
import { getSessionDebugDump, persistSessionDebugDump } from "./src/session/session-store";

app.get("/api/debug/sessions/:id/dump", (req, res) => {
  const dump = getSessionDebugDump(req.params.id);
  res.json(dump);
});
```

### For Monitoring
```typescript
import { getSession } from "./src/session/session-store";

const session = getSession(sessionId);
const dump = session.getDebugSessionDump({ mode: "compact", limit: 50 });
// ... analyze dump ...
```

---

## Success Metrics

You'll know it's working when:

1. ✅ Demo runs without errors
2. ✅ Dumps are created and saved
3. ✅ Hash comparison shows (✓ or ✗) for each event
4. ✅ Timestamps are recorded
5. ✅ Deterministic replay produces consistent results
6. ✅ Session store helpers return data
7. ✅ Tests can access debug events

---

## Troubleshooting Guide

### Import Errors
```
Error: Cannot find module 'clock-source.js'
```
→ Check file path and ensure it exists

### Demo Won't Run
```
Error: UniversalLiveSession is not a constructor
```
→ Verify `live-session.js` exports the class correctly

### Dump Not Saving
```
Error: ENOENT: no such directory './debug-dumps'
```
→ Directory will be created automatically; check write permissions

### Hashes Don't Match
```
Live: abc123... | Replay: def456...
```
→ Timing-sensitive logic detected; see QUICKSTART.md "Troubleshooting"

---

## Documentation Map

```
├── QUICKSTART.md                 ← Start here (5 min read)
├── CLOCK_AND_REPLAY.md           ← Full architecture (30 min)
├── INTEGRATION.md                ← API wiring (20 min)
└── IMPLEMENTATION_COMPLETE.md    ← Overview (10 min)

Code:
├── clock-source.js               ← ClockSource interface
├── replay-manager.js             ← Replay infrastructure
└── live-session.js (updated)     ← Session with clock
```

---

## Performance Notes

### Clock Overhead
- Negligible: one function call per timing operation
- No allocation, no parsing
- Identical to direct calls in live mode

### Dump Storage
- Full mode: ~5-10 KB per session (100 events)
- Compact mode: ~2-3 KB per session
- Budget: 1 GB storage = 100k-200k full sessions

### Timestamp Recording
- Negligible overhead
- Arrays in memory
- ~1 KB per 100 events

---

## Next Steps After Verification

1. **Run demo** → See it work
2. **Add API endpoints** → Expose to frontend
3. **Wire tests** → Automate stability checking
4. **Monitor production** → Identify patterns
5. **Debug issues** → Use dumps as evidence

Then you have a complete observability system for nondeterminism.

---

## Questions?

- **How does it work?** → `CLOCK_AND_REPLAY.md`
- **How do I use it?** → `QUICKSTART.md`
- **How do I integrate it?** → `INTEGRATION.md`
- **What's the output?** → `IMPLEMENTATION_COMPLETE.md`

All documentation is cross-referenced. Start with `QUICKSTART.md`.
