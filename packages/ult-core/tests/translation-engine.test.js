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
