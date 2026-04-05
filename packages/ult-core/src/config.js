const path = require("path");
const fs = require("fs");
const os = require("os");

function getCoreConfig() {
  const workspaceRootDir = process.env.ULT_ROOT_DIR || process.cwd();
  const packagedRuntimeDir = resolvePackagedRuntimeDir();
  const runtimeRootDir = process.env.ULT_RUNTIME_ROOT_DIR || packagedRuntimeDir || workspaceRootDir;
  const scriptsDir = resolveDirectory(runtimeRootDir, ["Scripts", "scripts"]);
  const modelsDir = path.join(runtimeRootDir, "models");
  const dataDir = process.env.ULT_DATA_DIR || resolveDataDir(workspaceRootDir, packagedRuntimeDir);
  const tempDir = process.env.TEMP_AUDIO_DIR || path.join(dataDir, "temp");
  const usesExternalWritableRuntime = Boolean(packagedRuntimeDir);

  return {
    rootDir: runtimeRootDir,
    workspaceRootDir,
    runtimeRootDir,
    scriptsDir,
    modelsDir,
    dataDir,
    tempDir,
    pythonPath: process.env.PYTHON_PATH || path.join(scriptsDir, "python.exe"),
    soxPath:
      process.env.SOX_PATH ||
      path.join(runtimeRootDir, fs.existsSync(path.join(runtimeRootDir, "sox")) ? "sox" : "sox-14.4.2", "sox.exe"),
    whisperWorkerPath:
      process.env.WHISPER_WORKER_PATH || path.join(scriptsDir, "whisper_stream_worker.py"),
    whisperModelPath:
      process.env.WHISPER_MODEL_PATH || path.join(modelsDir, "whisper_tiny"),
    argosWorkerPath:
      process.env.ARGOS_WORKER_PATH || path.join(scriptsDir, "argos_translate_worker.py"),
    argosEnsurePairPath:
      process.env.ARGOS_ENSURE_PAIR_PATH || path.join(scriptsDir, "ensure_argos_pair.py"),
    xttsWorkerPath:
      process.env.XTTS_WORKER_PATH || path.join(scriptsDir, "xtts_synthesize_worker.py"),
    speakScriptPath:
      process.env.SPEAKER_SCRIPT_PATH || path.join(scriptsDir, "speak.ps1"),
    topologyScriptPath:
      process.env.DEVICE_TOPOLOGY_SCRIPT_PATH || path.join(runtimeRootDir, "tools", "list-device-topology.ps1"),
    openAiApiKey: process.env.OPENAI_API_KEY || "",
    openAiTtsModel: process.env.OPENAI_TTS_MODEL || "gpt-4o-mini-tts",
    ttsVoiceName: process.env.TTS_VOICE_NAME || process.env.OPENAI_TTS_VOICE || "alloy",
    ttsLanguage: process.env.OPENAI_TTS_LANGUAGE || "",
    ttsOutputDeviceName: process.env.TTS_OUTPUT_DEVICE || "",
    sourceLanguage: process.env.SOURCE_LANGUAGE || "en",
    targetLanguage: process.env.TARGET_LANGUAGE || "te",
    onlinePolicy: process.env.ONLINE_POLICY || "auto",
    sampleRate: getEnvNumber("AUDIO_SAMPLE_RATE", 16000),
    channels: getEnvNumber("AUDIO_CHANNELS", 1),
    bytesPerSample: 2,
    chunkDurationMs: getEnvNumber("AUDIO_CHUNK_MS", 1000),
    minChunkDurationMs: getEnvNumber("MIN_AUDIO_CHUNK_MS", 600),
    overlapMs: getEnvNumber("AUDIO_OVERLAP_MS", 200),
    virtualDeviceName: process.env.VIRTUAL_AUDIO_DEVICE || "CABLE Output (VB-Audio Virtual Cable)",
    voiceProfilesDir: usesExternalWritableRuntime ? path.join(dataDir, "voice-profiles") : path.join(modelsDir, "voice-profiles"),
    argosPackagesDir: usesExternalWritableRuntime ? path.join(dataDir, "argos") : path.join(modelsDir, "argos"),
  };
}

function getEnvNumber(name, fallback) {
  const rawValue = process.env[name];
  if (!rawValue) {
    return fallback;
  }

  const parsedValue = Number(rawValue);
  return Number.isFinite(parsedValue) ? parsedValue : fallback;
}

function resolveDirectory(rootDir, candidates) {
  for (const candidate of candidates) {
    const fullPath = path.join(rootDir, candidate);
    if (fs.existsSync(fullPath)) {
      return fullPath;
    }
  }

  return path.join(rootDir, candidates[0]);
}

function resolvePackagedRuntimeDir() {
  if (!process.resourcesPath) {
    return "";
  }

  const runtimeDir = path.join(process.resourcesPath, "runtime");
  return fs.existsSync(runtimeDir) ? runtimeDir : "";
}

function resolveDataDir(workspaceRootDir, packagedRuntimeDir) {
  if (!packagedRuntimeDir) {
    return path.join(workspaceRootDir, ".ult-runtime");
  }

  const baseDir = process.env.LOCALAPPDATA || process.env.APPDATA || os.tmpdir();
  return path.join(baseDir, "ULT Translator", ".ult-runtime");
}

module.exports = {
  getCoreConfig,
};
