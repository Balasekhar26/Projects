const TEMPORAL_IDENTITY_CONFIG = Object.freeze({
  minDurationMs: 20,
  majorityWindow: 5,
  majorityCount: 3,
  hysteresisMargin: 0.08,
});

function resolveTemporalIdentityConfig(overrides = {}) {
  return Object.freeze({
    ...TEMPORAL_IDENTITY_CONFIG,
    ...(overrides || {}),
  });
}

module.exports = {
  TEMPORAL_IDENTITY_CONFIG,
  resolveTemporalIdentityConfig,
};
