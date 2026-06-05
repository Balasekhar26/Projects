class SystemDoctor {
  constructor() {
    this.recordedLogs = [];
    this.simulationResults = [];
  }

  recordSession(eventLog, utteranceSnapshots, systemConfig) {
    const recording = {
      id: `rec-${Date.now()}`,
      recordedAt: Date.now(),
      eventLog: JSON.parse(JSON.stringify(eventLog)),
      utteranceSnapshots: JSON.parse(JSON.stringify(Array.from(utteranceSnapshots.entries()))),
      systemConfig: JSON.parse(JSON.stringify(systemConfig)),
    };
    this.recordedLogs.push(recording);
    return recording.id;
  }

  simulateParameterChange(recordingId, parameterName, newValue) {
    const recording = this.recordedLogs.find((r) => r.id === recordingId);
    if (!recording) {
      return { success: false, error: "Recording not found" };
    }

    const simulationId = `sim-${Date.now()}-${Math.random().toString(16).slice(2, 8)}`;
    const result = {
      id: simulationId,
      recordingId,
      simulatedAt: Date.now(),
      parameter: parameterName,
      originalValue: recording.systemConfig[parameterName],
      newValue,
      predictions: [],
      riskAssessment: null,
    };

    result.predictions = this._predictiveAnalysis(
      recording.eventLog,
      recording.utteranceSnapshots,
      parameterName,
      newValue,
      recording.systemConfig
    );

    result.riskAssessment = this._assessRisks(result.predictions, parameterName);

    this.simulationResults.push(result);
    return result;
  }

  _predictiveAnalysis(eventLog, utteranceSnapshots, parameterName, newValue, currentConfig) {
    const predictions = [];

    if (parameterName === "stabilityWindowMs") {
      const latencySpikes = eventLog.filter((e) => e.type === "latency-spike");
      if (newValue < currentConfig.stabilityWindowMs) {
        predictions.push({
          aspect: "playback-latency",
          direction: "decrease",
          magnitude: "moderate",
          explanation: `Reducing stability window from ${currentConfig.stabilityWindowMs}ms to ${newValue}ms will allow speech to start earlier, but may increase revision mid-speech if updates keep arriving.`,
        });
      } else {
        predictions.push({
          aspect: "playback-delay",
          direction: "increase",
          magnitude: "moderate",
          explanation: `Increasing stability window will reduce revisions but may cause more noticeable silence before speech starts.`,
        });
      }
    }

    if (parameterName === "minimumConfidenceToSpeak") {
      const lowConfidenceEvents = eventLog.filter((e) => e.type === "stt-chunk" && e.confidence < newValue);
      const blockRatio = lowConfidenceEvents.length / eventLog.filter((e) => e.type === "stt-chunk").length;
      predictions.push({
        aspect: "speech-responsiveness",
        direction: newValue < currentConfig.minimumConfidenceToSpeak ? "increase" : "decrease",
        magnitude: blockRatio > 0.3 ? "high" : "moderate",
        explanation: `Setting confidence threshold to ${newValue.toFixed(2)} will affect ~${(blockRatio * 100).toFixed(0)}% of utterances based on recorded data.`,
      });
    }

    if (parameterName === "realtimeForceCommitMs") {
      const longUtterances = eventLog.filter((e) => e.type === "utterance-updated" && Date.now() - e.t > newValue);
      predictions.push({
        aspect: "utterance-finalization",
        direction: newValue < currentConfig.realtimeForceCommitMs ? "earlier" : "later",
        magnitude: "moderate",
        explanation: `Force commit threshold of ${newValue}ms will close ~${longUtterances.length} utterances sooner if applied retroactively.`,
      });
    }

    if (parameterName === "continuationDelayMs") {
      const silenceGaps = eventLog.filter((e) => e.type === "silence-gap");
      predictions.push({
        aspect: "silence-fill",
        direction: newValue < currentConfig.continuationDelayMs ? "faster" : "slower",
        magnitude: silenceGaps.length > 0 ? "high" : "low",
        explanation: `Continuation delay of ${newValue}ms will trigger presence playback ${newValue < currentConfig.continuationDelayMs ? "sooner" : "later"}. Recorded ${silenceGaps.length} gaps that might be affected.`,
      });
    }

    if (parameterName === "realtimeUtteranceSimilarityThreshold") {
      const oscillations = eventLog.filter((e) => e.type === "revision-oscillation");
      predictions.push({
        aspect: "revision-stability",
        direction: newValue > currentConfig.realtimeUtteranceSimilarityThreshold ? "increase" : "decrease",
        magnitude: oscillations.length > 0 ? "high" : "low",
        explanation: `Similarity threshold of ${newValue.toFixed(2)} ${newValue > currentConfig.realtimeUtteranceSimilarityThreshold ? "is more conservative" : "is more sensitive"}. Recorded ${oscillations.length} oscillation events.`,
      });
    }

    return predictions.length > 0 ? predictions : [{
      aspect: "unknown",
      direction: "neutral",
      magnitude: "low",
      explanation: "Parameter change prediction not available for this parameter.",
    }];
  }

  _assessRisks(predictions, parameterName) {
    let riskLevel = "low";
    let riskFactors = [];

    for (const pred of predictions) {
      if (pred.magnitude === "high" && ["revision-stability", "playback-latency", "utterance-finalization"].includes(pred.aspect)) {
        riskLevel = "medium";
        riskFactors.push(`High-magnitude change to ${pred.aspect}`);
      }
    }

    if (["stabilityWindowMs", "minimumConfidenceToSpeak"].includes(parameterName)) {
      riskFactors.push("Parameter directly affects arbitration gate; monitor jitter if applied");
    }

    return {
      level: riskLevel,
      factors: riskFactors,
      recommendation: riskLevel === "high"
        ? "Test on isolated session first before production deployment"
        : "Safe to apply; monitor metrics for 2-3 minutes after application",
    };
  }

  getSimulationResult(simulationId) {
    return this.simulationResults.find((r) => r.id === simulationId);
  }

  listRecordings() {
    return this.recordedLogs.map((r) => ({
      id: r.id,
      recordedAt: r.recordedAt,
      eventCount: r.eventLog.length,
      utteranceCount: r.utteranceSnapshots.length,
    }));
  }

  listSimulations() {
    return this.simulationResults.map((r) => ({
      id: r.id,
      recordingId: r.recordingId,
      parameter: r.parameter,
      originalValue: r.originalValue,
      newValue: r.newValue,
      riskLevel: r.riskAssessment.level,
    }));
  }

  exportSimulationReport(simulationId) {
    const result = this.getSimulationResult(simulationId);
    if (!result) {
      return "Simulation not found";
    }

    let report = `=== SYSTEM DOCTOR SIMULATION REPORT ===\n\n`;
    report += `Simulation ID: ${result.id}\n`;
    report += `Parameter: ${result.parameter}\n`;
    report += `Original Value: ${result.originalValue}\n`;
    report += `Proposed Value: ${result.newValue}\n`;
    report += `Simulated At: ${new Date(result.simulatedAt).toISOString()}\n\n`;

    report += `=== PREDICTIONS ===\n`;
    for (const pred of result.predictions) {
      report += `\nAspect: ${pred.aspect}\n`;
      report += `Direction: ${pred.direction} (${pred.magnitude} impact)\n`;
      report += `Expected: ${pred.explanation}\n`;
    }

    report += `\n=== RISK ASSESSMENT ===\n`;
    report += `Risk Level: ${result.riskAssessment.level}\n`;
    report += `Risk Factors:\n`;
    for (const factor of result.riskAssessment.factors) {
      report += `  - ${factor}\n`;
    }
    report += `\nRecommendation: ${result.riskAssessment.recommendation}\n`;

    return report;
  }
}

module.exports = {
  SystemDoctor,
};
