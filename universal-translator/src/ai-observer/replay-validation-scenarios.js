/**
 * Test Scenarios for Deterministic Replay Validation
 * 
 * Phase 3A Validation: Test the system under realistic conditions
 * to ensure timing normalization prevents ghost anomalies.
 */

const { EventTimeNormalizer } = require("./event-time-normalizer");
const { DeterministicReplayHarness } = require("./deterministic-replay-harness");
const { AnomalyDetector } = require("./anomaly-detector");

class ReplayValidationScenarios {
  constructor() {
    this.harness = new DeterministicReplayHarness({
      diagnosticMode: false,
    });
    this.results = [];
  }

  /**
   * Scenario 1: Fast Speech
   * 
   * Fast talker (140+ wpm) with minimal pauses.
   * Risk: high utterance update frequency, potential revision oscillation.
   */
  generateFastSpeechScenario(durationMs = 15000) {
    const events = [];
    let eventTime = Date.now();
    const baseTime = eventTime;

    const chunkIntervalMs = 350;
    let chunkNumber = 0;

    for (let t = 0; t < durationMs; t += chunkIntervalMs) {
      const utteranceNumber = Math.floor(t / 3000);
      const confidence = 0.75 + Math.random() * 0.2;

      events.push({
        type: "stt-chunk",
        t: baseTime + t,
        chunkNumber: chunkNumber++,
        transcript: `word${utteranceNumber}_${Math.floor(Math.random() * 10)}`,
        confidence,
        isStable: Math.random() > 0.6,
        rms: 0.02 + Math.random() * 0.015,
        durationMs: chunkIntervalMs,
      });

      const revisionCount = Math.floor(t / 1000);
      if (revisionCount > 0 && t % 1000 === 0) {
        events.push({
          type: "utterance-updated",
          t: baseTime + t,
          utteranceId: `utt-${utteranceNumber}`,
          revision: revisionCount,
          mode: "tentative",
          confidence,
          playbackState: "idle",
        });
      }

      if (Math.random() > 0.85) {
        events.push({
          type: "arbitration-decision",
          t: baseTime + t,
          utteranceId: `utt-${utteranceNumber}`,
          action: Math.random() > 0.3 ? "speak" : "wait",
          reason: "tentative-ready",
        });
      }
    }

    return {
      name: "Fast Speech",
      description: "Fast talker (140+ wpm), minimal pauses, high update frequency",
      durationMs,
      events,
      expectedRisks: ["revision-oscillation", "latency-spike-cluster"],
    };
  }

  /**
   * Scenario 2: Emotional Speech
   * 
   * Speaker with varied pace, emotion changes, prosody variation.
   * Risk: confidence drops during emotion transitions, confidence variation.
   */
  generateEmotionalSpeechScenario(durationMs = 20000) {
    const events = [];
    let eventTime = Date.now();
    const baseTime = eventTime;

    const phases = [
      { name: "calm", duration: 5000, minConfidence: 0.85, maxConfidence: 0.95 },
      { name: "excited", duration: 5000, minConfidence: 0.65, maxConfidence: 0.80 },
      { name: "uncertain", duration: 5000, minConfidence: 0.45, maxConfidence: 0.60 },
      { name: "resolved", duration: 5000, minConfidence: 0.80, maxConfidence: 0.92 },
    ];

    let chunkNumber = 0;
    let phaseIndex = 0;
    let phaseStartTime = 0;
    const chunkIntervalMs = 500;

    for (let t = 0; t < durationMs; t += chunkIntervalMs) {
      if (phaseIndex < phases.length && t - phaseStartTime >= phases[phaseIndex].duration) {
        phaseIndex++;
        phaseStartTime = t;
      }

      const phase = phases[phaseIndex] || phases[phases.length - 1];
      const confidence =
        phase.minConfidence +
        Math.random() * (phase.maxConfidence - phase.minConfidence);

      events.push({
        type: "stt-chunk",
        t: baseTime + t,
        chunkNumber: chunkNumber++,
        transcript: `emotional_${phase.name}_${Math.floor(Math.random() * 5)}`,
        confidence,
        isStable: confidence > 0.75,
        rms: 0.015 + Math.random() * 0.02,
        durationMs: chunkIntervalMs,
      });

      if (t % 1000 === 0) {
        events.push({
          type: "utterance-updated",
          t: baseTime + t,
          utteranceId: `utt-emotional-${Math.floor(t / 3000)}`,
          revision: Math.floor(t / 1000),
          mode: confidence > 0.8 ? "commit" : "tentative",
          confidence,
        });
      }

      if (confidence > 0.7 && Math.random() > 0.6) {
        events.push({
          type: "playback-enqueued",
          t: baseTime + t,
          utteranceId: `utt-emotional-${Math.floor(t / 3000)}`,
          mode: "tentative",
          confidence,
        });
      }
    }

    return {
      name: "Emotional Speech",
      description:
        "Varied pace, emotion changes, prosody shifts, confidence variation",
      durationMs,
      events,
      expectedRisks: ["confidence-drop", "playback-blocked-excessively"],
    };
  }

  /**
   * Scenario 3: Noisy Speech
   * 
   * Background noise, audio dropouts, intermittent clarity.
   * Risk: gaps, low RMS, confidence instability, true silence gaps.
   */
  generateNoisySpeechScenario(durationMs = 18000) {
    const events = [];
    let eventTime = Date.now();
    const baseTime = eventTime;

    const noisyPeriods = [
      { start: 2000, end: 4000, noiseType: "fan" },
      { start: 8000, end: 9500, noiseType: "keyboard" },
      { start: 13000, end: 15000, noiseType: "ambient" },
    ];

    let chunkNumber = 0;
    const chunkIntervalMs = 400;

    for (let t = 0; t < durationMs; t += chunkIntervalMs) {
      const isNoisy = noisyPeriods.some((p) => t >= p.start && t < p.end);
      const isDropout = Math.random() > 0.92;

      let confidence = 0.8 + Math.random() * 0.15;
      let rms = 0.02 + Math.random() * 0.01;

      if (isNoisy) {
        confidence = 0.45 + Math.random() * 0.25;
        rms = 0.035 + Math.random() * 0.015;
      }

      if (isDropout) {
        confidence = 0.2 + Math.random() * 0.15;
        rms = 0.005 + Math.random() * 0.003;
      }

      events.push({
        type: "stt-chunk",
        t: baseTime + t,
        chunkNumber: chunkNumber++,
        transcript: isDropout ? "" : `noisy_${Math.floor(Math.random() * 10)}`,
        confidence,
        isStable: confidence > 0.75 && !isDropout,
        rms,
        durationMs: chunkIntervalMs,
        reason: isDropout ? "vad-silence" : "speech",
      });

      if (!isDropout && confidence > 0.5) {
        events.push({
          type: "utterance-updated",
          t: baseTime + t,
          utteranceId: `utt-noisy-${Math.floor(t / 4000)}`,
          revision: Math.floor(t / 1500),
          mode: confidence > 0.8 ? "commit" : "tentative",
          confidence,
        });
      }

      if (isDropout && t % 1500 === 0) {
        events.push({
          type: "silence-gap",
          t: baseTime + t,
          reason: "dropout",
          gapMs: 400,
        });
      }
    }

    return {
      name: "Noisy Speech",
      description: "Background noise, dropouts, intermittent clarity",
      durationMs,
      events,
      expectedRisks: ["silence-gaps", "confidence-drop", "latency-spike-cluster"],
    };
  }

  /**
   * Run all scenarios and validate determinism
   */
  runAllScenarios(replayCount = 3) {
    const scenarios = [
      this.generateFastSpeechScenario(),
      this.generateEmotionalSpeechScenario(),
      this.generateNoisySpeechScenario(),
    ];

    const scenarioResults = [];

    for (const scenario of scenarios) {
      console.log(`\n📊 Testing: ${scenario.name}`);
      console.log(`   ${scenario.description}`);
      console.log(`   Duration: ${scenario.durationMs}ms, Events: ${scenario.events.length}`);

      const sessionId = this.harness.recordSession(
        null,
        scenario.events,
        [],
        {}
      );

      const deterministicReport = this.harness.validateReplayDeterminism(
        sessionId,
        replayCount
      );

      const timingAnalysis = this.harness.analyzeTimingCoherence(sessionId);

      scenarioResults.push({
        scenario: scenario.name,
        sessionId,
        isDeterministic: deterministicReport.isDeterministic,
        verdict: deterministicReport.verdict,
        healthScoreVariance: deterministicReport.healthScoreVariance,
        issueCountVariance: deterministicReport.issueCountVariance,
        coherence: timingAnalysis.coherenceReport?.overallCoherence?.status,
        timingRiskLevel: timingAnalysis.riskAssessment.level,
      });

      console.log(`   ✓ ${deterministicReport.verdict}`);
      console.log(`   Coherence: ${timingAnalysis.coherenceReport?.overallCoherence?.status}`);
    }

    this.results = scenarioResults;
    return {
      totalScenarios: scenarios.length,
      allDeterministic: scenarioResults.every((r) => r.isDeterministic),
      results: scenarioResults,
    };
  }

  generateValidationReport() {
    if (this.results.length === 0) {
      return "No scenarios run yet. Call runAllScenarios() first.";
    }

    let report = `\n=== PHASE 3A VALIDATION REPORT ===\n\n`;
    report += `Scenarios Tested: ${this.results.length}\n`;
    report += `All Deterministic: ${this.results.every((r) => r.isDeterministic) ? "✓ YES" : "✗ NO"}\n\n`;

    for (const result of this.results) {
      report += `📊 ${result.scenario}\n`;
      report += `   Status: ${result.isDeterministic ? "✓ PASS" : "✗ FAIL"}\n`;
      report += `   ${result.verdict}\n`;
      report += `   Health Score Variance: ${result.healthScoreVariance}\n`;
      report += `   Issue Count Variance: ${result.issueCountVariance}\n`;
      report += `   Timing Coherence: ${result.coherence}\n`;
      report += `   Timing Risk: ${result.timingRiskLevel}\n\n`;
    }

    const allPass = this.results.every((r) => r.isDeterministic);
    report += `\n${allPass ? "✓ CONCLUSION: System ready for Phase 3B (adaptive tuning)" : "✗ CONCLUSION: Resolve timing issues before proceeding"}\n`;

    return report;
  }
}

module.exports = {
  ReplayValidationScenarios,
};
