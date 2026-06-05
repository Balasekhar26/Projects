# AI Observer Layer — Self-Healing Diagnostic Architecture

## 🎯 Core Principle

The AI Observer is a **read-only diagnostic and suggestion system** that watches your realtime speech pipeline without modifying it.

```
Runtime Events → Event Collector → Anomaly Detector → Suggestion Engine
                         ↓
                  System Doctor (offline simulator)
```

It is **NOT** an autopilot that directly controls the engine.

---

## 🧩 Architecture Components

### 1. EventCollector

**Purpose**: Captures all events flowing through the system in a time-ordered log.

**Ingests**:
- STT chunks (confidence, transcripts, RMS)
- Utterance lifecycle (spawned, updated, spoken)
- Arbitration decisions (speak/wait/morph)
- Playback boundaries (start, end, duration)
- Latency spikes and silence gaps

**Is read-only**: All ingest methods record passively; no state mutation.

```javascript
observer.ingestSttChunk({ chunkNumber, transcript, confidence, rms });
observer.ingestUtteranceUpdated(utterance, mode, delta);
observer.ingestArbitrationDecision(utteranceId, decision, systemState);
```

---

### 2. AnomalyDetector

**Purpose**: Analyzes event logs to identify patterns that suggest system problems.

**Detects**:
- `revision-oscillation` — utterance version keeps changing before speech
- `latency-spike-cluster` — sustained processing delays
- `silence-gaps` — long pauses where playback should occur
- `confidence-drop` — STT recognition quality degradation
- `version-starvation` — utterance stuck in "forming" state
- `playback-blocked-excessively` — arbitration gate too conservative
- `stability-gate-too-strict` — confidence threshold unachievable

**Output**: List of issues with root cause hypotheses and severity.

```javascript
const analysis = detector.analyzeLog(eventLog, utteranceSnapshots);
// analysis = { issues: [...], score: 0-100 }
```

---

### 3. SuggestionEngine

**Purpose**: Converts anomalies into actionable parameter adjustment suggestions.

**Generates suggestions** with:
- Parameter name (e.g., `stabilityWindowMs`)
- Direction (`increase`, `decrease`, `no-change`)
- Confidence score (0-1)
- Root cause explanation
- Estimated impact on system

**Manages suggestion lifecycle**:
- `pending` — waiting for user review
- `approved` — user accepted; ready for application
- `rejected` — user declined

```javascript
const suggestions = engine.generateSuggestions(issues);
// suggestions[0] = {
//   parameter: "stabilityWindowMs",
//   direction: "decrease",
//   confidence: 0.85,
//   ...
// }

engine.approveSuggestion(suggestionId, "Apply to reduce jitter");
```

---

### 4. SystemDoctor

**Purpose**: Offline replay simulator that tests parameter changes without touching live system.

**Records**: Complete session logs with all events and utterances.

**Simulates**: Parameter changes and predicts effects.

**Assesses**: Risks before applying changes.

```javascript
const recordingId = doctor.recordSession(eventLog, snapshots, config);
const simulation = doctor.simulateParameterChange(
  recordingId,
  "stabilityWindowMs",
  150  // proposed new value
);

// simulation.predictions = [{
//   aspect: "playback-latency",
//   direction: "decrease",
//   explanation: "..."
// }]
//
// simulation.riskAssessment = {
//   level: "medium",
//   factors: ["..."],
//   recommendation: "..."
// }
```

---

## 📡 Integration Points

### Hook 1: STT Chunk Processing

In `realtime-translator.js`, after STT returns:

```javascript
if (observer) {
  observer.ingestSttChunk({
    chunkNumber,
    transcript: transcriptState.fullText,
    confidence: transcriptState.confidence,
    isStable: transcriptState.isStable,
    rms: chunk.analysis?.rms,
    durationMs: chunk.durationMs,
  });
}
```

### Hook 2: Utterance Updates

In `utterance-manager.js`, when utterance target changes:

```javascript
if (observer) {
  observer.ingestUtteranceUpdated(utterance, mode, targetDelta);
}
```

### Hook 3: Arbitration Decisions

In `realtime-translator.js`, after `decidePlayback()`:

```javascript
if (observer) {
  observer.ingestArbitrationDecision(utterance.id, arbitration, {
    currentJob: this.playbackController.currentJob,
    currentConfidence: this.playbackController.currentConfidence,
  });
}
```

### Hook 4: Playback Lifecycle

In `buildPlaybackEvent()` callbacks:

```javascript
onAudibleStart: () => {
  if (observer) {
    observer.ingestPlaybackStart(utteranceId, version);
  }
  // ...
},
onAudibleEnd: () => {
  if (observer) {
    observer.ingestPlaybackEnd(utteranceId, version, durationMs);
  }
  // ...
},
```

---

## 🔬 Usage Patterns

### Pattern 1: Continuous Monitoring

```javascript
const observer = new AIObserver({
  analysisIntervalMs: 10000,  // analyze every 10 seconds
});

// Wire into pipeline (see integration points above)

// Periodically analyze
setInterval(() => {
  const report = observer.analyze();
  if (report) {
    console.log(observer.formatDiagnostic());
  }
}, 15000);
```

### Pattern 2: Manual Analysis

```javascript
observer.analyze();
const suggestions = observer.getSuggestions();

for (const suggestion of suggestions) {
  console.log(`${suggestion.parameter}: ${suggestion.direction}`);
  console.log(`  Reason: ${suggestion.reason}`);
  console.log(`  Confidence: ${(suggestion.confidence * 100).toFixed(0)}%`);
  
  // User reviews and decides
  if (userApproves(suggestion)) {
    observer.suggestionEngine.approveSuggestion(suggestion.id);
  }
}
```

### Pattern 3: Offline Testing (System Doctor)

```javascript
// Record a real session
const recordingId = observer.recordSession(currentConfig);

// Simulate a parameter change without touching live system
const sim = observer.simulateParameterChange(
  recordingId,
  "stabilityWindowMs",
  150
);

// Review predictions and risks
console.log(observer.getSimulationReport(sim.id));

// If predictions are acceptable, apply manually to config
if (sim.riskAssessment.level === "low") {
  config.stabilityWindowMs = 150;
  restartPipeline();
}
```

---

## ⚙️ Configuration

```javascript
const observer = new AIObserver({
  maxHistoryMinutes: 5,              // keep last 5 minutes of events
  analysisIntervalMs: 10000,         // analyze every 10 seconds
  latencyThresholdMs: 250,           // alert if chunk > 250ms
  silenceThresholdMs: 500,           // alert if gap > 500ms
  revisionOscillationWindow: 1000,   // check oscillation in last 1s
  confidenceDropThreshold: 0.15,     // alert if drop > 0.15
});
```

---

## 🛡️ Safety Guarantees

### What the Observer CANNOT do:

- ❌ Modify `utterance-manager.js` at runtime
- ❌ Change arbitration thresholds live
- ❌ Interrupt playback directly
- ❌ Alter config without human approval
- ❌ Mutate pipeline state

### What the Observer CAN do:

- ✅ Record all events
- ✅ Identify patterns and issues
- ✅ Suggest parameter changes
- ✅ Simulate changes offline
- ✅ Generate diagnostic reports

---

## 📊 Output Examples

### Health Report

```
=== AI OBSERVER DIAGNOSTIC REPORT ===
System Health Score: 78/100
Total Issues Detected: 3

Issues Detected:
  [HIGH] revision-oscillation
    → translation confidence unstable or threshold too sensitive

  [MEDIUM] latency-spike-cluster
    → STT, translation, or TTS backend slower than configured expectations

  [MEDIUM] silence-gaps
    → continuation layer not triggering or playback delay too high
```

### Suggestion Queue

```
=== AI OBSERVER SUGGESTIONS ===

[1] realtimeUtteranceSimilarityThreshold (increase)
    Issue: revision-oscillation
    Severity: high
    Confidence: 85%
    Reason: reduce sensitivity to minor translation variations
    Root Cause: translation confidence unstable or threshold too sensitive
    Estimated Impact: Reduce audio jitter and speaking hesitation artifacts
    ID: sug-1702000000-abc123

[2] continuationDelayMs (decrease)
    Issue: silence-gaps
    Severity: medium
    Confidence: 70%
    ...
```

### System Doctor Report

```
=== SYSTEM DOCTOR SIMULATION REPORT ===
Parameter: stabilityWindowMs
Original Value: 220
Proposed Value: 150

=== PREDICTIONS ===
Aspect: playback-latency
Direction: decrease (moderate impact)
Expected: Reducing stability window will allow speech to start earlier...

=== RISK ASSESSMENT ===
Risk Level: medium
Risk Factors:
  - High-magnitude change to playback-latency
  - Parameter directly affects arbitration gate; monitor jitter if applied

Recommendation: Test on isolated session first before production deployment
```

---

## 🧠 Design Philosophy

The Observer embodies a key principle:

> **Intelligence without autonomy. Diagnosis without blind automation.**

It watches. It learns. It suggests. But it never drives.

The pipeline stays deterministic. The Observer stays humble.

---

## 🚀 Future Enhancements

- [ ] Long-term trend analysis (hours/days)
- [ ] Cross-session pattern learning
- [ ] Confidence scoring for multi-parameter suggestions
- [ ] Integration with config management API
- [ ] Automated A/B testing framework
- [ ] Real-time dashboard visualization

---

## 📝 Notes

- The observer is designed to be **zero-overhead** if unused (all methods are no-ops if observer not wired)
- Event log is **automatically pruned** based on `maxHistoryMinutes`
- Suggestions can be **batch-approved** for common patterns
- System Doctor recordings are **completely isolated** from runtime

This architecture allows you to build a **self-understanding** speech system without sacrificing the determinism that makes it reliable.
