/**
 * Event Time Normalization Layer
 *
 * Purpose: Align system, stream, utterance, observer, and quota time onto
 * a single decision axis that can be used for observer analysis and replay.
 */

class EventTimeNormalizer {
  constructor(options = {}) {
    this.diagnosticMode = options.diagnosticMode || false;
    this.now = typeof options.now === "function" ? options.now : () => Date.now();
    this.defaultMode = options.defaultMode || "observer";
    this.modeProfiles = {
      capture: { stream: 0.55, utterance: 0.1, system: 0.2, observer: 0.1, quota: 0.05 },
      utterance: { stream: 0.2, utterance: 0.45, system: 0.2, observer: 0.1, quota: 0.05 },
      observer: { stream: 0.2, utterance: 0.2, system: 0.15, observer: 0.35, quota: 0.1 },
      "quota-constrained": { stream: 0.2, utterance: 0.2, system: 0.15, observer: 0.1, quota: 0.35 },
      replay: { stream: 0.35, utterance: 0.3, system: 0.15, observer: 0.1, quota: 0.1 },
      ...(options.modeProfiles || {}),
    };

    this.reset(options.sessionOrigin);
  }

  normalizeEvent(rawEvent, metadata = {}) {
    const sequenceNumber = metadata.sequence ?? rawEvent.sequence ?? this.eventSequence++;
    const eventId = rawEvent.id || `evt-${sequenceNumber}`;
    const normalizedMode = this._resolveNormalizationMode(rawEvent, metadata);
    const extracted = this._extractDomains(rawEvent, metadata);
    const sessionId = metadata.sessionId || rawEvent.sessionId || "default-session";
    const lineageId = rawEvent.lineageId || rawEvent.utteranceId || metadata.lineageId;
    const eventSource = metadata.source || rawEvent.source || rawEvent.type || "unknown";
    const causalityKey = this._buildCausalityKey(rawEvent, {
      eventId,
      sessionId,
      lineageId,
      sequenceNumber,
    });

    this._initializeOrigins(extracted.domainTimes);

    const rebasedTimes = this._rebaseDomains(extracted.domainTimes);
    const normalizedComputation = this._computeNormalizedTime(
      rebasedTimes,
      extracted.confidences,
      normalizedMode
    );
    const skewData = this._computeSkewData(extracted.domainTimes);
    const coherenceScore = this._computeCoherence(rebasedTimes, extracted.confidences);

    this._recordSkewStats(skewData, normalizedComputation.domainContributions.length);

    const timing = {
      systemTime: extracted.domainTimes.system,
      streamTime: extracted.domainTimes.stream,
      utteranceTime: extracted.domainTimes.utterance,
      observerTime: extracted.domainTimes.observer,
      quotaTime: extracted.domainTimes.quota,
      normalizedTime: normalizedComputation.normalizedTime,
      normalizationMode: normalizedMode,
      normalizationWeights: normalizedComputation.normalizationWeights,
      coherenceScore,
      causalityKey,
      skew: skewData,
      confidences: extracted.confidences,
      normalizationTrace: {
        mode: normalizedMode,
        origins: { ...this.origins },
        denominator: normalizedComputation.denominator,
        contributingDomains: normalizedComputation.domainContributions,
        ignoredDomains: normalizedComputation.ignoredDomains,
      },
      rawTimes: extracted.domainTimes,
      rebasedTimes,
    };

    const normalizedEvent = {
      ...rawEvent,
      id: eventId,
      sessionId,
      lineageId,
      sequence: sequenceNumber,
      eventSequence: sequenceNumber,
      source: eventSource,
      time: timing,
      timing,
    };

    if (this.diagnosticMode && coherenceScore < 0.6) {
      this._logCoherenceWarning(normalizedEvent, coherenceScore);
    }

    return normalizedEvent;
  }

  normalizeEventBatch(events, metadata = {}) {
    return events.map((event, index) => {
      const eventMetadata = {
        ...metadata,
        sequence: metadata.sequences?.[index] ?? index,
        systemTime: metadata.systemTimes?.[index],
        streamTime: metadata.streamTimes?.[index],
        utteranceTime: metadata.utteranceTimes?.[index],
        observerTime: metadata.observerTimes?.[index],
        quotaTime: metadata.quotaTimes?.[index],
      };
      return this.normalizeEvent(event, eventMetadata);
    });
  }

  getCoherenceReport() {
    if (this.timingStats.systemToUtterance.length === 0) {
      return {
        status: "insufficient-data",
        message: "Not enough events recorded yet",
      };
    }

    const report = {
      totalEvents: this.eventSequence,
      systemToUtterance: this._analyzeSkewArray(this.timingStats.systemToUtterance),
      systemToObserver: this._analyzeSkewArray(this.timingStats.systemToObserver),
      utteranceToObserver: this._analyzeSkewArray(this.timingStats.utteranceToObserver),
      streamToSystem: this._analyzeSkewArray(this.timingStats.streamToSystem),
      contributionCount: this.timingStats.contributionCount,
    };

    const allSkews = [
      ...this.timingStats.systemToUtterance,
      ...this.timingStats.systemToObserver,
      ...this.timingStats.utteranceToObserver,
      ...this.timingStats.streamToSystem,
    ];

    const avgSkew = allSkews.reduce((a, b) => a + b, 0) / allSkews.length;
    const maxSkew = Math.max(...allSkews.map((value) => Math.abs(value)));

    report.overallCoherence = {
      averageSkewMs: avgSkew.toFixed(2),
      maxDeviation: maxSkew.toFixed(2),
      status: maxSkew < 50 ? "excellent" : maxSkew < 150 ? "good" : "warning",
    };

    return report;
  }

  validateDeterminism(eventLog1, eventLog2, options = {}) {
    if (eventLog1.length !== eventLog2.length) {
      return {
        isDeterministic: false,
        reason: "event-count-mismatch",
        log1Count: eventLog1.length,
        log2Count: eventLog2.length,
      };
    }

    const tolerance = {
      normalizedTimeTolerance: Number.isFinite(options.normalizedTimeTolerance)
        ? options.normalizedTimeTolerance
        : 5,
      coherenceScoreTolerance: Number.isFinite(options.coherenceScoreTolerance)
        ? options.coherenceScoreTolerance
        : 0.05,
    };

    const mismatches = [];

    for (let i = 0; i < eventLog1.length; i++) {
      const e1 = eventLog1[i];
      const e2 = eventLog2[i];

      if (e1.type !== e2.type) {
        mismatches.push({
          index: i,
          issue: "type-mismatch",
          log1Type: e1.type,
          log2Type: e2.type,
        });
        continue;
      }

      const normalizedTimeDiff = Math.abs(
        (e1.timing?.normalizedTime || 0) - (e2.timing?.normalizedTime || 0)
      );
      if (normalizedTimeDiff > tolerance.normalizedTimeTolerance) {
        mismatches.push({
          index: i,
          issue: "normalized-time-drift",
          log1Time: e1.timing?.normalizedTime,
          log2Time: e2.timing?.normalizedTime,
          drift: normalizedTimeDiff,
        });
      }

      const coherenceDiff = Math.abs(
        (e1.timing?.coherenceScore || 0) - (e2.timing?.coherenceScore || 0)
      );
      if (coherenceDiff > tolerance.coherenceScoreTolerance) {
        mismatches.push({
          index: i,
          issue: "coherence-divergence",
          log1Coherence: e1.timing?.coherenceScore,
          log2Coherence: e2.timing?.coherenceScore,
          diff: coherenceDiff,
        });
      }

      if ((e1.timing?.causalityKey || "") !== (e2.timing?.causalityKey || "")) {
        mismatches.push({
          index: i,
          issue: "causality-key-mismatch",
          log1CausalityKey: e1.timing?.causalityKey,
          log2CausalityKey: e2.timing?.causalityKey,
        });
      }
    }

    const isDeterministic = mismatches.length === 0;

    return {
      isDeterministic,
      mismatchCount: mismatches.length,
      mismatches: mismatches.slice(0, 10),
      determinismScore:
        eventLog1.length === 0
          ? "1.000"
          : ((eventLog1.length - mismatches.length) / eventLog1.length).toFixed(3),
    };
  }

  reset(sessionOrigin) {
    const now = this.now();

    this.origins = {
      system: Number.isFinite(sessionOrigin) ? sessionOrigin : null,
      stream: 0,
      utterance: 0,
      observer: Number.isFinite(sessionOrigin) ? sessionOrigin : null,
      quota: null,
    };
    this.eventSequence = 0;
    this.timingStats = {
      systemToUtterance: [],
      systemToObserver: [],
      utteranceToObserver: [],
      streamToSystem: [],
      contributionCount: 0,
    };
    this.lastResetAt = now;
  }

  _resolveNormalizationMode(rawEvent, metadata) {
    if (metadata.normalizationMode) {
      return metadata.normalizationMode;
    }

    if (rawEvent.time?.normalizationMode || rawEvent.timing?.normalizationMode) {
      return rawEvent.time?.normalizationMode || rawEvent.timing?.normalizationMode;
    }

    if (rawEvent.type === "stt-chunk" || rawEvent.type === "playback-start") {
      return "capture";
    }

    if (rawEvent.type?.startsWith("utterance")) {
      return "utterance";
    }

    if (rawEvent.type === "quota-pressure") {
      return "quota-constrained";
    }

    return this.defaultMode;
  }

  _extractDomains(rawEvent, metadata) {
    const fallbackSystemTime = metadata.systemTime ?? rawEvent.t ?? rawEvent.systemTime ?? this.now();
    const domainTimes = {
      system: this._toFiniteNumber(
        metadata.systemTime,
        rawEvent.time?.systemTime,
        rawEvent.timing?.systemTime,
        rawEvent.systemTime,
        rawEvent.t
      ),
      stream: this._toFiniteNumber(
        metadata.streamTime,
        rawEvent.time?.streamTime,
        rawEvent.timing?.streamTime,
        rawEvent.streamTime,
        rawEvent.streamTimestamp,
        rawEvent.audioOffsetMs
      ),
      utterance: this._toFiniteNumber(
        metadata.utteranceTime,
        rawEvent.time?.utteranceTime,
        rawEvent.timing?.utteranceTime,
        rawEvent.utteranceTime
      ),
      observer: this._toFiniteNumber(
        metadata.observerTime,
        rawEvent.time?.observerTime,
        rawEvent.timing?.observerTime,
        rawEvent.observerTime
      ),
      quota: this._extractQuotaTime(
        metadata.quotaTime,
        rawEvent.time?.quotaTime,
        rawEvent.timing?.quotaTime,
        rawEvent.quotaTime,
        fallbackSystemTime
      ),
    };

    if (!Number.isFinite(domainTimes.system)) {
      domainTimes.system = fallbackSystemTime;
    }
    if (!Number.isFinite(domainTimes.observer)) {
      domainTimes.observer = domainTimes.system;
    }
    if (!Number.isFinite(domainTimes.utterance) && rawEvent.type?.startsWith("utterance")) {
      domainTimes.utterance = domainTimes.system;
    }

    return {
      domainTimes,
      confidences: this._extractConfidences(rawEvent, metadata, domainTimes),
    };
  }

  _extractConfidences(rawEvent, metadata, domainTimes) {
    const explicit = metadata.confidences || rawEvent.time?.confidences || rawEvent.timing?.confidences || {};
    const eventConfidence = this._clampConfidence(
      metadata.confidence,
      rawEvent.confidence,
      rawEvent.payload?.confidence
    );
    const stabilityConfidence = rawEvent.isStable === true ? 1 : rawEvent.isStable === false ? 0.65 : null;
    const quotaConfidence =
      rawEvent.quotaTime?.confidence ??
      rawEvent.time?.quotaTime?.confidence ??
      rawEvent.timing?.quotaTime?.confidence ??
      metadata.quotaConfidence;

    return {
      system: this._clampConfidence(explicit.system, 1),
      stream: this._clampConfidence(
        explicit.stream,
        eventConfidence,
        Number.isFinite(domainTimes.stream) ? 1 : 0
      ),
      utterance: this._clampConfidence(
        explicit.utterance,
        stabilityConfidence,
        eventConfidence,
        Number.isFinite(domainTimes.utterance) ? 1 : 0
      ),
      observer: this._clampConfidence(explicit.observer, 1),
      quota: this._clampConfidence(
        explicit.quota,
        quotaConfidence,
        Number.isFinite(domainTimes.quota) ? 0.9 : 0
      ),
    };
  }

  _extractQuotaTime(...sources) {
    const fallbackSystemTime = sources[sources.length - 1];
    for (let i = 0; i < sources.length - 1; i++) {
      const source = sources[i];
      if (Number.isFinite(source)) {
        return source;
      }
      if (!source || typeof source !== "object") {
        continue;
      }
      if (Number.isFinite(source.readyAt)) {
        return source.readyAt;
      }
      if (Number.isFinite(source.delayMs)) {
        return source.readyAt || fallbackSystemTime + source.delayMs;
      }
    }
    return undefined;
  }

  _initializeOrigins(domainTimes) {
    for (const [domain, value] of Object.entries(domainTimes)) {
      if (!Number.isFinite(value)) {
        continue;
      }
      if (!Number.isFinite(this.origins[domain])) {
        this.origins[domain] = value;
      } else if (domain !== "stream" && domain !== "utterance") {
        this.origins[domain] = Math.min(this.origins[domain], value);
      }
    }
  }

  _rebaseDomains(domainTimes) {
    const rebased = {};

    for (const [domain, value] of Object.entries(domainTimes)) {
      if (!Number.isFinite(value)) {
        rebased[domain] = undefined;
        continue;
      }

      const origin = this.origins[domain];
      rebased[domain] = Number.isFinite(origin) ? value - origin : value;
    }

    return rebased;
  }

  _computeNormalizedTime(rebasedTimes, confidences, mode) {
    const profile = this.modeProfiles[mode] || this.modeProfiles[this.defaultMode];
    const domainOrder = ["stream", "utterance", "system", "observer", "quota"];
    const domainContributions = [];
    const ignoredDomains = [];

    let numerator = 0;
    let denominator = 0;

    for (const domain of domainOrder) {
      const time = rebasedTimes[domain];
      const baseWeight = profile[domain] || 0;
      const confidence = this._clampConfidence(confidences[domain], 0);
      const effectiveWeight = baseWeight * confidence;

      if (!Number.isFinite(time) || effectiveWeight <= 0) {
        ignoredDomains.push({
          domain,
          reason: !Number.isFinite(time) ? "missing-time" : "zero-effective-weight",
          baseWeight,
          confidence,
        });
        continue;
      }

      numerator += time * effectiveWeight;
      denominator += effectiveWeight;
      domainContributions.push({
        domain,
        rawTime: time,
        rebasedTime: time,
        baseWeight,
        confidence,
        effectiveWeight: Number(effectiveWeight.toFixed(6)),
      });
    }

    return {
      normalizedTime: denominator > 0 ? Math.round(numerator / denominator) : 0,
      denominator: Number(denominator.toFixed(6)),
      domainContributions,
      ignoredDomains,
      normalizationWeights: domainContributions.reduce((acc, domain) => {
        acc[domain.domain] = domain.effectiveWeight;
        return acc;
      }, { stream: 0, utterance: 0, system: 0, observer: 0, quota: 0 }),
    };
  }

  _computeCoherence(rebasedTimes, confidences) {
    const availableDomains = Object.entries(rebasedTimes).filter(([, value]) => Number.isFinite(value));
    if (availableDomains.length <= 1) {
      return 1;
    }

    const pairScores = [];
    const maxAcceptableSkew = 120;

    for (let i = 0; i < availableDomains.length; i++) {
      for (let j = i + 1; j < availableDomains.length; j++) {
        const [leftName, leftValue] = availableDomains[i];
        const [rightName, rightValue] = availableDomains[j];
        const skew = Math.abs(leftValue - rightValue);
        const rawScore = Math.max(0, 1 - skew / maxAcceptableSkew);
        const confidence = Math.min(
          this._clampConfidence(confidences[leftName], 1),
          this._clampConfidence(confidences[rightName], 1)
        );
        pairScores.push(rawScore * confidence);
      }
    }

    const coherenceScore = pairScores.reduce((sum, score) => sum + score, 0) / pairScores.length;
    return Math.min(1, Math.max(0, Number(coherenceScore.toFixed(3))));
  }

  _computeSkewData(domainTimes) {
    return {
      systemToUtterance: this._difference(domainTimes.utterance, domainTimes.system),
      systemToObserver: this._difference(domainTimes.observer, domainTimes.system),
      utteranceToObserver: this._difference(domainTimes.observer, domainTimes.utterance),
      streamToSystem: this._difference(domainTimes.stream, domainTimes.system),
    };
  }

  _recordSkewStats(skewData, contributionCount) {
    this.timingStats.contributionCount += contributionCount;

    this._pushIfFinite(this.timingStats.systemToUtterance, skewData.systemToUtterance);
    this._pushIfFinite(this.timingStats.systemToObserver, skewData.systemToObserver);
    this._pushIfFinite(this.timingStats.utteranceToObserver, skewData.utteranceToObserver);
    this._pushIfFinite(this.timingStats.streamToSystem, skewData.streamToSystem);

    for (const key of ["systemToUtterance", "systemToObserver", "utteranceToObserver", "streamToSystem"]) {
      if (this.timingStats[key].length > 10000) {
        this.timingStats[key].shift();
      }
    }
  }

  _analyzeSkewArray(skewArray) {
    if (skewArray.length === 0) {
      return { count: 0, mean: 0, stddev: 0, min: 0, max: 0 };
    }

    const mean = skewArray.reduce((a, b) => a + b, 0) / skewArray.length;
    const variance =
      skewArray.reduce((sum, val) => sum + Math.pow(val - mean, 2), 0) / skewArray.length;
    const stddev = Math.sqrt(variance);

    return {
      count: skewArray.length,
      mean: mean.toFixed(2),
      stddev: stddev.toFixed(2),
      min: Math.min(...skewArray).toFixed(0),
      max: Math.max(...skewArray).toFixed(0),
    };
  }

  _buildCausalityKey(rawEvent, context) {
    return [
      context.sessionId,
      context.lineageId || rawEvent.utteranceId || "no-lineage",
      rawEvent.type || "unknown",
      context.sequenceNumber,
      context.eventId,
    ].join(":");
  }

  _logCoherenceWarning(event, score) {
    if (!this.diagnosticMode) return;

    console.warn(`Low coherence detected [score=${(score * 100).toFixed(0)}%]:`);
    console.warn(`   Event: ${event.type}`);
    console.warn(`   SystemTime: ${event.timing.systemTime}`);
    console.warn(`   StreamTime: ${event.timing.streamTime}`);
    console.warn(`   UtteranceTime: ${event.timing.utteranceTime}`);
    console.warn(`   ObserverTime: ${event.timing.observerTime}`);
    console.warn(`   NormalizedTime: ${event.timing.normalizedTime}`);
  }

  _toFiniteNumber(...values) {
    for (const value of values) {
      if (Number.isFinite(value)) {
        return value;
      }
    }
    return undefined;
  }

  _difference(left, right) {
    if (!Number.isFinite(left) || !Number.isFinite(right)) {
      return undefined;
    }
    return left - right;
  }

  _pushIfFinite(target, value) {
    if (Number.isFinite(value)) {
      target.push(value);
    }
  }

  _clampConfidence(...values) {
    for (const value of values) {
      if (Number.isFinite(value)) {
        return Math.min(1, Math.max(0, value));
      }
    }
    return 0;
  }
}

module.exports = {
  EventTimeNormalizer,
};
