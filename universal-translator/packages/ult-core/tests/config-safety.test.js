const test = require("node:test");
const assert = require("node:assert/strict");

const { resolveCoreConfig } = require("../src/config");
const { HybridTranslationEngine } = require("../src/translation-engine");

test("config defaults are safe with minimal overrides and do not require worker startup at import time", () => {
  const config = resolveCoreConfig({
    tempDir: "C:\\temp\\ult-test",
    voiceProfilesDir: "C:\\temp\\ult-test\\voices",
  });

  assert.equal(typeof config.pythonPath, "string");
  assert.equal(typeof config.scriptsDir, "string");
  assert.equal(config.onlinePolicy, "offline-only");
  assert.equal(config.runtimeTier, "free");
  assert.equal(config.freeOnlyProviders, true);
  assert.equal(config.allowExperimentalOnline, false);
  assert.equal(config.latencyProfile, "ultra-low");
  assert.equal(config.maxRealtimeLatencyMs, 500);
});

test("paid providers stay locked even when keys or paid tier are supplied", () => {
  const freeConfig = resolveCoreConfig({
    openAiApiKey: "test-openai",
    deepLApiKey: "test-deepl",
    nvidiaNimApiKey: "test-nvidia",
  });
  assert.equal(freeConfig.freeOnlyProviders, true);
  assert.equal(freeConfig.allowExperimentalOnline, false);
  assert.equal(freeConfig.openAiApiKey, "");
  assert.equal(freeConfig.deepLApiKey, "");
  assert.equal(freeConfig.nvidiaNimApiKey, "");

  const paidConfig = resolveCoreConfig({
    runtimeTier: "paid",
    openAiApiKey: "test-openai",
    deepLApiKey: "test-deepl",
    nvidiaNimApiKey: "test-nvidia",
  });
  assert.equal(paidConfig.runtimeTier, "free");
  assert.equal(paidConfig.freeOnlyProviders, true);
  assert.equal(paidConfig.allowExperimentalOnline, false);
  assert.equal(paidConfig.openAiApiKey, "");
  assert.equal(paidConfig.deepLApiKey, "");
  assert.equal(paidConfig.nvidiaNimApiKey, "");
});

test("latency profiles provide explicit free realtime budgets", () => {
  const ultra = resolveCoreConfig({ latencyProfile: "ultra-low" });
  const stable = resolveCoreConfig({ latencyProfile: "stable" });

  assert.equal(ultra.maxRealtimeLatencyMs, 500);
  assert.ok(ultra.chunkDurationMs < stable.chunkDurationMs);
  assert.ok(ultra.realtimeForceCommitMs < stable.realtimeForceCommitMs);
});

test("translation engine can be constructed with minimal config without starting workers", () => {
  const engine = new HybridTranslationEngine({
    tempDir: "C:\\temp\\ult-test",
    voiceProfilesDir: "C:\\temp\\ult-test\\voices",
  });

  assert.ok(engine);
  assert.equal(engine.google, null);
  engine.stop();
});
