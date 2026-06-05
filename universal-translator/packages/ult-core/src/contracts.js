const SESSION_KINDS = Object.freeze({
  DESKTOP_RUNTIME: "desktop_runtime",
  ANDROID_RUNTIME: "android_runtime",
  BROWSER_DEBUG: "browser_debug",
  MICROPHONE: "microphone",
  SYSTEM: "system",
});

const ONLINE_POLICIES = Object.freeze({
  AUTO: "auto",
  ONLINE_ONLY: "online-only",
  OFFLINE_ONLY: "offline-only",
});

const SESSION_EVENT_TYPES = Object.freeze({
  STATUS: "status",
  ROUTING_STATE: "routing_state",
  PARTIAL_TRANSCRIPT: "partial_transcript",
  PARTIAL_TRANSLATION: "partial_translation",
  FINAL_TRANSLATION: "final_translation",
  TTS_STARTED: "tts_started",
  TTS_FINISHED: "tts_finished",
  LATENCY_SAMPLE: "latency_sample",
  ERROR: "error",
  SNAPSHOT: "snapshot",
  HEALTH: "health",
});

function createStartSessionRequest(overrides = {}) {
  return {
    platform: "windows",
    sourceLanguage: "en",
    targetLanguage: "te",
    autoDetectSource: true,
    sessionKind: SESSION_KINDS.BROWSER_DEBUG,
    inputDeviceId: "",
    outputDeviceId: "",
    micInputDeviceId: "",
    speakerOutputDeviceId: "",
    micTargetLanguage: "te",
    speakerTargetLanguage: "te",
    routeProfileId: "browser-debug",
    onlinePolicy: ONLINE_POLICIES.OFFLINE_ONLY,
    voiceProfileId: "generic:offline-default",
    preserveEmotion: true,
    ...overrides,
  };
}

function normalizeStartSessionRequest(input = {}) {
  const request = createStartSessionRequest(input);
  return {
    platform: normalizePlatform(request.platform),
    sourceLanguage: normalizeToken(request.sourceLanguage, "en"),
    autoDetectSource: request.autoDetectSource !== false,
    targetLanguage: normalizeToken(request.targetLanguage, "te"),
    sessionKind: normalizeSessionKind(request.sessionKind),
    inputDeviceId: normalizeToken(request.inputDeviceId || request.micInputDeviceId, ""),
    outputDeviceId: normalizeToken(request.outputDeviceId || request.speakerOutputDeviceId, ""),
    micInputDeviceId: normalizeToken(request.micInputDeviceId || request.inputDeviceId, ""),
    speakerOutputDeviceId: normalizeToken(request.speakerOutputDeviceId || request.outputDeviceId, ""),
    micTargetLanguage: normalizeToken(request.micTargetLanguage || request.targetLanguage, "te"),
    speakerTargetLanguage: normalizeToken(request.speakerTargetLanguage || request.targetLanguage, "te"),
    routeProfileId: normalizeToken(request.routeProfileId, "browser-debug"),
    onlinePolicy: normalizeOnlinePolicy(request.onlinePolicy),
    voiceProfileId: normalizeToken(request.voiceProfileId, "generic:offline-default"),
    preserveEmotion: request.preserveEmotion !== false,
  };
}

function createSessionEvent(type, payload = {}) {
  return {
    type,
    timestamp: new Date().toISOString(),
    ...payload,
  };
}

function normalizeToken(value, fallback) {
  const normalized = typeof value === "string" ? value.trim() : "";
  return normalized || fallback;
}

function normalizeSessionKind(value) {
  const normalized = normalizeToken(value, SESSION_KINDS.BROWSER_DEBUG)
    .toLowerCase()
    .replace(/-/g, "_");

  if (normalized === "microphone" || normalized === "system") {
    return SESSION_KINDS.DESKTOP_RUNTIME;
  }

  if (normalized === "browserdebug") {
    return SESSION_KINDS.BROWSER_DEBUG;
  }

  return Object.values(SESSION_KINDS).includes(normalized)
    ? normalized
    : SESSION_KINDS.BROWSER_DEBUG;
}

function normalizeOnlinePolicy(value) {
  const normalized = normalizeToken(value, ONLINE_POLICIES.OFFLINE_ONLY);
  return Object.values(ONLINE_POLICIES).includes(normalized)
    ? normalized
    : ONLINE_POLICIES.OFFLINE_ONLY;
}

function normalizePlatform(value) {
  const normalized = normalizeToken(value, process.platform);
  if (normalized === "win32") return "windows";
  if (normalized === "darwin") return "macos";
  return normalized;
}

module.exports = {
  ONLINE_POLICIES,
  SESSION_EVENT_TYPES,
  SESSION_KINDS,
  createSessionEvent,
  createStartSessionRequest,
  normalizeOnlinePolicy,
  normalizeSessionKind,
  normalizeStartSessionRequest,
};
