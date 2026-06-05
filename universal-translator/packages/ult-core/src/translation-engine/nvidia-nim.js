const DEFAULT_ENDPOINT = "https://integrate.api.nvidia.com/v1/chat/completions";
const DEFAULT_GENERAL_MODEL = "meta/llama-3.1-8b-instruct";
const DEFAULT_TRANSLATION_MODEL = "nvidia/riva-translate-4b-instruct-v1.1";
const RIVA_TRANSLATE_LANGUAGES = new Set([
  "ar",
  "de",
  "en",
  "es",
  "fr",
  "ja",
  "ko",
  "pt",
  "ru",
  "zh",
]);

async function translateWithNvidiaNim({ text, sourceLanguage, targetLanguage, config = {} }) {
  const apiKey = normalizeText(config.nvidiaNimApiKey);
  if (!apiKey) {
    throw new Error("NVIDIA_NIM_API_KEY or NVIDIA_API_KEY is not configured.");
  }

  const endpoint = normalizeText(config.nvidiaNimEndpoint) || DEFAULT_ENDPOINT;
  const model = selectModel({ sourceLanguage, targetLanguage, config });
  const timeoutMs = normalizePositiveNumber(config.nvidiaNimTimeoutMs, 30000);
  const maxTokens = normalizePositiveNumber(config.nvidiaNimMaxTokens, 1024);
  const messages = buildMessages({ text, sourceLanguage, targetLanguage, model });
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetch(endpoint, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${apiKey}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        model,
        temperature: 0.1,
        top_p: 0.7,
        max_tokens: maxTokens,
        stream: false,
        messages,
      }),
      signal: controller.signal,
    });

    if (!response.ok) {
      const errorText = await readResponseText(response);
      throw new Error(
        `NVIDIA NIM API error: ${response.status} ${response.statusText || ""} ${errorText}`.trim()
      );
    }

    const payload = await response.json();
    const content =
      payload?.choices?.[0]?.message?.content ||
      payload?.choices?.[0]?.text ||
      payload?.output_text ||
      "";
    const translatedText = stripWrappingQuotes(normalizeText(content));

    if (!translatedText) {
      throw new Error("NVIDIA NIM returned an empty translation.");
    }

    return translatedText;
  } catch (error) {
    if (error?.name === "AbortError") {
      throw new Error(`NVIDIA NIM translation timed out after ${timeoutMs} ms.`);
    }
    throw error;
  } finally {
    clearTimeout(timeout);
  }
}

class NvidiaNimTranslateClient {
  constructor(config = {}) {
    this.config = config;
  }

  async translate({ text, sourceLanguage, targetLanguage }) {
    return translateWithNvidiaNim({
      text,
      sourceLanguage,
      targetLanguage,
      config: this.config,
    });
  }
}

async function readResponseText(response) {
  try {
    return await response.text();
  } catch {
    return "";
  }
}

function selectModel({ sourceLanguage, targetLanguage, config }) {
  const explicitModel = normalizeText(config.nvidiaNimModel);
  if (explicitModel) {
    return explicitModel;
  }

  if (canUseRivaTranslate(sourceLanguage, targetLanguage)) {
    return normalizeText(config.nvidiaNimTranslationModel) || DEFAULT_TRANSLATION_MODEL;
  }

  return normalizeText(config.nvidiaNimGeneralModel) || DEFAULT_GENERAL_MODEL;
}

function canUseRivaTranslate(sourceLanguage, targetLanguage) {
  const source = normalizeLanguage(sourceLanguage);
  const target = normalizeLanguage(targetLanguage);
  return source && target && source !== "auto" &&
    RIVA_TRANSLATE_LANGUAGES.has(source) &&
    RIVA_TRANSLATE_LANGUAGES.has(target);
}

function buildMessages({ text, sourceLanguage, targetLanguage, model }) {
  const source = languageLabel(sourceLanguage || "auto");
  const target = languageLabel(targetLanguage);
  if (model === DEFAULT_TRANSLATION_MODEL || model.includes("riva-translate")) {
    return [
      {
        role: "system",
        content: `You are an expert at translating text from ${source} to ${target}.`,
      },
      {
        role: "user",
        content: `What is the ${target} translation of the sentence: ${text}?`,
      },
    ];
  }

  return [
    {
      role: "system",
      content:
        `You are a translation engine. Translate the user's text from ${source} to ${target}. ` +
        "Return only the translated text. Do not add explanations, labels, markdown, or quotes.",
    },
    {
      role: "user",
      content: text,
    },
  ];
}

function stripWrappingQuotes(value) {
  if (value.length < 2 || value.includes("\n")) {
    return value;
  }

  const first = value[0];
  const last = value[value.length - 1];
  if (
    (first === '"' && last === '"') ||
    (first === "'" && last === "'") ||
    (first === "`" && last === "`")
  ) {
    return value.slice(1, -1).trim();
  }

  return value;
}

function normalizeText(value) {
  return typeof value === "string" ? value.trim() : "";
}

function normalizeLanguage(value) {
  const normalized = normalizeText(value).toLowerCase();
  return normalized.split("-", 1)[0];
}

function languageLabel(value) {
  const labels = {
    ar: "Arabic",
    de: "German",
    en: "English",
    es: "Spanish",
    fr: "French",
    hi: "Hindi",
    ja: "Japanese",
    ko: "Korean",
    pt: "Portuguese",
    ru: "Russian",
    te: "Telugu",
    zh: "Chinese",
  };
  const normalized = normalizeLanguage(value);
  return labels[normalized] || normalizeText(value) || "auto";
}

function normalizePositiveNumber(value, fallback) {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

module.exports = {
  DEFAULT_ENDPOINT,
  DEFAULT_GENERAL_MODEL,
  DEFAULT_TRANSLATION_MODEL,
  NvidiaNimTranslateClient,
  translateWithNvidiaNim,
};
