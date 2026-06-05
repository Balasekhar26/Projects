const test = require("node:test");
const assert = require("node:assert/strict");

const {
  evaluateTemporalIdentities,
  stabilizeTemporalIdentities,
} = require("../../../src/ai-observer/temporal-identity");
const { computeDecisionHash } = require("../../../src/ai-observer/debug-record");
const { runTemporalLatencyHarness } = require("../../../src/ai-observer/temporal-latency-harness");

function createRecord(index, dominantDomain, normalizedTime, type = "final_translation", contributionsOverride = null) {
  const contributions = contributionsOverride || (
    dominantDomain === "observer"
      ? { system: 0.2, observer: 0.8 }
      : { system: 0.8, observer: 0.2 }
  );

  return {
    id: `evt-${index}`,
    type,
    normalizedTime,
    sessionTime: normalizedTime,
    rawTime: normalizedTime,
    dominantDomain,
    contributions,
    flags: [],
    ignoredDomains: [],
    ignoredDomainsDecision: [],
    timing: {
      raw: {},
      rebased: {},
      normalizationTrace: {},
      skew: {},
      coherenceScore: 1,
      flags: {},
    },
    weights: {},
    confidences: {},
    causalityKey: {
      sourceEventIds: [],
      transformation: "normalize.v1",
      dependencyHash: `dep-${index}`,
    },
    createdAt: normalizedTime,
    schemaVersion: "1.0",
    normalizationVersion: "v1",
  };
}

test("temporal identity rejects a single-frame spike between matching identities", () => {
  const records = [
    createRecord(0, "system", 0),
    createRecord(1, "system", 10),
    createRecord(2, "system", 20),
    createRecord(3, "observer", 30),
    createRecord(4, "system", 40),
    createRecord(5, "system", 50),
    createRecord(6, "system", 60),
  ];

  const stabilized = stabilizeTemporalIdentities(records);

  assert.deepEqual(
    stabilized.map((record) => record.dominantDomain),
    ["system", "system", "system", "system", "system", "system", "system"]
  );
  assert.equal(stabilized[3].temporalIdentity.state, "spike-rejected");
});

test("temporal identity preserves a real flip that persists long enough", () => {
  const records = [
    createRecord(0, "system", 0),
    createRecord(1, "system", 10),
    createRecord(2, "system", 20),
    createRecord(3, "observer", 30),
    createRecord(4, "observer", 40),
    createRecord(5, "observer", 50),
    createRecord(6, "observer", 60),
    createRecord(7, "system", 70),
    createRecord(8, "system", 80),
    createRecord(9, "system", 90),
  ];

  const stabilized = stabilizeTemporalIdentities(records);

  assert.deepEqual(
    stabilized.map((record) => record.dominantDomain),
    ["system", "system", "system", "observer", "observer", "observer", "observer", "system", "system", "system"]
  );
  assert.equal(stabilized[3].temporalIdentity.state, "warming");
  assert.equal(stabilized[5].temporalIdentity.state, "confirmed");
  assert.equal(stabilized[9].temporalIdentity.state, "confirmed");
  assert.equal(stabilized[5].temporalIdentity.metrics.commitDelayMs >= 20, true);
});

test("temporal identity is isolated per event type so interleaved channels do not corrupt each other", () => {
  const records = [
    createRecord(0, "system", 0, "status"),
    createRecord(1, "observer", 5, "health"),
    createRecord(2, "system", 10, "status"),
    createRecord(3, "observer", 15, "health"),
    createRecord(4, "system", 20, "status"),
    createRecord(5, "observer", 25, "health"),
  ];

  const stabilized = stabilizeTemporalIdentities(records);

  assert.deepEqual(
    stabilized.map((record) => `${record.type}:${record.dominantDomain}`),
    [
      "status:system",
      "health:observer",
      "status:system",
      "health:observer",
      "status:system",
      "health:observer",
    ]
  );
});

test("decision hashes now track stabilized identity rather than only event type", () => {
  const systemRecord = createRecord(0, "system", 0);
  const observerRecord = createRecord(1, "observer", 10);

  const systemHash = computeDecisionHash(systemRecord);
  const observerHash = computeDecisionHash(observerRecord);

  assert.notEqual(systemHash, observerHash);
});

test("temporal identity exposes delayed-reality transition metrics", () => {
  const records = [
    createRecord(0, "system", 0),
    createRecord(1, "system", 20),
    createRecord(2, "system", 40),
    createRecord(3, "observer", 100, "final_translation", { system: 0.53, observer: 0.47 }),
    createRecord(4, "observer", 120, "final_translation", { system: 0.52, observer: 0.48 }),
    createRecord(5, "observer", 140, "final_translation", { system: 0.35, observer: 0.65 }),
    createRecord(6, "observer", 180, "final_translation", { system: 0.2, observer: 0.8 }),
    createRecord(7, "observer", 220, "final_translation", { system: 0.18, observer: 0.82 }),
  ];

  const harness = runTemporalLatencyHarness(records);
  const observerTransition = harness.transitions.find(
    (transition) => transition.effectiveDominantDomain === "observer"
  );

  assert.ok(observerTransition);
  assert.equal(observerTransition.firstEvidenceTime, 100);
  assert.equal(observerTransition.commitTime >= 140, true);
  assert.equal(observerTransition.commitDelayMs >= 40, true);
  assert.equal(observerTransition.prematureCommits, 0);
});

test("temporal identity metadata carries explainable stability components", () => {
  const records = [
    createRecord(0, "system", 0),
    createRecord(1, "system", 10),
    createRecord(2, "observer", 20),
    createRecord(3, "system", 30),
    createRecord(4, "observer", 40),
    createRecord(5, "observer", 50),
    createRecord(6, "observer", 70),
  ];

  const evaluated = evaluateTemporalIdentities(records);
  const finalObserver = evaluated.records[6].temporalIdentity.metrics;

  assert.equal(typeof finalObserver.stabilityScore, "number");
  assert.equal(typeof finalObserver.confirmationFrames, "number");
  assert.equal(typeof finalObserver.commitDelayMs, "number");
  assert.equal(typeof finalObserver.rejectedSpikes, "number");
  assert.equal(typeof finalObserver.hysteresisHoldMs, "number");
  assert.equal(typeof finalObserver.rawFlipAttempts, "number");
  assert.equal(finalObserver.stabilityScore >= 0 && finalObserver.stabilityScore <= 1, true);
});
