const { getCoreConfig } = require("../../packages/ult-core/src/config");
const { HybridTranslationEngine } = require("../../packages/ult-core/src/translation-engine");

let translator = null;

async function translateInput({
  transcript,
  whisperTranslation,
  detectedLanguage,
  sourceLanguage,
  targetLanguage,
  onlinePolicy = "offline-only",
}) {
  if (!translator) {
    translator = new HybridTranslationEngine(getCoreConfig());
  }

  return translator.translate({
    transcript,
    whisperTranslation,
    detectedLanguage,
    sourceLanguage,
    targetLanguage,
    onlinePolicy,
  });
}

module.exports = {
  translateInput,
};
