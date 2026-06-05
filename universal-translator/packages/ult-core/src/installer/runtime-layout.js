const fs = require("fs/promises");
const path = require("path");

const TRANSIENT_AUDIO_EXTENSIONS = new Set([".wav", ".mp3", ".webm", ".raw", ".pcm"]);

async function ensureRuntimeLayout(config) {
  await fs.mkdir(config.dataDir, { recursive: true });
  await fs.mkdir(config.tempDir, { recursive: true });
  await fs.mkdir(config.voiceProfilesDir, { recursive: true });
  await fs.mkdir(config.argosPackagesDir, { recursive: true });
}

async function pruneTempArtifacts(config) {
  await fs.mkdir(config.tempDir, { recursive: true });
  const entries = await fs.readdir(config.tempDir, { withFileTypes: true }).catch(() => []);
  const removedEntries = [];

  for (const entry of entries) {
    if (!entry.isFile()) {
      continue;
    }

    const extension = path.extname(entry.name).toLowerCase();
    if (!TRANSIENT_AUDIO_EXTENSIONS.has(extension)) {
      continue;
    }

    const entryPath = path.join(config.tempDir, entry.name);
    await fs.rm(entryPath, { force: true }).catch(() => {});
    removedEntries.push(entry.name);
  }

  return {
    removedCount: removedEntries.length,
    removedEntries,
  };
}

module.exports = {
  ensureRuntimeLayout,
  pruneTempArtifacts,
};
