const { EventEmitter } = require("events");

class EventCollector extends EventEmitter {
  constructor({ maxHistoryMinutes = 5 } = {}) {
    super();
    this.maxHistoryMs = maxHistoryMinutes * 60 * 1000;
    this.eventLog = [];
    this.utteranceSnapshots = new Map();
    this.pausedAt = null;
    this.isPaused = false;
  }

  collectSttChunk(chunkInfo) {
    const event = {
      t: Date.now(),
      type: "stt-chunk",
      chunkNumber: chunkInfo.chunkNumber || 0,
      transcript: chunkInfo.transcript || "",
      confidence: Number.isFinite(chunkInfo.confidence) ? chunkInfo.confidence : 0,
      isStable: Boolean(chunkInfo.isStable),
      extendsPrevious: Boolean(chunkInfo.extendsPrevious),
      deltaText: chunkInfo.deltaText || "",
      rms: Number.isFinite(chunkInfo.rms) ? chunkInfo.rms : null,
      durationMs: Number.isFinite(chunkInfo.durationMs) ? chunkInfo.durationMs : 0,
      reason: chunkInfo.reason || "unknown",
    };
    this._appendEvent(event);
    return event;
  }

  collectUtteranceSpawned(utterance) {
    const event = {
      t: Date.now(),
      type: "utterance-spawned",
      utteranceId: utterance.id,
      revision: utterance.revision,
      status: utterance.status,
      sourceText: utterance.source.hypothesis,
      confidence: utterance.source.confidence,
    };
    this._appendEvent(event);
    this._snapshotUtterance(utterance);
    return event;
  }

  collectUtteranceUpdated(utterance, mode, delta) {
    const event = {
      t: Date.now(),
      type: "utterance-updated",
      utteranceId: utterance.id,
      revision: utterance.revision,
      mode,
      status: utterance.status,
      sourceText: utterance.source.hypothesis,
      targetText: utterance.target.hypothesis,
      targetDelta: delta || "",
      confidence: utterance.target.confidence,
      playbackState: utterance.playback.state,
      lastSpokenVersion: utterance.playback.lastSpokenVersion,
    };
    this._appendEvent(event);
    this._snapshotUtterance(utterance);
    return event;
  }

  collectArbitrationDecision(utteranceId, decision, systemState) {
    const event = {
      t: Date.now(),
      type: "arbitration-decision",
      utteranceId,
      action: decision.action,
      mode: decision.mode,
      reason: decision.reason,
      isMorph: Boolean(decision.isMorph),
      currentJob: Boolean(systemState.currentJob),
      currentConfidence: Number.isFinite(systemState.currentConfidence)
        ? systemState.currentConfidence
        : 0,
    };
    this._appendEvent(event);
    return event;
  }

  collectPlaybackEvent(event) {
    const record = {
      t: Date.now(),
      type: "playback-enqueued",
      utteranceId: event.utteranceId || event.phraseId,
      utteranceVersion: event.utteranceVersion || event.revision,
      mode: event.mode,
      text: event.text,
      confidence: Number.isFinite(event.confidence) ? event.confidence : 0,
      priority: Number.isFinite(event.priority) ? event.priority : 0,
      segmentId: event.segmentId,
      supersedesSegmentId: event.supersedesSegmentId,
    };
    this._appendEvent(record);
    return record;
  }

  collectPlaybackStart(utteranceId, version) {
    const event = {
      t: Date.now(),
      type: "playback-start",
      utteranceId,
      version,
    };
    this._appendEvent(event);
    return event;
  }

  collectPlaybackEnd(utteranceId, version, durationMs) {
    const event = {
      t: Date.now(),
      type: "playback-end",
      utteranceId,
      version,
      durationMs: Number.isFinite(durationMs) ? durationMs : 0,
    };
    this._appendEvent(event);
    return event;
  }

  collectLatencySpike(chunkNumber, latencyMs, threshold) {
    if (latencyMs <= threshold) {
      return null;
    }

    const event = {
      t: Date.now(),
      type: "latency-spike",
      chunkNumber,
      latencyMs,
      threshold,
      overage: latencyMs - threshold,
    };
    this._appendEvent(event);
    return event;
  }

  collectSilenceGap(reason, gapMs, expectedMaxMs) {
    if (gapMs <= expectedMaxMs) {
      return null;
    }

    const event = {
      t: Date.now(),
      type: "silence-gap",
      reason,
      gapMs,
      expectedMax: expectedMaxMs,
      excess: gapMs - expectedMaxMs,
    };
    this._appendEvent(event);
    return event;
  }

  collectAnomalouseState(issue) {
    const event = {
      t: Date.now(),
      type: "anomalous-state",
      issue: issue.issue || "unknown",
      severity: issue.severity || "low",
      context: issue.context || {},
    };
    this._appendEvent(event);
    return event;
  }

  pause() {
    this.isPaused = true;
    this.pausedAt = Date.now();
  }

  resume() {
    this.isPaused = false;
    this.pausedAt = null;
  }

  getRecentEvents(typeFilter = null, lastNMs = 30000) {
    const cutoff = Date.now() - lastNMs;
    return this.eventLog.filter((e) => {
      if (e.t < cutoff) return false;
      if (typeFilter && !Array.isArray(typeFilter)) return e.type === typeFilter;
      if (typeFilter && Array.isArray(typeFilter)) return typeFilter.includes(e.type);
      return true;
    });
  }

  getUtteranceTimeline(utteranceId) {
    return this.eventLog.filter((e) => e.utteranceId === utteranceId);
  }

  getUtteranceSnapshot(utteranceId) {
    return this.utteranceSnapshots.get(utteranceId);
  }

  getAllSnapshots() {
    return Array.from(this.utteranceSnapshots.values());
  }

  clear() {
    this.eventLog = [];
    this.utteranceSnapshots.clear();
  }

  exportLog(format = "json") {
    if (format === "json") {
      return JSON.stringify({
        exportedAt: Date.now(),
        events: this.eventLog,
        snapshots: Array.from(this.utteranceSnapshots.entries()),
      }, null, 2);
    }

    return this.eventLog.map((e) => JSON.stringify(e)).join("\n");
  }

  _appendEvent(event) {
    if (this.isPaused) {
      return;
    }

    this.eventLog.push(event);
    this._pruneOldEvents();
  }

  _snapshotUtterance(utterance) {
    if (!utterance || !utterance.id) {
      return;
    }

    this.utteranceSnapshots.set(utterance.id, {
      id: utterance.id,
      status: utterance.status,
      revision: utterance.revision,
      createdAt: utterance.createdAt,
      lastUpdateAt: utterance.lastUpdateAt,
      source: { ...utterance.source },
      target: { ...utterance.target },
      playback: { ...utterance.playback },
      continuityScore: utterance.continuityScore,
      timeline: utterance.timeline.map((e) => ({ ...e })),
    });
  }

  _pruneOldEvents() {
    const cutoff = Date.now() - this.maxHistoryMs;
    this.eventLog = this.eventLog.filter((e) => e.t > cutoff);
  }
}

module.exports = {
  EventCollector,
};
