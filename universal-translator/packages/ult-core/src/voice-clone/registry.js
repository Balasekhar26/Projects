const fs = require("fs/promises");
const path = require("path");
const { resolveCoreConfig } = require("../config");

const BUILTIN_VOICE_PROFILES = [
  {
    id: "generic:offline-default",
    label: "Offline Neural Default",
    provider: "local",
    kind: "generic",
    speakerLabel: "Offline Neural Default",
    status: "ready",
  },
];

async function listVoiceProfiles(config = {}) {
  const resolvedConfig = resolveCoreConfig(config);
  const storedProfiles = await readVoiceProfiles(resolvedConfig);
  return [...storedProfiles, ...BUILTIN_VOICE_PROFILES];
}

async function getVoiceProfile(config = {}, voiceProfileId) {
  const profiles = await listVoiceProfiles(config);
  return profiles.find((profile) => profile.id === voiceProfileId) || null;
}

async function registerLocalVoiceProfile(config = {}, profile) {
  const resolvedConfig = resolveCoreConfig(config);
  const existing = await readVoiceProfiles(resolvedConfig);
  const normalizedProfile = normalizeVoiceProfile(profile);
  const nextProfiles = [normalizedProfile, ...existing.filter((entry) => entry.id !== normalizedProfile.id)];
  await fs.mkdir(resolvedConfig.voiceProfilesDir, { recursive: true });
  await fs.writeFile(
    path.join(resolvedConfig.voiceProfilesDir, "profiles.json"),
    JSON.stringify(nextProfiles, null, 2),
    "utf8"
  );
  return normalizedProfile;
}

async function readVoiceProfiles(config = {}) {
  const resolvedConfig = resolveCoreConfig(config);
  try {
    const raw = await fs.readFile(path.join(resolvedConfig.voiceProfilesDir, "profiles.json"), "utf8");
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.map(normalizeVoiceProfile) : [];
  } catch (error) {
    if (error && typeof error === "object" && error.code === "ENOENT") {
      return [];
    }
    throw error;
  }
}

function normalizeVoiceProfile(profile = {}) {
  const id = typeof profile.id === "string" && profile.id.trim() ? profile.id.trim() : `voice:${Date.now()}`;
  const speakerLabel =
    typeof profile.speakerLabel === "string" && profile.speakerLabel.trim()
      ? profile.speakerLabel.trim()
      : typeof profile.label === "string" && profile.label.trim()
        ? profile.label.trim()
        : id;

  return {
    id,
    label: speakerLabel,
    speakerLabel,
    provider: typeof profile.provider === "string" && profile.provider.trim() ? profile.provider.trim() : "local",
    kind: typeof profile.kind === "string" && profile.kind.trim() ? profile.kind.trim() : "consented-clone",
    consentRecordedAt:
      typeof profile.consentRecordedAt === "string" && profile.consentRecordedAt.trim()
        ? profile.consentRecordedAt.trim()
        : null,
    consentTextVersion:
      typeof profile.consentTextVersion === "string" && profile.consentTextVersion.trim()
        ? profile.consentTextVersion.trim()
        : null,
    sampleRate: Number.isFinite(Number(profile.sampleRate)) ? Number(profile.sampleRate) : 16000,
    status: typeof profile.status === "string" && profile.status.trim() ? profile.status.trim() : "ready",
    samplePath: typeof profile.samplePath === "string" && profile.samplePath.trim() ? profile.samplePath.trim() : "",
  };
}

function isConsentedLocalVoiceProfile(profile) {
  return Boolean(
    profile &&
      profile.kind === "consented-clone" &&
      profile.status === "ready" &&
      profile.samplePath &&
      profile.consentRecordedAt &&
      profile.consentTextVersion
  );
}

module.exports = {
  BUILTIN_VOICE_PROFILES,
  getVoiceProfile,
  isConsentedLocalVoiceProfile,
  listVoiceProfiles,
  registerLocalVoiceProfile,
};
