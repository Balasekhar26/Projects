const test = require("node:test");
const assert = require("node:assert/strict");

const {
  aggregateVoiceIdentityProfiles,
  blendVoiceIdentityProfiles,
  extractVoiceIdentityFromChunk,
} = require("../src/voice-identity/profile");
const { TieredSpeechEngine } = require("../src/tts-engine/tiered-speaker");
const { RealtimeTranslator } = require("../../../src/pipeline/realtime-translator");

test("voice identity extractor derives stable profile fields from voiced audio", () => {
  const sampleRate = 16000;
  const durationSeconds = 0.6;
  const length = Math.floor(sampleRate * durationSeconds);
  const pcm = new Int16Array(length);

  for (let index = 0; index < length; index += 1) {
    const t = index / sampleRate;
    const sample =
      (Math.sin(2 * Math.PI * 180 * t) * 0.45) +
      (Math.sin(2 * Math.PI * 900 * t) * 0.12) +
      (Math.sin(2 * Math.PI * 2500 * t) * 0.07);
    pcm[index] = Math.round(sample * 32767);
  }

  const profile = extractVoiceIdentityFromChunk({
    pcmBuffer: Buffer.from(pcm.buffer),
    analysis: { rms: 0.18, peak: 0.46, zeroCrossingRate: 0.08, isSpeechLikely: true },
  }, { sampleRate, channels: 1 });

  assert.equal(profile !== null, true);
  assert.equal(profile.f0Mean > 150 && profile.f0Mean < 210, true);
  assert.equal(profile.f0Range > 10, true);
  assert.equal(Array.isArray(profile.formants), true);
  assert.equal(profile.formants.length, 3);
  assert.equal(profile.tempo >= 0.9 && profile.tempo <= 1.08, true);
});

test("rolling voice identity smoothing avoids hard snaps", () => {
  const translator = new RealtimeTranslator({
    config: {
      tempDir: "C:\\temp\\ult-test",
      sampleRate: 16000,
      channels: 1,
      bytesPerSample: 2,
      targetLanguage: "te",
      voiceIdentityWindowMs: 5000,
      voiceIdentityBlendFactor: 0.15,
    },
    capture: { on() {}, once() {}, start() {}, stop() {} },
    sttClient: { on() {} },
    translator: {},
    speaker: {},
  });

  const first = {
    pcmBuffer: Buffer.alloc(3200),
    durationMs: 200,
    analysis: { rms: 0.08, peak: 0.2, zeroCrossingRate: 0.06, isSpeechLikely: true },
  };
  const second = {
    pcmBuffer: Buffer.alloc(3200),
    durationMs: 200,
    analysis: { rms: 0.22, peak: 0.5, zeroCrossingRate: 0.18, isSpeechLikely: true },
  };

  translator.updateVoiceIdentity(first, 1000);
  const initial = translator.voiceIdentityProfile;
  translator.updateVoiceIdentity(second, 1400);
  const blended = translator.voiceIdentityProfile;

  assert.equal(initial !== null, true);
  assert.equal(blended !== null, true);
  assert.equal(blended.energy > initial.energy, true);
  assert.equal(blended.energy < 0.22, true);
});

test("tiered speaker applyVoiceIdentity maps profile into bounded playback controls", () => {
  const engine = new TieredSpeechEngine({
    tempDir: "C:\\temp\\ult-test",
    sampleRate: 16000,
    channels: 1,
    bytesPerSample: 2,
    targetLanguage: "en",
  });

  const shaped = engine.applyVoiceIdentity({
    f0Mean: 205,
    f0Range: 42,
    formants: [420, 1500, 3400],
    tempo: 1.06,
    energy: 0.14,
    tilt: 0.35,
    cadence: 0.7,
  }, {
    tempo: 0.98,
    volumeBoost: 0.96,
    pitchCents: 18,
    cadence: 0.5,
    emotionalTilt: 0.1,
    startupFadeMs: 50,
  });

  try {
    assert.equal(shaped.tempo > 0.98, true);
    assert.equal(shaped.volumeBoost > 0.96, true);
    assert.equal(shaped.pitchCents > 18, true);
    assert.equal(shaped.pitchCents <= 80, true);
    assert.equal(Math.abs(shaped.bassDb) <= 2.5, true);
    assert.equal(Math.abs(shaped.trebleDb) <= 2.5, true);
  } finally {
    engine.stop();
  }
});

test("tiered speaker splits long utterances into streaming-friendly clauses", () => {
  const engine = new TieredSpeechEngine({
    tempDir: "C:\\temp\\ult-test",
    sampleRate: 16000,
    channels: 1,
    bytesPerSample: 2,
    targetLanguage: "en",
  });

  try {
    const segments = engine._splitTextForStreaming(
      "This is the opening thought, and it should start quickly. Here is a longer follow-up clause that should be carried in a later slice so playback can begin sooner."
    );

    assert.equal(Array.isArray(segments), true);
    assert.equal(segments.length >= 2, true);
    assert.equal(segments[0].includes("opening thought"), true);
    assert.equal(segments.at(-1).includes("later slice"), true);
  } finally {
    engine.stop();
  }
});

test("tiered speaker breaks clauses into micro-flow segments", () => {
  const engine = new TieredSpeechEngine({
    tempDir: "C:\\temp\\ult-test",
    sampleRate: 16000,
    channels: 1,
    bytesPerSample: 2,
    targetLanguage: "en",
  });

  try {
    const plan = engine._buildStreamingPlan(
      "This should begin quickly and keep flowing through the rest of the sentence without waiting too long."
    );

    assert.equal(Array.isArray(plan), true);
    assert.equal(plan.length >= 3, true);
    assert.equal(plan[0].text.split(/\s+/).length <= 3, true);
    assert.equal(plan.some((segment) => segment.isMicro), true);
  } finally {
    engine.stop();
  }
});

test("voice identity helpers blend and aggregate profiles consistently", () => {
  const aggregated = aggregateVoiceIdentityProfiles([
    {
      durationMs: 300,
      profile: { f0Mean: 120, f0Range: 30, formants: [450, 1400, 2800], tempo: 0.96, energy: 0.07, tilt: -0.2, cadence: 0.58 },
    },
    {
      durationMs: 600,
      profile: { f0Mean: 180, f0Range: 45, formants: [620, 1650, 3200], tempo: 1.04, energy: 0.14, tilt: 0.25, cadence: 0.68 },
    },
  ]);
  const blended = blendVoiceIdentityProfiles(
    { f0Mean: 150, f0Range: 34, formants: [500, 1500, 3000], tempo: 1, energy: 0.1, tilt: 0, cadence: 0.6 },
    aggregated,
    0.15
  );

  assert.equal(aggregated.f0Mean > 150, true);
  assert.equal(aggregated.energy > 0.1, true);
  assert.equal(blended.f0Mean > 150, true);
  assert.equal(blended.f0Mean < aggregated.f0Mean, true);
});
