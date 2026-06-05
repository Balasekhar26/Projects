class AnomalyDetector {
  constructor(options = {}) {
    this.options = {
      latencyThresholdMs: Number.isFinite(options.latencyThresholdMs)
        ? options.latencyThresholdMs
        : 250,
      silenceThresholdMs: Number.isFinite(options.silenceThresholdMs)
        ? options.silenceThresholdMs
        : 500,
      revisionOscillationWindow: Number.isFinite(options.revisionOscillationWindow)
        ? options.revisionOscillationWindow
        : 1000,
      confidenceDropThreshold: Number.isFinite(options.confidenceDropThreshold)
        ? options.confidenceDropThreshold
        : 0.15,
      minEventsForAnalysis: Number.isFinite(options.minEventsForAnalysis)
        ? options.minEventsForAnalysis
        : 10,
    };
  }

  analyzeLog(eventLog, utteranceSnapshots) {
    if (!eventLog || eventLog.length < this.options.minEventsForAnalysis) {
      return { issues: [], score: 100 };
    }

    const issues = [];

    issues.push(...this._detectRevisionOscillation(eventLog));
    issues.push(...this._detectLatencySpikes(eventLog));
    issues.push(...this._detectSilenceGaps(eventLog));
    issues.push(...this._detectConfidenceDrops(eventLog));
    issues.push(...this._detectVersionStarvation(eventLog, utteranceSnapshots));
    issues.push(...this._detectPlaybackMisalignment(eventLog));
    issues.push(...this._detectArbitrationBlocking(eventLog));

    const score = Math.max(0, 100 - issues.length * 5 - this._computeSeverityPenalty(issues));
    return { issues, score };
  }

  _detectRevisionOscillation(eventLog) {
    const issues = [];
    const utterances = new Map();

    for (const event of eventLog) {
      if (event.type !== "utterance-updated") continue;

      if (!utterances.has(event.utteranceId)) {
        utterances.set(event.utteranceId, []);
      }
      utterances.get(event.utteranceId).push(event);
    }

    for (const [utteranceId, updates] of utterances) {
      if (updates.length < 3) continue;

      const recentWindow = updates.filter((u) => Date.now() - u.t < this.options.revisionOscillationWindow);
      if (recentWindow.length < 3) continue;

      const revisions = new Set(recentWindow.map((u) => u.revision));
      if (revisions.size >= recentWindow.length * 0.6) {
        issues.push({
          type: "revision-oscillation",
          severity: "high",
          utteranceId,
          oscillationCount: revisions.size,
          windowMs: this.options.revisionOscillationWindow,
          rootCauseHypothesis:
            "translation confidence unstable or threshold too sensitive",
          suggestedFix: {
            parameter: "realtimeUtteranceSimilarityThreshold",
            direction: "increase",
            reason: "reduce sensitivity to minor translation variations",
          },
        });
      }
    }

    return issues;
  }

  _detectLatencySpikes(eventLog) {
    const issues = [];
    const spikeGroups = [];
    let currentSpike = null;

    for (const event of eventLog) {
      if (event.type !== "latency-spike") continue;

      if (!currentSpike || event.t - currentSpike[currentSpike.length - 1].t > 3000) {
        if (currentSpike && currentSpike.length >= 2) {
          spikeGroups.push(currentSpike);
        }
        currentSpike = [event];
      } else {
        currentSpike.push(event);
      }
    }
    if (currentSpike && currentSpike.length >= 2) {
      spikeGroups.push(currentSpike);
    }

    for (const group of spikeGroups) {
      const avgOverage = group.reduce((sum, e) => sum + (e.overage || 0), 0) / group.length;
      issues.push({
        type: "latency-spike-cluster",
        severity: avgOverage > 100 ? "high" : "medium",
        spikeCount: group.length,
        avgOverageMs: Math.round(avgOverage),
        thresholdMs: group[0].threshold,
        rootCauseHypothesis:
          "STT, translation, or TTS backend slower than configured expectations",
        suggestedFix: {
          parameter: "realtimeTargetLatencyMs",
          direction: "increase",
          reason: "give pipeline more time to process without overloading queue",
        },
      });
    }

    return issues;
  }

  _detectSilenceGaps(eventLog) {
    const issues = [];
    const gapEvents = eventLog.filter((e) => e.type === "silence-gap");

    if (gapEvents.length === 0) {
      return issues;
    }

    const avgExcess = gapEvents.reduce((sum, e) => sum + (e.excess || 0), 0) / gapEvents.length;
    if (avgExcess > 150) {
      issues.push({
        type: "silence-gaps",
        severity: "medium",
        gapCount: gapEvents.length,
        avgExcessMs: Math.round(avgExcess),
        rootCauseHypothesis:
          "continuation layer not triggering or playback delay too high",
        suggestedFix: {
          parameter: "continuationDelayMs",
          direction: "decrease",
          reason: "reduce delay before presence/continuation playback",
        },
      });
    }

    return issues;
  }

  _detectConfidenceDrops(eventLog) {
    const issues = [];
    const confidenceEvents = eventLog
      .filter((e) => e.type === "stt-chunk" && Number.isFinite(e.confidence))
      .sort((a, b) => a.t - b.t);

    for (let i = 1; i < confidenceEvents.length; i++) {
      const drop = confidenceEvents[i - 1].confidence - confidenceEvents[i].confidence;
      if (drop > this.options.confidenceDropThreshold) {
        issues.push({
          type: "confidence-drop",
          severity: drop > 0.3 ? "medium" : "low",
          dropAmount: drop.toFixed(3),
          from: confidenceEvents[i - 1].confidence.toFixed(3),
          to: confidenceEvents[i].confidence.toFixed(3),
          rootCauseHypothesis:
            "STT backend recognition quality degraded mid-utterance or audio quality dropped",
          suggestedFix: {
            parameter: "realtimeSpeechConfidenceThreshold",
            direction: "no-change",
            reason: "issue is external (audio quality); no config adjustment helps",
          },
        });
        break;
      }
    }

    return issues;
  }

  _detectVersionStarvation(eventLog, utteranceSnapshots) {
    const issues = [];

    if (!utteranceSnapshots || utteranceSnapshots.size === 0) {
      return issues;
    }

    for (const [utteranceId, snapshot] of utteranceSnapshots) {
      const updates = eventLog.filter((e) => e.utteranceId === utteranceId && e.type === "utterance-updated");
      if (updates.length < 5) continue;

      const timeBetweenUpdates = [];
      for (let i = 1; i < updates.length; i++) {
        timeBetweenUpdates.push(updates[i].t - updates[i - 1].t);
      }

      const avgInterval = timeBetweenUpdates.reduce((a, b) => a + b, 0) / timeBetweenUpdates.length;
      const lastUpdate = updates[updates.length - 1];
      if (
        snapshot.status !== "committed" &&
        snapshot.playback.state !== "speaking" &&
        Date.now() - lastUpdate.t > 800
      ) {
        issues.push({
          type: "version-starvation",
          severity: "medium",
          utteranceId,
          revision: snapshot.revision,
          lastUpdateAgeMsMs: Date.now() - lastUpdate.t,
          rootCauseHypothesis:
            "utterance still forming but no meaningful progress; may be waiting forever",
          suggestedFix: {
            parameter: "realtimeForceCommitMs",
            direction: "decrease",
            reason: "force commit older utterances to prevent indefinite waiting",
          },
        });
      }
    }

    return issues;
  }

  _detectPlaybackMisalignment(eventLog) {
    const issues = [];
    const arbitrations = eventLog.filter((e) => e.type === "arbitration-decision");

    const blocked = arbitrations.filter((a) => a.action !== "speak");
    if (arbitrations.length > 5 && blocked.length / arbitrations.length > 0.5) {
      issues.push({
        type: "playback-blocked-excessively",
        severity: "medium",
        blockedCount: blocked.length,
        totalCount: arbitrations.length,
        blockRatio: (blocked.length / arbitrations.length).toFixed(2),
        rootCauseHypothesis:
          "arbitration too conservative; utterances waiting for stability that may never come",
        suggestedFix: {
          parameter: "stabilityWindowMs",
          direction: "decrease",
          reason: "reduce stability window to allow earlier playback",
        },
      });
    }

    return issues;
  }

  _detectArbitrationBlocking(eventLog) {
    const issues = [];
    const decisions = eventLog.filter((e) => e.type === "arbitration-decision");

    if (decisions.length === 0) {
      return issues;
    }

    const blockReasons = {};
    for (const decision of decisions) {
      if (decision.action !== "speak") {
        blockReasons[decision.reason] = (blockReasons[decision.reason] || 0) + 1;
      }
    }

    if (blockReasons["waiting-for-stability"] && blockReasons["waiting-for-stability"] > decisions.length * 0.4) {
      issues.push({
        type: "stability-gate-too-strict",
        severity: "medium",
        blockedCount: blockReasons["waiting-for-stability"],
        totalDecisions: decisions.length,
        rootCauseHypothesis: "utterance confidence or age conditions never met for speech",
        suggestedFix: {
          parameter: "minimumConfidenceToSpeak",
          direction: "decrease",
          reason: "lower confidence threshold to unblock playback",
        },
      });
    }

    return issues;
  }

  _computeSeverityPenalty(issues) {
    let penalty = 0;
    for (const issue of issues) {
      if (issue.severity === "high") penalty += 20;
      else if (issue.severity === "medium") penalty += 10;
      else penalty += 3;
    }
    return penalty;
  }
}

module.exports = {
  AnomalyDetector,
};
