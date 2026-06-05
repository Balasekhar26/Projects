const LIBRE_ENDPOINTS = [
  "https://libretranslate.com/translate",
  "https://translate.argosopentech.com/translate",
];

async function translateOnline({ text, sourceLanguage, targetLanguage }) {
  let lastError;
  for (const endpoint of LIBRE_ENDPOINTS) {
    try {
      return await tryEndpoint(endpoint, { text, sourceLanguage, targetLanguage });
    } catch (error) {
      lastError = error;
    }
  }
  throw lastError;
}

async function tryEndpoint(endpoint, { text, sourceLanguage, targetLanguage }) {
  const response = await fetch(endpoint, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      q: text,
      source: sourceLanguage || "auto",
      target: targetLanguage,
      format: "text",
    }),
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Online translation failed: ${errorText}`);
  }

  const payload = await response.json();
  return (payload.translatedText || payload.translated_text || "").trim();
}

module.exports = {
  translateOnline,
};
