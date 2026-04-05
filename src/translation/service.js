const { getCoreConfig } = require("../../packages/ult-core/src/config");
const { HybridTranslationEngine } = require("../../packages/ult-core/src/translation-engine");

const translator = new HybridTranslationEngine(getCoreConfig());

async function translateInput({
  transcript,
  whisperTranslation,
  detectedLanguage,
  sourceLanguage,
  targetLanguage,
  onlinePolicy = "auto",
}) {
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
