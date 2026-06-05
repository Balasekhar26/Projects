const { evaluateTemporalIdentities } = require("./temporal-identity");
const { resolveTemporalIdentityConfig } = require("./temporal-config");

function runTemporalLatencyHarness(records, options = {}) {
  const config = resolveTemporalIdentityConfig(options.temporalIdentityConfig || options);
  const evaluation = evaluateTemporalIdentities(records, config);
  const transitions = evaluation.transitions.map((transition) => ({
    channelKey: transition.channelKey,
    effectiveDominantDomain: transition.effectiveDominantDomain,
    firstEvidenceTime: transition.firstEvidenceTime,
    commitTime: transition.commitTime,
    commitDelay: transition.commitDelay,
    commitDelayMs: transition.commitDelayMs,
    confirmationFrames: transition.confirmationFrames,
    falseRejections: transition.falseRejections,
    prematureCommits: transition.prematureCommits,
    rawFlipAttempts: transition.rawFlipAttempts,
    rejectedSpikes: transition.rejectedSpikes,
    hysteresisHoldMs: transition.hysteresisHoldMs,
    stabilityScore: transition.stabilityScore,
  }));

  return {
    config,
    records: evaluation.records,
    transitions,
    summary: summarizeTransitions(transitions),
  };
}

function summarizeTransitions(transitions) {
  if (!Array.isArray(transitions) || transitions.length === 0) {
    return {
      transitionCount: 0,
      averageCommitDelayMs: 0,
      maxCommitDelayMs: 0,
      totalFalseRejections: 0,
      totalPrematureCommits: 0,
    };
  }

  const totalCommitDelay = transitions.reduce((sum, transition) => sum + transition.commitDelayMs, 0);
  const totalFalseRejections = transitions.reduce((sum, transition) => sum + transition.falseRejections, 0);
  const totalPrematureCommits = transitions.reduce((sum, transition) => sum + transition.prematureCommits, 0);

  return {
    transitionCount: transitions.length,
    averageCommitDelayMs: Math.round(totalCommitDelay / transitions.length),
    maxCommitDelayMs: Math.max(...transitions.map((transition) => transition.commitDelayMs)),
    totalFalseRejections,
    totalPrematureCommits,
  };
}

module.exports = {
  runTemporalLatencyHarness,
};
