const { resolveCoreConfig } = require("../config");

class DeepLTranslateClient {
  constructor(config = {}) {
    this.config = resolveCoreConfig(config);
    this.apiKey = this.config.deepLApiKey;
  }

  async translate({ text, sourceLanguage, targetLanguage }) {
    if (!this.apiKey) {
      throw new Error("DEEPL_API_KEY is not configured.");
    }

    const endpoint = this.apiKey.endsWith(":fx")
      ? "https://api-free.deepl.com/v2/translate"
      : "https://api.deepl.com/v2/translate";

    const params = new URLSearchParams();
    params.set("text", text);
    params.set("target_lang", mapTargetLanguage(targetLanguage));
    if (sourceLanguage && sourceLanguage !== "auto") {
      params.set("source_lang", mapSourceLanguage(sourceLanguage));
    }

    const response = await fetch(endpoint, {
      method: "POST",
      headers: {
        Authorization: `DeepL-Auth-Key ${this.apiKey}`,
        "Content-Type": "application/x-www-form-urlencoded",
      },
      body: params.toString(),
    });

    const payload = await response.json().catch(() => null);
    if (!response.ok) {
      throw new Error(payload?.message || payload?.error?.message || `DeepL translation failed (${response.status})`);
    }

    const translatedText = payload?.translations?.[0]?.text || "";
    return {
      translated_text: translatedText,
    };
  }
}

function mapSourceLanguage(code) {
  return String(code || "").trim().toUpperCase();
}

function mapTargetLanguage(code) {
  const normalized = String(code || "").trim().toUpperCase();
  if (normalized === "EN") return "EN-US";
  if (normalized === "PT") return "PT-BR";
  if (normalized === "ZH") return "ZH";
  return normalized;
}

module.exports = {
  DeepLTranslateClient,
};
