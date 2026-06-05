const { GoogleTranslateClient } = require("./google");
const { ArgosTranslateClient } = require("./argos");
const { MarianTranslateClient } = require("./marian");
const { DeepLTranslateClient } = require("./deepl");
const { NvidiaNimTranslateClient } = require("./nvidia-nim");
const { resolveCoreConfig } = require("../config");

const ARGOS_SUPPORTED = new Set([
  "ar", "bn", "zh", "nl", "fr", "de", "he", "hi", "id", "it", "ja", "ko",
  "fa", "pl", "pt", "ru", "es", "sv", "th", "tr", "uk", "ur", "vi", "zt",
]);

const GOOGLE_TIMEOUT_MS = 500;
const ONLINE_TIMEOUT_MS = 30000;
const CACHE_MAX = 200;

class TranslationCache {
  constructor() {
    this._map = new Map();
  }

  key(text, src, tgt) {
    return `${src}|${tgt}|${text}`;
  }

  get(text, src, tgt) {
    return this._map.get(this.key(text, src, tgt)) || null;
  }

  set(text, src, tgt, result) {
    if (this._map.size >= CACHE_MAX) {
      this._map.delete(this._map.keys().next().value);
    }
    this._map.set(this.key(text, src, tgt), result);
  }
}

class HybridTranslationEngine {
  constructor(config = {}) {
    this.config = resolveCoreConfig(config);
    this.google = null;
    this.argos = null;
    this.marian = null;
    this.deepl = null;
    this.nvidia = null;
    this.cache = new TranslationCache();
  }

  async translate({
    transcript,
    whisperTranslation,
    detectedLanguage,
    sourceLanguage,
    targetLanguage,
    onlinePolicy = this.config.onlinePolicy || "offline-only",
  }) {
    const text = norm(transcript);
    const whisper = norm(whisperTranslation);
    const src = normLang(detectedLanguage) || normLang(sourceLanguage) || "auto";
    const tgt = normLang(targetLanguage);

    if (!text && !whisper) return { translatedText: "", backend: "none" };
    if (!tgt || tgt === src) return { translatedText: text, backend: "passthrough" };
    if (tgt === "en" && whisper) return { translatedText: whisper, backend: "whisper" };
    if (!text) return { translatedText: "", backend: "none" };

    const effectiveSrc = src === "auto" ? "en" : src;
    const policy = normalizePolicy(onlinePolicy);
    const cached = this.cache.get(text, effectiveSrc, tgt);
    if (cached) return { ...cached, backend: `${cached.backend}+cache` };

    if (policy !== "offline-only" && !this.config.freeOnlyProviders) {
      const onlineResult = await this._translateOnline({
        text,
        sourceLanguage: effectiveSrc,
        targetLanguage: tgt,
        onlineOnly: policy === "online-only",
      });

      if (onlineResult) {
        this.cache.set(text, effectiveSrc, tgt, onlineResult);
        return onlineResult;
      }
    }

    if (policy === "online-only") {
      throw new Error(`Online translation unavailable for ${effectiveSrc}->${tgt}`);
    }

    const offlineResult = await this._translateOffline({
      text,
      sourceLanguage: effectiveSrc,
      targetLanguage: tgt,
    });

    this.cache.set(text, effectiveSrc, tgt, offlineResult);
    return offlineResult;
  }

  async _translateOnline({ text, sourceLanguage, targetLanguage, onlineOnly }) {
    const errors = [];
    for (const provider of this._onlineProviderOrder()) {
      try {
        if (provider === "nvidia") {
          if (!this.config.nvidiaNimApiKey) continue;
          const translated = await withTimeout(
            this._getNvidia().translate({ text, sourceLanguage, targetLanguage }),
            this.config.nvidiaNimTimeoutMs || ONLINE_TIMEOUT_MS,
            "NVIDIA NIM translation timeout"
          );
          if (translated) return { translatedText: translated, backend: "nvidia-nim" };
        }

        if (provider === "deepl") {
          if (!this.config.deepLApiKey) continue;
          const result = await withTimeout(
            this._getDeepL().translate({ text, sourceLanguage, targetLanguage }),
            ONLINE_TIMEOUT_MS,
            "DeepL translation timeout"
          );
          const translated = result?.translated_text || "";
          if (translated) return { translatedText: translated, backend: "deepl" };
        }

        if (provider === "google") {
          const result = await this._googleWithTimeout(text, sourceLanguage, targetLanguage);
          if (result) return result;
        }
      } catch (error) {
        errors.push(`${provider}: ${error.message}`);
        if (onlineOnly) {
          throw new Error(errors.join("; "));
        }
      }
    }

    if (onlineOnly && errors.length) {
      throw new Error(errors.join("; "));
    }
    return null;
  }

  async _translateOffline({ text, sourceLanguage, targetLanguage }) {
    if (ARGOS_SUPPORTED.has(targetLanguage)) {
      try {
        const translated = await this._getArgos().translate({
          text,
          sourceLanguage,
          targetLanguage,
        });
        if (translated) return { translatedText: translated, backend: "argos" };
      } catch {
        // Fall through to MarianMT.
      }
    }

    try {
      const translated = await this._getMarian().translate({
        text,
        sourceLanguage,
        targetLanguage,
      });
      if (translated) return { translatedText: translated, backend: "marian" };
    } catch (error) {
      throw new Error(`All translation failed for ${sourceLanguage}->${targetLanguage}: ${error.message}`);
    }

    return { translatedText: text, backend: "passthrough" };
  }

  _onlineProviderOrder() {
    const provider = norm(this.config.translationProvider).toLowerCase();
    if (["nvidia", "deepl", "google"].includes(provider)) {
      return [provider];
    }
    return ["nvidia", "deepl", "google"];
  }

  _getNvidia() {
    if (!this.nvidia) this.nvidia = new NvidiaNimTranslateClient(this.config);
    return this.nvidia;
  }

  _getDeepL() {
    if (!this.deepl) this.deepl = new DeepLTranslateClient(this.config);
    return this.deepl;
  }

  _getGoogle() {
    if (!this.google) this.google = new GoogleTranslateClient(this.config);
    return this.google;
  }

  _getArgos() {
    if (!this.argos) this.argos = new ArgosTranslateClient(this.config);
    return this.argos;
  }

  _getMarian() {
    if (!this.marian) this.marian = new MarianTranslateClient(this.config);
    return this.marian;
  }

  _googleWithTimeout(text, src, tgt) {
    return withTimeout(
      this._getGoogle()
        .translate({ text, sourceLanguage: src, targetLanguage: tgt })
        .then((result) => {
          const translated = result?.translated_text || "";
          return translated ? { translatedText: translated, backend: "google" } : null;
        }),
      GOOGLE_TIMEOUT_MS,
      `Google Translate timeout (>${GOOGLE_TIMEOUT_MS}ms)`
    );
  }

  stop() {
    this.google?.stop?.();
    this.argos?.stop?.();
    this.marian?.stop?.();
  }
}

function withTimeout(promise, timeoutMs, message) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error(message)), timeoutMs);
    Promise.resolve(promise)
      .then((value) => {
        clearTimeout(timer);
        resolve(value);
      })
      .catch((error) => {
        clearTimeout(timer);
        reject(error);
      });
  });
}

function normalizePolicy(value) {
  const policy = norm(value).toLowerCase();
  if (policy === "online-only" || policy === "offline-only") return policy;
  return "auto";
}

function norm(v) {
  return typeof v === "string" ? v.trim() : "";
}

function normLang(v) {
  return typeof v === "string" ? v.trim().toLowerCase() : "";
}

module.exports = { HybridTranslationEngine, TranslationCache };
