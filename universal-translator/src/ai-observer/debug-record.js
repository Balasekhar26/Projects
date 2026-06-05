const crypto = require("crypto");

const SCHEMA_VERSION = "1.0";
const NORMALIZATION_VERSION = "v1";
const MAX_DEBUG_EVENTS = 200;
const EPSILON_THRESHOLD = 1e-8;
const RATIO_EPSILON = 1e-6;

function stableStringify(value) {
  if (Array.isArray(value)) {
    return `[${value.map((item) => stableStringify(item)).join(",")}]`;
  }

  if (value && typeof value === "object") {
    const entries = Object.keys(value)
      .sort()
      .map((key) => `"${key}":${stableStringify(value[key])}`);
    return `{${entries.join(",")}}`;
  }

  return JSON.stringify(value);
}

function hashPayload(payload) {
  return crypto.createHash("sha256").update(stableStringify(payload)).digest("hex");
}

function normalizeContributions(contributions) {
  const raw = contributions || {};
  const normalized = {};
  const decisionDomains = ["system", "observer"].filter((domain) => Object.prototype.hasOwnProperty.call(raw, domain));
  const primaryTotal = decisionDomains.reduce((sum, domain) => sum + Math.abs(raw[domain] || 0), 0);

  // Handle absolute void
  if (primaryTotal < EPSILON_THRESHOLD) {
    for (const domain of Object.keys(raw).sort()) {
      normalized[domain] = 0;
    }
    return normalized;
  }

  // Normalize decision domains
  for (const domain of Object.keys(raw).sort()) {
    if (decisionDomains.includes(domain)) {
      normalized[domain] = Number((raw[domain] / primaryTotal).toFixed(6));
    } else {
      normalized[domain] = raw[domain] === 0 ? 0 : 1;
    }
  }

  // Check for relative void (numerical annihilation)
  if (decisionDomains.length === 2) {
    const [domain1, domain2] = decisionDomains;
    const val1 = Math.abs(normalized[domain1]);
    const val2 = Math.abs(normalized[domain2]);
    const minVal = Math.min(val1, val2);
    const maxVal = Math.max(val1, val2);
    const ratio = minVal / maxVal;

    if (ratio < RATIO_EPSILON) {
      // Numerical annihilation: smaller domain becomes 0, larger becomes 1
      const annihilated = minVal === val1 ? domain1 : domain2;
      const dominant = minVal === val1 ? domain2 : domain1;
      normalized[annihilated] = 0;
      normalized[dominant] = 1;
    }
  }

  return normalized;
}

function computeDependencyHash({ sourceEventIds, transformation, eventType, timing, weights, confidences }) {
  return hashPayload({
    sourceEventIds,
    transformation,
    eventType,
    timing,
    weights,
    confidences,
  });
}

function computeDecisionHash(record) {
  const payload = {
    type: record.type,
    dominantDomain: record.dominantDomain,
    contributions: normalizeContributions(record.contributions),
  };

  return hashPayload(payload);
}

function computeIntegrityHash(recordWithoutIntegrityHash) {
  const payload = {
    id: recordWithoutIntegrityHash.id,
    type: recordWithoutIntegrityHash.type,
    schemaVersion: recordWithoutIntegrityHash.schemaVersion,
    normalizationVersion: recordWithoutIntegrityHash.normalizationVersion,
    rawTime: recordWithoutIntegrityHash.rawTime,
    sessionTime: recordWithoutIntegrityHash.sessionTime,
    normalizedTime: recordWithoutIntegrityHash.normalizedTime,
    causalityKey: recordWithoutIntegrityHash.causalityKey,
    timing: recordWithoutIntegrityHash.timing,
    weights: recordWithoutIntegrityHash.weights,
    confidences: recordWithoutIntegrityHash.confidences,
    ignoredDomains: recordWithoutIntegrityHash.ignoredDomains,
    ignoredDomainsDecision: recordWithoutIntegrityHash.ignoredDomainsDecision,
    dominantDomain: recordWithoutIntegrityHash.dominantDomain,
    contributions: recordWithoutIntegrityHash.contributions,
    temporalIdentity: recordWithoutIntegrityHash.temporalIdentity,
    flags: recordWithoutIntegrityHash.flags,
    createdAt: recordWithoutIntegrityHash.createdAt,
  };

  return hashPayload(payload);
}

function computeTimingHash(record) {
  const payload = {
    rawTime: record.rawTime,
    sessionTime: record.sessionTime,
    normalizedTime: record.normalizedTime,
    timing: record.timing,
  };

  return hashPayload(payload);
}

function computeLogicHash(record) {
  const payload = {
    type: record.type,
    dominantDomain: record.dominantDomain,
    contributions: normalizeContributions(record.contributions),
  };

  return hashPayload(payload);
}

function verifyNormalizationDebugRecord(record) {
  const cloned = {
    ...record,
  };
  delete cloned.integrityHash;

  const expectedHash = computeIntegrityHash(cloned);
  if (record.integrityHash !== expectedHash) {
    throw new Error("DEBUG RECORD CORRUPTED: integrity mismatch");
  }

  return true;
}

function deepFreeze(value) {
  if (!value || typeof value !== "object" || Object.isFrozen(value)) {
    return value;
  }

  Object.freeze(value);
  for (const key of Object.keys(value)) {
    deepFreeze(value[key]);
  }

  return value;
}

module.exports = {
  SCHEMA_VERSION,
  NORMALIZATION_VERSION,
  MAX_DEBUG_EVENTS,
  EPSILON_THRESHOLD,
  RATIO_EPSILON,
  stableStringify,
  hashPayload,
  normalizeContributions,
  computeDependencyHash,
  computeIntegrityHash,
  computeDecisionHash,
  computeTimingHash,
  computeLogicHash,
  verifyNormalizationDebugRecord,
  deepFreeze,
};
