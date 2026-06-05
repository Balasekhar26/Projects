const LANGUAGE_CATALOG = [
  { code: "ar", label: "Arabic" },
  { code: "bn", label: "Bengali" },
  { code: "de", label: "German" },
  { code: "en", label: "English", offlinePreferred: true },
  { code: "es", label: "Spanish" },
  { code: "fa", label: "Persian" },
  { code: "fr", label: "French" },
  { code: "gu", label: "Gujarati" },
  { code: "he", label: "Hebrew" },
  { code: "hi", label: "Hindi", offlinePreferred: true },
  { code: "id", label: "Indonesian" },
  { code: "it", label: "Italian" },
  { code: "ja", label: "Japanese" },
  { code: "kn", label: "Kannada" },
  { code: "ko", label: "Korean" },
  { code: "ml", label: "Malayalam" },
  { code: "mr", label: "Marathi" },
  { code: "nl", label: "Dutch" },
  { code: "pa", label: "Punjabi" },
  { code: "pl", label: "Polish" },
  { code: "pt", label: "Portuguese" },
  { code: "ru", label: "Russian" },
  { code: "sv", label: "Swedish" },
  { code: "ta", label: "Tamil" },
  { code: "te", label: "Telugu", offlinePreferred: true },
  { code: "th", label: "Thai" },
  { code: "tr", label: "Turkish" },
  { code: "uk", label: "Ukrainian" },
  { code: "ur", label: "Urdu" },
  { code: "vi", label: "Vietnamese" },
  { code: "zh", label: "Chinese" },
];

function listLanguages() {
  return LANGUAGE_CATALOG.slice();
}

function getLanguage(code) {
  const normalized = typeof code === "string" ? code.trim().toLowerCase() : "";
  return LANGUAGE_CATALOG.find((language) => language.code === normalized) || null;
}

module.exports = {
  LANGUAGE_CATALOG,
  getLanguage,
  listLanguages,
};
