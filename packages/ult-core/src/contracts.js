const SESSION_KINDS = Object.freeze({
  MICROPHONE: "microphone",
  SYSTEM: "system",
  BROWSER_DEBUG: "browser-debug",
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
});

function createStartSessionRequest(overrides = {}) {
  return {
    sourceLanguage: "en",
    targetLanguage: "te",
    sessionKind: SESSION_KINDS.BROWSER_DEBUG,
    inputDeviceId: "",
    outputDeviceId: "",
    routeProfileId: "browser-debug",
    onlinePolicy: ONLINE_POLICIES.AUTO,
    voiceProfileId: "builtin:alloy",
    preserveEmotion: true,
    ...overrides,
  };
}

function normalizeStartSessionRequest(input = {}) {
  const request = createStartSessionRequest(input);
  return {
    sourceLanguage: normalizeToken(request.sourceLanguage, "en"),
    targetLanguage: normalizeToken(request.targetLanguage, "te"),
    sessionKind: normalizeSessionKind(request.sessionKind),
    inputDeviceId: normalizeToken(request.inputDeviceId, ""),
    outputDeviceId: normalizeToken(request.outputDeviceId, ""),
    routeProfileId: normalizeToken(request.routeProfileId, "browser-debug"),
    onlinePolicy: normalizeOnlinePolicy(request.onlinePolicy),
    voiceProfileId: normalizeToken(request.voiceProfileId, "builtin:alloy"),
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
  const normalized = normalizeToken(value, SESSION_KINDS.BROWSER_DEBUG);
  return Object.values(SESSION_KINDS).includes(normalized)
    ? normalized
    : SESSION_KINDS.BROWSER_DEBUG;
}

function normalizeOnlinePolicy(value) {
  const normalized = normalizeToken(value, ONLINE_POLICIES.AUTO);
  return Object.values(ONLINE_POLICIES).includes(normalized)
    ? normalized
    : ONLINE_POLICIES.AUTO;
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
