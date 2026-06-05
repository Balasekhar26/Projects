const test = require("node:test");
const assert = require("node:assert/strict");

const { HybridTranslationEngine } = require("../src/translation-engine");

test("translation engine uses whisper output directly for english targets", async () => {
  const engine = new HybridTranslationEngine({
    pythonPath: "",
    argosWorkerPath: "",
    argosPackagesDir: "",
  });

  const result = await engine.translate({
    transcript: "hola",
    whisperTranslation: "hello",
    detectedLanguage: "es",
    sourceLanguage: "es",
    targetLanguage: "en",
    onlinePolicy: "offline-only",
  });

  assert.equal(result.translatedText, "hello");
  assert.equal(result.backend, "whisper");
});

test("translation engine rejects online translation even when NVIDIA settings are supplied", async () => {
  const engine = new HybridTranslationEngine({
    runtimeTier: "paid",
    nvidiaNimApiKey: "test-key",
    translationProvider: "nvidia",
    onlinePolicy: "online-only",
  });

  await assert.rejects(
    () =>
      engine.translate({
        transcript: "hello",
        sourceLanguage: "en",
        targetLanguage: "es",
        onlinePolicy: "online-only",
      }),
    /Online translation unavailable/
  );
  assert.equal(engine.nvidia, null);
});

test("translation engine blocks paid providers in free tier even if keys exist", async () => {
  const engine = new HybridTranslationEngine({
    nvidiaNimApiKey: "test-key",
    translationProvider: "nvidia",
    onlinePolicy: "online-only",
  });

  await assert.rejects(
    () =>
      engine.translate({
        transcript: "hello",
        sourceLanguage: "en",
        targetLanguage: "es",
        onlinePolicy: "online-only",
      }),
    /Online translation unavailable/
  );
});

test("translation engine lazily starts offline workers only when needed", () => {
  const engine = new HybridTranslationEngine({
    pythonPath: "",
    argosWorkerPath: "",
    argosPackagesDir: "",
  });

  assert.equal(engine.google, null);
  assert.equal(engine.argos, null);
  assert.equal(engine.marian, null);
  assert.equal(engine.nvidia, null);
  engine.stop();
});
