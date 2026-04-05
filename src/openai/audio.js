const fs = require("fs/promises");
const path = require("path");

const { config } = require("../runtime");

const BUILTIN_TTS_VOICES = [
  "alloy",
  "ash",
  "ballad",
  "coral",
  "echo",
  "fable",
  "onyx",
  "nova",
  "sage",
  "shimmer",
  "verse",
  "marin",
  "cedar",
];

const voiceStorePath = path.join(config.tempDir, "openai-custom-voices.json");

function assertOpenAiApiKey() {
  if (!config.openAiApiKey) {
    throw new Error("OPENAI_API_KEY is not configured.");
  }
}

function getAuthorizationHeaders(extraHeaders = {}) {
  assertOpenAiApiKey();
  return {
    Authorization: `Bearer ${config.openAiApiKey}`,
    ...extraHeaders,
  };
}

async function readStoredCustomVoices() {
  try {
    const raw = await fs.readFile(voiceStorePath, "utf8");
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch (error) {
    if (error && typeof error === "object" && error.code === "ENOENT") {
      return [];
    }
    throw error;
  }
}

async function writeStoredCustomVoices(voices) {
  await fs.mkdir(path.dirname(voiceStorePath), { recursive: true });
  await fs.writeFile(voiceStorePath, JSON.stringify(voices, null, 2), "utf8");
}

async function rememberCustomVoice(voice) {
  const existingVoices = await readStoredCustomVoices();
  const dedupedVoices = existingVoices.filter((entry) => entry.id !== voice.id);
  dedupedVoices.unshift(voice);
  await writeStoredCustomVoices(dedupedVoices.slice(0, 20));
}

async function listAvailableTtsVoices() {
  const storedCustomVoices = await readStoredCustomVoices();
  const builtinVoices = BUILTIN_TTS_VOICES.map((voiceId) => ({
    id: voiceId,
    label: `${voiceId} (OpenAI built-in)`,
    kind: "builtin",
  }));

  const customVoices = storedCustomVoices.map((voice) => ({
    id: voice.id,
    label: `${voice.name || voice.id} (Custom clone)`,
    kind: "custom",
  }));

  return [...customVoices, ...builtinVoices];
}

async function createVoiceConsent({ name, language, file }) {
  assertOpenAiApiKey();

  const formData = new FormData();
  formData.append("name", name);
  formData.append("language", language);
  formData.append("recording", file, file.name || "consent.wav");

  const response = await fetch("https://api.openai.com/v1/audio/voice_consents", {
    method: "POST",
    headers: getAuthorizationHeaders(),
    body: formData,
  });

  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(payload?.error?.message || "Unable to create voice consent.");
  }

  return payload;
}

async function createCustomVoice({ name, consentId, file }) {
  assertOpenAiApiKey();

  const formData = new FormData();
  formData.append("name", name);
  formData.append("consent", consentId);
  formData.append("audio_sample", file, file.name || "voice-sample.wav");

  const response = await fetch("https://api.openai.com/v1/audio/voices", {
    method: "POST",
    headers: getAuthorizationHeaders(),
    body: formData,
  });

  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(payload?.error?.message || "Unable to create custom voice.");
  }

  await rememberCustomVoice({
    id: payload.id,
    name: payload.name || name,
    consentId,
    createdAt: new Date().toISOString(),
  });

  return payload;
}

async function synthesizeSpeech({
  input,
  voice,
  instructions,
  language,
  speed,
  format = "wav",
}) {
  assertOpenAiApiKey();

  const response = await fetch("https://api.openai.com/v1/audio/speech", {
    method: "POST",
    headers: getAuthorizationHeaders({
      "Content-Type": "application/json",
    }),
    body: JSON.stringify({
      model: config.openAiTtsModel,
      voice: voice.startsWith("voice_") ? { id: voice } : voice,
      input,
      instructions,
      language,
      format,
      speed,
    }),
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`OpenAI speech generation failed: ${errorText}`);
  }

  return Buffer.from(await response.arrayBuffer());
}

module.exports = {
  BUILTIN_TTS_VOICES,
  createCustomVoice,
  createVoiceConsent,
  listAvailableTtsVoices,
  synthesizeSpeech,
};
