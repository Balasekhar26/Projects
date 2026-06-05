const fs = require("fs");
const path = require("path");
const os = require("os");

function detectHardwareProfile() {
  const totalMemGb = Math.round((os.totalmem() / (1024 ** 3)) * 10) / 10;
  const cpuCount = os.cpus().length;

  let profileId = "balanced";
  if (totalMemGb <= 8 || cpuCount <= 4) {
    profileId = "compact";
  } else if (totalMemGb >= 24 && cpuCount >= 8) {
    profileId = "performance";
  }

  return {
    profileId,
    cpuCount,
    totalMemGb,
    gpu: {
      name: process.env.ULT_GPU_NAME || "unknown",
      adapterRamGb: Number(process.env.ULT_GPU_RAM_GB || 0),
    },
  };
}

function buildLanguagePairPackId(sourceLanguage, targetLanguage) {
  return `pair:${sourceLanguage || "auto"}-${targetLanguage || "auto"}`;
}

function listModelPacks(options = {}) {
  const rootDir = options.rootDir || process.cwd();
  const sourceLanguage = normalizeLanguage(options.sourceLanguage || "en");
  const targetLanguage = normalizeLanguage(options.targetLanguage || "te");
  const pairPackId = buildLanguagePairPackId(sourceLanguage, targetLanguage);
  const modelsDir = path.join(rootDir, "models");
  const argosDir = options.argosPackagesDir || path.join(modelsDir, "argos");
  const voiceProfilesDir = options.voiceProfilesDir || path.join(modelsDir, "voice-profiles");
  const whisperTinyPath = path.join(modelsDir, "whisper_tiny", "model.bin");
  const scriptsDir = options.scriptsDir || resolveScriptsDir(rootDir);
  const voiceProfilesPath = path.join(voiceProfilesDir, "profiles.json");

  const packs = [
    {
      id: "runtime:base",
      label: "Base runtime",
      description: "Shared Node, Python, SoX, and PowerShell runtime helpers.",
      installState: fileExists(path.join(scriptsDir, "python.exe")) ? "installed" : "missing",
      transport: "bundled",
    },
    {
      id: "stt:whisper-tiny",
      label: "Whisper tiny",
      description: "Low-latency offline speech recognition model.",
      installState: fileExists(whisperTinyPath) ? "installed" : "missing",
      transport: "bundled",
    },
    {
      id: "translation:argos-runtime",
      label: "Argos Translate runtime",
      description: "Offline translation engine and downloaded language packages.",
      installState: fileExists(path.join(scriptsDir, "argos_translate_worker.py")) ? "installed" : "missing",
      transport: "download-on-demand",
    },
    {
      id: "voice:xtts",
      label: "XTTS voice cloning",
      description: "Best-effort local voice preservation for consented profiles.",
      installState: fileExists(path.join(scriptsDir, "xtts_synthesize_worker.py"))
        ? fileExists(voiceProfilesPath)
          ? "installed"
          : "ready-on-first-use"
        : "missing",
      transport: "download-on-demand",
    },
    {
      id: pairPackId,
      label: `${sourceLanguage} -> ${targetLanguage} offline pair`,
      description: "Language-pair offline translation pack.",
      installState: hasArgosLanguagePair(argosDir, sourceLanguage, targetLanguage) ? "installed" : "downloadable",
      transport: "download-on-demand",
    },
  ];

  return packs;
}

function listInstalledArgosPairs(argosDir) {
  try {
    return fs
      .readdirSync(argosDir, { withFileTypes: true })
      .filter((entry) => entry.isDirectory())
      .map((entry) => path.join(argosDir, entry.name, "metadata.json"))
      .filter((metadataPath) => fileExists(metadataPath))
      .map(readArgosMetadata)
      .filter(Boolean)
      .map((metadata) => ({
        sourceLanguage: normalizeOptionalLanguage(metadata.from_code),
        targetLanguage: normalizeOptionalLanguage(metadata.to_code),
      }))
      .filter((entry) => entry.sourceLanguage && entry.targetLanguage);
  } catch {
    return [];
  }
}

function hasArgosLanguagePair(argosDir, sourceLanguage, targetLanguage) {
  const normalizedSource = normalizeLanguage(sourceLanguage);
  const normalizedTarget = normalizeLanguage(targetLanguage);

  return listInstalledArgosPairs(argosDir).some(
    (entry) =>
      entry.sourceLanguage === normalizedSource && entry.targetLanguage === normalizedTarget
  );
}

function fileExists(targetPath) {
  try {
    return fs.existsSync(targetPath);
  } catch {
    return false;
  }
}

function normalizeLanguage(value) {
  return typeof value === "string" && value.trim() ? value.trim().toLowerCase() : "en";
}

function normalizeOptionalLanguage(value) {
  return typeof value === "string" && value.trim() ? value.trim().toLowerCase() : "";
}

function readArgosMetadata(metadataPath) {
  try {
    const raw = fs.readFileSync(metadataPath, "utf8");
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

function resolveScriptsDir(rootDir) {
  const uppercasePath = path.join(rootDir, "Scripts");
  if (fileExists(uppercasePath)) {
    return uppercasePath;
  }

  return path.join(rootDir, "scripts");
}

module.exports = {
  buildLanguagePairPackId,
  detectHardwareProfile,
  hasArgosLanguagePair,
  listInstalledArgosPairs,
  listModelPacks,
};
