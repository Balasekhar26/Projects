const { EventCollector } = require("./event-collector");
const { AnomalyDetector } = require("./anomaly-detector");
const { SuggestionEngine } = require("./suggestion-engine");
const { SystemDoctor } = require("./system-doctor");
const { EventTimeNormalizer } = require("./event-time-normalizer");
const { DeterministicReplayHarness } = require("./deterministic-replay-harness");

class AIObserver {
  constructor(options = {}) {
    this.eventCollector = new EventCollector({
      maxHistoryMinutes: options.maxHistoryMinutes || 5,
    });

    this.anomalyDetector = new AnomalyDetector({
      latencyThresholdMs: options.latencyThresholdMs || 250,
      silenceThresholdMs: options.silenceThresholdMs || 500,
      revisionOscillationWindow: options.revisionOscillationWindow || 1000,
    });

    this.suggestionEngine = new SuggestionEngine();
    this.systemDoctor = new SystemDoctor();

    this.analysisReport = null;
    this.lastAnalysisAt = 0;
    this.analysisIntervalMs = options.analysisIntervalMs || 10000;
  }

  ingestSttChunk(chunkInfo) {
    return this.eventCollector.collectSttChunk(chunkInfo);
  }

  ingestUtteranceSpawned(utterance) {
    return this.eventCollector.collectUtteranceSpawned(utterance);
  }

  ingestUtteranceUpdated(utterance, mode, delta) {
    return this.eventCollector.collectUtteranceUpdated(utterance, mode, delta);
  }

  ingestArbitrationDecision(utteranceId, decision, systemState) {
    return this.eventCollector.collectArbitrationDecision(utteranceId, decision, systemState);
  }

  ingestPlaybackEvent(event) {
    return this.eventCollector.collectPlaybackEvent(event);
  }

  ingestPlaybackStart(utteranceId, version) {
    return this.eventCollector.collectPlaybackStart(utteranceId, version);
  }

  ingestPlaybackEnd(utteranceId, version, durationMs) {
    return this.eventCollector.collectPlaybackEnd(utteranceId, version, durationMs);
  }

  ingestLatencySpike(chunkNumber, latencyMs, threshold) {
    return this.eventCollector.collectLatencySpike(chunkNumber, latencyMs, threshold);
  }

  ingestSilenceGap(reason, gapMs, expectedMaxMs) {
    return this.eventCollector.collectSilenceGap(reason, gapMs, expectedMaxMs);
  }

  analyze() {
    const now = Date.now();
    if (now - this.lastAnalysisAt < this.analysisIntervalMs) {
      return null;
    }

    const eventLog = this.eventCollector.getRecentEvents();
    const snapshots = this.eventCollector.getAllSnapshots();

    const analysis = this.anomalyDetector.analyzeLog(eventLog, snapshots);

    const suggestions = this.suggestionEngine.generateSuggestions(analysis.issues);
    for (const suggestion of suggestions) {
      this.suggestionEngine.enqueueSuggestion(suggestion);
    }

    this.analysisReport = {
      analyzedAt: now,
      healthScore: analysis.score,
      issuesTotalCount: analysis.issues.length,
      issues: analysis.issues,
      suggestions,
    };

    this.lastAnalysisAt = now;
    return this.analysisReport;
  }

  getHealthReport() {
    return this.analysisReport;
  }

  getSuggestions() {
    return this.suggestionEngine.getPendingSuggestions();
  }

  formatDiagnostic() {
    if (!this.analysisReport) {
      return "No analysis available yet. Run analyze() first.";
    }

    let report = `\n=== AI OBSERVER DIAGNOSTIC REPORT ===\n`;
    report += `System Health Score: ${this.analysisReport.healthScore}/100\n`;
    report += `Total Issues Detected: ${this.analysisReport.issuesTotalCount}\n\n`;

    if (this.analysisReport.issuesTotalCount === 0) {
      report += "✓ System appears healthy. No anomalies detected.\n";
    } else {
      report += "Issues Detected:\n";
      for (const issue of this.analysisReport.issues) {
        report += `  [${issue.severity.toUpperCase()}] ${issue.type}\n`;
        report += `    → ${issue.rootCauseHypothesis}\n\n`;
      }
    }

    if (this.analysisReport.suggestions.length > 0) {
      report += `\nPending Suggestions: ${this.analysisReport.suggestions.length}\n`;
      report += this.suggestionEngine.formatSuggestionReport();
    }

    return report;
  }

  recordSession(systemConfig) {
    return this.systemDoctor.recordSession(
      this.eventCollector.eventLog,
      this.eventCollector.utteranceSnapshots,
      systemConfig
    );
  }

  simulateParameterChange(recordingId, parameter, newValue) {
    return this.systemDoctor.simulateParameterChange(recordingId, parameter, newValue);
  }

  getSimulationReport(simulationId) {
    return this.systemDoctor.exportSimulationReport(simulationId);
  }

  pause() {
    this.eventCollector.pause();
  }

  resume() {
    this.eventCollector.resume();
  }

  clear() {
    this.eventCollector.clear();
    this.analysisReport = null;
    this.lastAnalysisAt = 0;
  }

  exportLog() {
    return this.eventCollector.exportLog();
  }
}

module.exports = {
  AIObserver,
  EventCollector,
  AnomalyDetector,
  SuggestionEngine,
  SystemDoctor,
};
