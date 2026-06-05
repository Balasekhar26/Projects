/**
 * Deterministic Replay Harness
 *
 * Purpose: Replay recorded event streams under a deterministic clock and
 * fail fast when causal outputs diverge from the recorded baseline.
 */

const { EventTimeNormalizer } = require("./event-time-normalizer");
const { AnomalyDetector } = require("./anomaly-detector");

class DeterministicReplayHarness {
  constructor(options = {}) {
    this.options = {
      diagnosticMode: options.diagnosticMode || false,
      strict: options.strict !== false,
      timingToleranceMs: Number.isFinite(options.timingToleranceMs)
        ? options.timingToleranceMs
        : 20,
      determinismToleranceMs: Number.isFinite(options.determinismToleranceMs)
        ? options.determinismToleranceMs
        : 5,
      ...(options || {}),
    };

    this.anomalyDetector = new AnomalyDetector(options);
    this.recordings = new Map();
    this.replayResults = [];
    this.recordingCounter = 0;
    this.replayCounter = 0;
  }

  recordSession(sessionId, events, utteranceSnapshots, systemState, options = {}) {
    const canonicalRawEvents = this._canonicalizeEvents(events, sessionId, options);
    const finalSessionId = sessionId || `rec-${String(++this.recordingCounter).padStart(4, "0")}`;
    const sessionOrigin = this._resolveSessionOrigin(canonicalRawEvents);
    const randomSeed = options.randomSeed ?? 0;
    const normalizationProfile = options.normalizationProfile || "replay";
    const quotaModel = options.quotaModel || "recorded";

    const timeNormalizer = this._createNormalizer(sessionOrigin);
    const normalizedEvents = canonicalRawEvents.map((event) =>
      timeNormalizer.normalizeEvent(event, {
        sessionId: finalSessionId,
        sequence: event.sequence,
        normalizationMode: event.normalizationMode || normalizationProfile,
        systemTime: event.t,
        streamTime: event.streamTime,
        utteranceTime: event.utteranceTime,
        observerTime: event.observerTime,
        quotaTime: event.quotaTime,
        confidences: event.timeConfidences,
      })
    );

    const normalizedSnapshots = this._normalizeSnapshots(utteranceSnapshots);
    const baselineAnalysis = this._runDeterministicAnalysis(
      normalizedEvents,
      normalizedSnapshots,
      sessionOrigin
    );

    const recording = {
      id: finalSessionId,
      recordedAt: sessionOrigin,
      eventCount: normalizedEvents.length,
      sessionOrigin,
      rawEvents: canonicalRawEvents,
      events: normalizedEvents,
      utteranceSnapshots: normalizedSnapshots,
      systemState: this._clone(systemState || {}),
      configSnapshot: this._clone(options.configSnapshot || {}),
      randomSeed,
      normalizationProfile,
      quotaModel,
      coherenceReport: timeNormalizer.getCoherenceReport(),
      baselineAnalysis,
      expectations: this._extractDeterministicExpectations(
        normalizedEvents,
        normalizedSnapshots,
        baselineAnalysis
      ),
    };

    this.recordings.set(finalSessionId, recording);
    return finalSessionId;
  }

  replaySession(sessionId, options = {}) {
    const recording = this.recordings.get(sessionId);
    if (!recording) {
      return {
        success: false,
        error: "Recording not found",
        sessionId,
      };
    }

    const timeNormalizer = this._createNormalizer(recording.sessionOrigin);
    const replayedEvents = recording.rawEvents.map((event) =>
      timeNormalizer.normalizeEvent(event, {
        sessionId: recording.id,
        sequence: event.sequence,
        normalizationMode: event.normalizationMode || recording.normalizationProfile,
        systemTime: event.t,
        streamTime: event.streamTime,
        utteranceTime: event.utteranceTime,
        observerTime: event.observerTime,
        quotaTime: event.quotaTime,
        confidences: event.timeConfidences,
      })
    );

    const analysis = this._runDeterministicAnalysis(
      replayedEvents,
      recording.utteranceSnapshots,
      recording.sessionOrigin
    );
    const timingDeterminism = timeNormalizer.validateDeterminism(recording.events, replayedEvents, {
      normalizedTimeTolerance: this.options.determinismToleranceMs,
    });
    const divergence = this.assertNoDivergence(recording, replayedEvents, analysis, options);

    if (!timingDeterminism.isDeterministic || !divergence.passed) {
      return {
        success: false,
        stopped: true,
        sessionId,
        error: "determinism-divergence",
        timingDeterminism,
        divergence,
      };
    }

    const replayResult = {
      success: true,
      replayId: `replay-${String(++this.replayCounter).padStart(4, "0")}`,
      sessionId,
      replayedAt: recording.sessionOrigin,
      durationMs: 0,
      eventCount: recording.eventCount,
      coherenceScore: recording.coherenceReport?.overallCoherence?.status,
      analysis,
      isHealthy: analysis.score >= 75,
      timingDeterminism,
      divergence,
    };

    this.replayResults.push(replayResult);
    return replayResult;
  }

  assertNoDivergence(recording, replayedEvents, analysis, options = {}) {
    const policy = {
      utteranceStructure: "STRICT",
      arbitrationDecision: "STRICT",
      playbackDecision: "STRICT",
      timingToleranceMs: Number.isFinite(options.timingToleranceMs)
        ? options.timingToleranceMs
        : this.options.timingToleranceMs,
      logs: "IGNORE",
    };

    const actualExpectations = this._extractDeterministicExpectations(
      replayedEvents,
      recording.utteranceSnapshots,
      analysis
    );
    const mismatches = [
      ...this._compareStrictArrays(
        "utterance-structure",
        recording.expectations.utteranceStructure,
        actualExpectations.utteranceStructure
      ),
      ...this._compareStrictArrays(
        "arbitration-decisions",
        recording.expectations.arbitrationDecisions,
        actualExpectations.arbitrationDecisions
      ),
      ...this._compareTimedArrays(
        "playback-decisions",
        recording.expectations.playbackDecisions,
        actualExpectations.playbackDecisions,
        policy.timingToleranceMs
      ),
      ...this._compareStrictArrays(
        "anomalies",
        recording.expectations.anomalySignature,
        actualExpectations.anomalySignature
      ),
    ];

    return {
      passed: mismatches.length === 0,
      policy,
      mismatchCount: mismatches.length,
      mismatches: mismatches.slice(0, 10),
    };
  }

  compareReplays(replayId1, replayId2) {
    const replay1 = this.replayResults.find((result) => result.replayId === replayId1);
    const replay2 = this.replayResults.find((result) => result.replayId === replayId2);

    if (!replay1 || !replay2) {
      return { success: false, error: "One or both replays not found" };
    }

    return {
      replay1Id: replayId1,
      replay2Id: replayId2,
      sameSession: replay1.sessionId === replay2.sessionId,
      scoreDelta: replay1.analysis.score - replay2.analysis.score,
      issueCountDelta: replay1.analysis.issues.length - replay2.analysis.issues.length,
      issueTypeMatches: this._compareIssueLists(replay1.analysis.issues, replay2.analysis.issues),
      deterministic:
        replay1.divergence?.passed === true &&
        replay2.divergence?.passed === true &&
        replay1.timingDeterminism?.isDeterministic === true &&
        replay2.timingDeterminism?.isDeterministic === true,
    };
  }

  validateReplayDeterminism(sessionId, replays = 3) {
    const recording = this.recordings.get(sessionId);
    if (!recording) {
      return { success: false, error: "Session not found" };
    }

    const replayIds = [];
    const replayResults = [];

    for (let i = 0; i < replays; i++) {
      const result = this.replaySession(sessionId);
      if (result.success === false) {
        return {
          success: false,
          error: result.error,
          stoppedAtReplay: i + 1,
          timingDeterminism: result.timingDeterminism,
          divergence: result.divergence,
        };
      }

      replayIds.push(result.replayId);
      replayResults.push(result);
    }

    const isDeterministic = this._checkReplayDeterminism(replayResults);
    const issueConsistency = this._assessIssueConsistency(replayResults);

    return {
      success: true,
      sessionId,
      replayCount: replays,
      replayIds,
      isDeterministic,
      healthScoreVariance: this._computeVariance(replayResults.map((result) => result.analysis.score)),
      issueCountVariance: this._computeVariance(
        replayResults.map((result) => result.analysis.issues.length)
      ),
      issueTypeConsistency: issueConsistency,
      verdict: isDeterministic
        ? "DETERMINISTIC: Replay output matched baseline on every run"
        : "NON-DETERMINISTIC: Replay output diverged from baseline",
    };
  }

  analyzeTimingCoherence(sessionId) {
    const recording = this.recordings.get(sessionId);
    if (!recording) {
      return { success: false, error: "Session not found" };
    }

    return {
      sessionId,
      recordedAt: recording.recordedAt,
      eventCount: recording.eventCount,
      coherenceReport: recording.coherenceReport,
      eventTimingBreakdown: this._analyzeEventTiming(recording.events),
      riskAssessment: this._assessTimingRisks(recording),
    };
  }

  exportReplayReport(replayId) {
    const replay = this.replayResults.find((result) => result.replayId === replayId);
    if (!replay) {
      return "Replay not found";
    }

    let report = "=== DETERMINISTIC REPLAY REPORT ===\n\n";
    report += `Replay ID: ${replay.replayId}\n`;
    report += `Session ID: ${replay.sessionId}\n`;
    report += `Events Processed: ${replay.eventCount}\n`;
    report += `Timing Coherence: ${replay.coherenceScore}\n`;
    report += `Deterministic: ${replay.timingDeterminism.isDeterministic ? "Yes" : "No"}\n`;
    report += `Divergence Free: ${replay.divergence.passed ? "Yes" : "No"}\n\n`;
    report += `Health Score: ${replay.analysis.score}/100\n`;
    report += `Issue Count: ${replay.analysis.issues.length}\n`;

    if (replay.divergence.mismatches.length > 0) {
      report += "\nMismatches:\n";
      for (const mismatch of replay.divergence.mismatches) {
        report += `  - ${mismatch.category} @ ${mismatch.index}: ${mismatch.reason}\n`;
      }
    }

    return report;
  }

  listSessions() {
    return Array.from(this.recordings.values()).map((recording) => ({
      id: recording.id,
      recordedAt: recording.recordedAt,
      eventCount: recording.eventCount,
      coherence: recording.coherenceReport?.overallCoherence?.status,
    }));
  }

  listReplays() {
    return this.replayResults.map((result) => ({
      id: result.replayId,
      sessionId: result.sessionId,
      durationMs: result.durationMs,
      healthScore: result.analysis.score,
      replayedAt: result.replayedAt,
      deterministic: result.timingDeterminism?.isDeterministic === true,
      divergenceFree: result.divergence?.passed === true,
    }));
  }

  _canonicalizeEvents(events = [], sessionId) {
    const baseTime = this._guessBaseTime(events);

    return (events || []).map((event, index) => {
      const systemTime = this._finite(
        event.t,
        event.systemTime,
        event.time?.systemTime,
        event.timing?.systemTime,
        baseTime + index
      );
      const streamTime = this._finite(
        event.streamTime,
        event.time?.streamTime,
        event.timing?.streamTime
      );
      const utteranceTime = this._finite(
        event.utteranceTime,
        event.time?.utteranceTime,
        event.timing?.utteranceTime
      );
      const observerTime = this._finite(
        event.observerTime,
        event.time?.observerTime,
        event.timing?.observerTime,
        systemTime
      );
      const quotaTime = this._canonicalizeQuotaTime(
        event.quotaTime || event.time?.quotaTime || event.timing?.quotaTime,
        systemTime
      );

      return {
        ...this._clone(event),
        id: event.id || `${sessionId || "session"}-evt-${index}`,
        sessionId: event.sessionId || sessionId || "default-session",
        sequence: event.sequence ?? index,
        t: systemTime,
        systemTime,
        streamTime,
        utteranceTime,
        observerTime,
        quotaTime,
        normalizationMode: event.normalizationMode || event.time?.normalizationMode,
        timeConfidences: {
          ...(event.timeConfidences || {}),
          ...(event.time?.confidences || {}),
          ...(event.timing?.confidences || {}),
        },
      };
    });
  }

  _normalizeSnapshots(utteranceSnapshots) {
    if (Array.isArray(utteranceSnapshots)) {
      return this._clone(utteranceSnapshots);
    }

    if (utteranceSnapshots?.values) {
      return Array.from(utteranceSnapshots.values()).map((snapshot) => this._clone(snapshot));
    }

    return [];
  }

  _createNormalizer(sessionOrigin) {
    return new EventTimeNormalizer({
      diagnosticMode: this.options.diagnosticMode,
      defaultMode: "observer",
      sessionOrigin,
    });
  }

  _runDeterministicAnalysis(events, utteranceSnapshots, sessionOrigin) {
    const snapshotMap = new Map(
      utteranceSnapshots.map((snapshot) => [snapshot.id, snapshot])
    );
    const deterministicNow = this._deriveDeterministicNow(events, sessionOrigin);

    return this._withDeterministicClock(deterministicNow, () =>
      this.anomalyDetector.analyzeLog(events, snapshotMap)
    );
  }

  _deriveDeterministicNow(events, sessionOrigin) {
    const latestSystemTime = events.reduce((max, event) => {
      return Math.max(max, this._finite(event.timing?.systemTime, event.t, sessionOrigin));
    }, sessionOrigin || 0);

    return latestSystemTime + 1000;
  }

  _withDeterministicClock(fixedNow, callback) {
    const originalNow = Date.now;
    Date.now = () => fixedNow;

    try {
      return callback();
    } finally {
      Date.now = originalNow;
    }
  }

  _extractDeterministicExpectations(events, utteranceSnapshots, analysis) {
    const utteranceStructure = [
      ...utteranceSnapshots.map((snapshot) => ({
        id: snapshot.id,
        revision: snapshot.revision,
        status: snapshot.status,
      })),
      ...events
        .filter((event) => event.type?.startsWith("utterance"))
        .map((event) => ({
          id: event.utteranceId || event.lineageId || event.id,
          revision: event.revision ?? null,
          status: event.mode || event.status || null,
        })),
    ];

    const arbitrationDecisions = events
      .filter((event) => event.type === "arbitration-decision")
      .map((event) => ({
        utteranceId: event.utteranceId || null,
        action: event.action || event.decision || null,
        normalizedTime: event.timing?.normalizedTime ?? null,
      }));

    const playbackDecisions = events
      .filter((event) => event.type?.includes("playback") || event.type?.startsWith("tts_"))
      .map((event) => ({
        type: event.type,
        utteranceId: event.utteranceId || null,
        normalizedTime: event.timing?.normalizedTime ?? null,
      }));

    const anomalySignature = (analysis?.issues || []).map((issue) => ({
      type: issue.type,
      severity: issue.severity,
    }));

    return {
      utteranceStructure: this._stableSort(utteranceStructure),
      arbitrationDecisions: this._stableSort(arbitrationDecisions),
      playbackDecisions: this._stableSort(playbackDecisions),
      anomalySignature: this._stableSort(anomalySignature),
    };
  }

  _compareStrictArrays(category, expected, actual) {
    const expectedValues = expected.map((value) => JSON.stringify(value));
    const actualValues = actual.map((value) => JSON.stringify(value));
    const maxLength = Math.max(expectedValues.length, actualValues.length);
    const mismatches = [];

    for (let index = 0; index < maxLength; index++) {
      if (expectedValues[index] === actualValues[index]) {
        continue;
      }

      mismatches.push({
        category,
        index,
        reason: "strict-mismatch",
        expected: expected[index],
        actual: actual[index],
      });
    }

    return mismatches;
  }

  _compareTimedArrays(category, expected, actual, toleranceMs) {
    const maxLength = Math.max(expected.length, actual.length);
    const mismatches = [];

    for (let index = 0; index < maxLength; index++) {
      const expectedItem = expected[index];
      const actualItem = actual[index];

      if (!expectedItem || !actualItem) {
        mismatches.push({
          category,
          index,
          reason: "count-mismatch",
          expected: expectedItem,
          actual: actualItem,
        });
        continue;
      }

      const stableShapeMatches =
        expectedItem.type === actualItem.type &&
        expectedItem.utteranceId === actualItem.utteranceId;
      const timingDrift = Math.abs(
        (expectedItem.normalizedTime || 0) - (actualItem.normalizedTime || 0)
      );

      if (!stableShapeMatches || timingDrift > toleranceMs) {
        mismatches.push({
          category,
          index,
          reason: !stableShapeMatches ? "structure-mismatch" : "timing-drift",
          driftMs: timingDrift,
          expected: expectedItem,
          actual: actualItem,
        });
      }
    }

    return mismatches;
  }

  _compareIssueLists(issues1, issues2) {
    const types1 = new Set((issues1 || []).map((issue) => issue.type || issue));
    const types2 = new Set((issues2 || []).map((issue) => issue.type || issue));
    const intersection = new Set([...types1].filter((value) => types2.has(value)));
    const union = new Set([...types1, ...types2]);

    return union.size === 0 ? "1.00" : (intersection.size / union.size).toFixed(2);
  }

  _checkReplayDeterminism(replayResults) {
    return replayResults.every(
      (result) =>
        result.success === true &&
        result.divergence?.passed === true &&
        result.timingDeterminism?.isDeterministic === true
    );
  }

  _computeVariance(values) {
    if (values.length === 0) return 0;

    const mean = values.reduce((sum, value) => sum + value, 0) / values.length;
    const variance =
      values.reduce((sum, value) => sum + Math.pow(value - mean, 2), 0) / values.length;

    return Math.sqrt(variance);
  }

  _assessIssueConsistency(replayResults) {
    const issueCounts = replayResults.map((result) => result.analysis.issues.length);
    const issueTypes = replayResults.map((result) => result.analysis.issues.map((issue) => issue.type));
    const countVariance = this._computeVariance(issueCounts);
    const typeConsistency = this._compareIssueLists(
      issueTypes[0] || [],
      issueTypes[issueTypes.length - 1] || []
    );

    return {
      countVariance: countVariance.toFixed(2),
      typeConsistency: parseFloat(typeConsistency),
      consistent: countVariance === 0 && parseFloat(typeConsistency) === 1,
    };
  }

  _analyzeEventTiming(events) {
    const sttEvents = events.filter((event) => event.type === "stt-chunk");
    const utteranceEvents = events.filter((event) => event.type?.includes("utterance"));
    const playbackEvents = events.filter((event) => event.type?.includes("playback"));

    return {
      sttChunkCount: sttEvents.length,
      utteranceEventCount: utteranceEvents.length,
      playbackEventCount: playbackEvents.length,
      timespan:
        events.length > 0
          ? (events[events.length - 1].timing?.normalizedTime || 0) -
            (events[0].timing?.normalizedTime || 0)
          : 0,
    };
  }

  _assessTimingRisks(recording) {
    const coherence = recording.coherenceReport?.overallCoherence;
    let riskLevel = "low";
    const riskFactors = [];

    if (coherence?.status === "warning") {
      riskLevel = "high";
      riskFactors.push("System exhibits significant timing misalignment across domains");
    } else if (coherence?.status === "good") {
      riskLevel = "medium";
      riskFactors.push("Minor timing drift detected; observer may have blind spots");
    }

    if (parseFloat(coherence?.maxDeviation || 0) > 150) {
      riskFactors.push("Some events have high timing deviation (>150ms)");
    }

    return {
      level: riskLevel,
      factors: riskFactors,
      recommendation:
        riskLevel === "high"
          ? "Review event clock injection before trusting observer output"
          : "System timing appears healthy; replay should be trustworthy",
    };
  }

  _resolveSessionOrigin(events) {
    const times = events
      .map((event) => this._finite(event.t, event.observerTime))
      .filter((value) => Number.isFinite(value));

    return times.length > 0 ? Math.min(...times) : Date.now();
  }

  _guessBaseTime(events) {
    const explicitTimes = (events || [])
      .map((event) => this._finite(event.t, event.systemTime, event.time?.systemTime))
      .filter((value) => Number.isFinite(value));

    return explicitTimes.length > 0 ? Math.min(...explicitTimes) : Date.now();
  }

  _canonicalizeQuotaTime(quotaTime, systemTime) {
    if (!quotaTime) {
      return undefined;
    }

    if (Number.isFinite(quotaTime)) {
      return quotaTime;
    }

    return {
      ...quotaTime,
      readyAt: this._finite(
        quotaTime.readyAt,
        Number.isFinite(quotaTime.delayMs) ? systemTime + quotaTime.delayMs : undefined
      ),
    };
  }

  _finite(...values) {
    for (const value of values) {
      if (Number.isFinite(value)) {
        return value;
      }
    }
    return undefined;
  }

  _stableSort(values) {
    return values
      .map((value, index) => ({ value, index }))
      .sort((left, right) => {
        const leftSerialized = JSON.stringify(left.value);
        const rightSerialized = JSON.stringify(right.value);
        if (leftSerialized < rightSerialized) return -1;
        if (leftSerialized > rightSerialized) return 1;
        return left.index - right.index;
      })
      .map((entry) => entry.value);
  }

  _clone(value) {
    return JSON.parse(JSON.stringify(value));
  }
}

module.exports = {
  DeterministicReplayHarness,
};
