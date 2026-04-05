function normalizeText(value) {
  return typeof value === "string" ? value.trim() : "";
}

class EnglishTranslator {
  async translate(input) {
    const transcript = normalizeText(input.transcript);
    const whisperTranslation = normalizeText(input.whisperTranslation);
    const detectedLanguage = normalizeText(input.detectedLanguage).toLowerCase();

    if (whisperTranslation) {
      return {
        translatedText: whisperTranslation,
        backend: "whisper",
      };
    }

    if (!transcript) {
      return {
        translatedText: "",
        backend: "none",
      };
    }

    if (!detectedLanguage || detectedLanguage === "en") {
      return {
        translatedText: transcript,
        backend: "passthrough",
      };
    }

    throw new Error(
      `No text translation backend is configured for detected language "${detectedLanguage}". ` +
        "Whisper translation was empty, so the chunk could not be translated to English."
    );
  }
}

module.exports = {
  EnglishTranslator,
};
