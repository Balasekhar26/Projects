const fs = require("fs/promises");
const path = require("path");

const BUILTIN_VOICE_PROFILES = [
  { id: "builtin:alloy", label: "Alloy (OpenAI built-in)", provider: "openai", kind: "builtin" },
  { id: "builtin:ash", label: "Ash (OpenAI built-in)", provider: "openai", kind: "builtin" },
  { id: "builtin:verse", label: "Verse (OpenAI built-in)", provider: "openai", kind: "builtin" },
];

async function listVoiceProfiles(config) {
  const storedProfiles = await readVoiceProfiles(config);
  return [...storedProfiles, ...BUILTIN_VOICE_PROFILES];
}

async function getVoiceProfile(config, voiceProfileId) {
  const profiles = await listVoiceProfiles(config);
  return profiles.find((profile) => profile.id === voiceProfileId) || null;
}

async function registerLocalVoiceProfile(config, profile) {
  const existing = await readVoiceProfiles(config);
  const nextProfiles = [profile, ...existing.filter((entry) => entry.id !== profile.id)];
  await fs.mkdir(config.voiceProfilesDir, { recursive: true });
  await fs.writeFile(
    path.join(config.voiceProfilesDir, "profiles.json"),
    JSON.stringify(nextProfiles, null, 2),
    "utf8"
  );
  return profile;
}

async function readVoiceProfiles(config) {
  try {
    const raw = await fs.readFile(path.join(config.voiceProfilesDir, "profiles.json"), "utf8");
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch (error) {
    if (error && typeof error === "object" && error.code === "ENOENT") {
      return [];
    }
    throw error;
  }
}

module.exports = {
  BUILTIN_VOICE_PROFILES,
  getVoiceProfile,
  listVoiceProfiles,
  registerLocalVoiceProfile,
};
