const { translateOnline } = require("./online-libre");
const { ArgosTranslateClient } = require("./argos");

class HybridTranslationEngine {
  constructor(config) {
    this.config = config;
    this.offline = new ArgosTranslateClient(config);
  }

  async translate({
    transcript,
    whisperTranslation,
    detectedLanguage,
    sourceLanguage,
    targetLanguage,
    onlinePolicy = "auto",
  }) {
    const normalizedTranscript = normalizeText(transcript);
    const normalizedWhisper = normalizeText(whisperTranslation);
    const normalizedSource = normalizeLanguage(sourceLanguage);
    const normalizedTarget = normalizeLanguage(targetLanguage);
    const normalizedDetected = normalizeLanguage(detectedLanguage) || normalizedSource || "auto";

    if (!normalizedTranscript && !normalizedWhisper) {
      return { translatedText: "", backend: "none" };
    }

    if (!normalizedTarget || normalizedTarget === normalizedSource) {
      return { translatedText: normalizedTranscript, backend: "passthrough" };
    }

    if (normalizedTarget === "en" && normalizedWhisper) {
      return { translatedText: normalizedWhisper, backend: "whisper" };
    }

    if (!normalizedTranscript) {
      return { translatedText: "", backend: "none" };
    }

    const canUseOnline = onlinePolicy !== "offline-only" && onlinePolicy !== "auto";
    if (canUseOnline || onlinePolicy === "online-only") {
      try {
        const translatedText = await translateOnline({
          text: normalizedTranscript,
          sourceLanguage: normalizedDetected,
          targetLanguage: normalizedTarget,
        });
        return { translatedText, backend: "libretranslate" };
      } catch (error) {
        if (onlinePolicy === "online-only") {
          throw error;
        }
      }
    }

    const translatedText = await this.offline.translate({
      text: normalizedTranscript,
      sourceLanguage: normalizedDetected,
      targetLanguage: normalizedTarget,
    });

    return {
      translatedText,
      backend: "argos",
    };
  }

  stop() {
    this.offline.stop();
  }
}

function normalizeText(value) {
  return typeof value === "string" ? value.trim() : "";
}

function normalizeLanguage(value) {
  return typeof value === "string" ? value.trim().toLowerCase() : "";
}

module.exports = {
  HybridTranslationEngine,
};
