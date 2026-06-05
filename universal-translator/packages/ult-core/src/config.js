const path = require("path");
const fs = require("fs");
const os = require("os");
const { spawnSync } = require("child_process");

function getCoreConfig(overrides = {}) {
  const env = {
    ...process.env,
    ...Object.entries(overrides).reduce((acc, [key, value]) => {
      if (typeof value === "string") {
        acc[key] = value;
      }
      return acc;
    }, {}),
  };

  const resolvedRoot = path.resolve(__dirname, "..", "..", "..");
  const envRoot = normalizeString(env.ULT_ROOT_DIR);
  const workspaceRootDir = envRoot || resolvedRoot;
  const packagedRuntimeDir = resolvePackagedRuntimeDir();
  const runtimeRootDir =
    normalizeString(overrides.runtimeRootDir) ||
    normalizeString(env.ULT_RUNTIME_ROOT_DIR) ||
    packagedRuntimeDir ||
    workspaceRootDir;
  const scriptsDir = normalizeString(overrides.scriptsDir) || resolveDirectory(runtimeRootDir, ["Scripts", "scripts"]);
  const modelsDir = normalizeString(overrides.modelsDir) || path.join(runtimeRootDir, "models");
  const dataDir =
    normalizeString(overrides.dataDir) ||
    normalizeString(env.ULT_DATA_DIR) ||
    resolveDataDir(workspaceRootDir, packagedRuntimeDir);
  const tempDir = normalizeString(overrides.tempDir) || normalizeString(env.TEMP_AUDIO_DIR) || path.join(dataDir, "temp");
  const usesExternalWritableRuntime = Boolean(packagedRuntimeDir);
  const venvDir = normalizeString(overrides.venvDir) || path.join(workspaceRootDir, "venv");
  const pythonExePath =
    normalizeString(overrides.pythonPath) ||
    normalizeString(env.PYTHON_PATH) ||
    resolvePythonPath({ venvDir, scriptsDir });
  const runtimeTier = "free";
  const latencyProfile = (
    normalizeString(overrides.latencyProfile) ||
    normalizeString(env.ULT_LATENCY_PROFILE) ||
    "ultra-low"
  ).toLowerCase();
  const lowLatencyDefaults = getLatencyDefaults(latencyProfile);
  const forceFreeOnly = true;

  return {
    rootDir: runtimeRootDir,
    workspaceRootDir,
    runtimeRootDir,
    scriptsDir,
    modelsDir,
    dataDir,
    tempDir,
    venvDir,
    pythonPath: pythonExePath,
    soxPath:
      normalizeString(overrides.soxPath) ||
      normalizeString(env.SOX_PATH) ||
      path.join(runtimeRootDir, fs.existsSync(path.join(runtimeRootDir, "sox")) ? "sox" : "sox-14.4.2", "sox.exe"),
    whisperWorkerPath:
      normalizeString(overrides.whisperWorkerPath) ||
      normalizeString(env.WHISPER_WORKER_PATH) ||
      path.join(scriptsDir, "whisper_stream_worker.py"),
    voskWorkerPath:
      normalizeString(overrides.voskWorkerPath) ||
      normalizeString(env.VOSK_WORKER_PATH) ||
      path.join(scriptsDir, "vosk_stream_worker.py"),
    whisperModelPath:
      normalizeString(overrides.whisperModelPath) ||
      normalizeString(env.WHISPER_MODEL_PATH) ||
      path.join(modelsDir, "whisper_tiny"),
    whisperHttpPort: getNumber(overrides.whisperHttpPort, env.WHISPER_HTTP_PORT, 8765),
    whisperStartupTimeoutMs: getNumber(
      overrides.whisperStartupTimeoutMs,
      env.WHISPER_HTTP_STARTUP_TIMEOUT_MS,
      45000
    ),
    voskModelPath:
      normalizeString(overrides.voskModelPath) ||
      normalizeString(env.VOSK_MODEL_PATH) ||
      path.join(modelsDir, "vosk-model-small-en-us-0.15"),
    argosWorkerPath:
      normalizeString(overrides.argosWorkerPath) ||
      normalizeString(env.ARGOS_WORKER_PATH) ||
      path.join(scriptsDir, "argos_translate_worker.py"),
    googleTranslateWorkerPath:
      normalizeString(overrides.googleTranslateWorkerPath) ||
      normalizeString(env.GOOGLE_TRANSLATE_WORKER_PATH) ||
      path.join(scriptsDir, "google_translate_worker.py"),
    gTtsWorkerPath:
      normalizeString(overrides.gTtsWorkerPath) ||
      normalizeString(env.GTTS_WORKER_PATH) ||
      path.join(scriptsDir, "gtts_worker.py"),
    argosEnsurePairPath:
      normalizeString(overrides.argosEnsurePairPath) ||
      normalizeString(env.ARGOS_ENSURE_PAIR_PATH) ||
      path.join(scriptsDir, "ensure_argos_pair.py"),
    xttsWorkerPath:
      normalizeString(overrides.xttsWorkerPath) ||
      normalizeString(env.XTTS_WORKER_PATH) ||
      path.join(scriptsDir, "xtts_synthesize_worker.py"),
    prosodyExtractorPath:
      normalizeString(overrides.prosodyExtractorPath) ||
      normalizeString(env.PROSODY_EXTRACTOR_PATH) ||
      path.join(scriptsDir, "prosody_extractor_worker.py"),
    prosodyTransferPath:
      normalizeString(overrides.prosodyTransferPath) ||
      normalizeString(env.PROSODY_TRANSFER_PATH) ||
      path.join(scriptsDir, "prosody_transfer_worker.py"),
    audioSeparatorPath:
      normalizeString(overrides.audioSeparatorPath) ||
      normalizeString(env.AUDIO_SEPARATOR_PATH) ||
      path.join(scriptsDir, "audio_separator_worker.py"),
    marianWorkerPath:
      normalizeString(overrides.marianWorkerPath) ||
      normalizeString(env.MARIAN_WORKER_PATH) ||
      path.join(scriptsDir, "marian_translate_worker.py"),
    edgeTtsWorkerPath:
      normalizeString(overrides.edgeTtsWorkerPath) ||
      normalizeString(env.EDGE_TTS_WORKER_PATH) ||
      path.join(scriptsDir, "edge_tts_worker.py"),
    speakScriptPath:
      normalizeString(overrides.speakScriptPath) ||
      normalizeString(env.SPEAKER_SCRIPT_PATH) ||
      path.join(scriptsDir, "speak.ps1"),
    topologyScriptPath:
      normalizeString(overrides.topologyScriptPath) ||
      normalizeString(env.DEVICE_TOPOLOGY_SCRIPT_PATH) ||
      path.join(runtimeRootDir, "tools", "list-device-topology.ps1"),
    openAiApiKey: "",
    deepLApiKey: "",
    nvidiaNimApiKey: "",
    nvidiaNimEndpoint: "",
    nvidiaNimModel: "",
    nvidiaNimTranslationModel: "",
    nvidiaNimGeneralModel: "",
    nvidiaNimTimeoutMs: getNumber(overrides.nvidiaNimTimeoutMs, env.NVIDIA_NIM_TIMEOUT_MS, 30000),
    nvidiaNimMaxTokens: getNumber(overrides.nvidiaNimMaxTokens, env.NVIDIA_NIM_MAX_TOKENS, 1024),
    translationProvider:
      "local",
    openAiTtsModel: "",
    elevenlabsApiKey: "",
    elevenlabsVoiceId: "",
    ttsVoiceName:
      normalizeString(overrides.ttsVoiceName) ||
      normalizeString(env.TTS_VOICE_NAME) ||
      "alloy",
    ttsLanguage: normalizeString(overrides.ttsLanguage),
    ttsOutputDeviceName: normalizeString(overrides.ttsOutputDeviceName) || normalizeString(env.TTS_OUTPUT_DEVICE),
    sourceLanguage: normalizeString(overrides.sourceLanguage) || normalizeString(env.SOURCE_LANGUAGE) || "en",
    targetLanguage: normalizeString(overrides.targetLanguage) || normalizeString(env.TARGET_LANGUAGE) || "te",
    onlinePolicy: "offline-only",
    runtimeTier,
    latencyProfile,
    allowExperimentalOnline: false,
    freeOnlyProviders: true,
    enableVoskRealtime:
      parseBoolean(overrides.enableVoskRealtime, parseBoolean(env.ULT_ENABLE_VOSK_REALTIME, false)),
    sampleRate: getNumber(overrides.sampleRate, env.AUDIO_SAMPLE_RATE, 16000),
    channels: getNumber(overrides.channels, env.AUDIO_CHANNELS, 1),
    bytesPerSample: 2,
    chunkDurationMs: getNumber(overrides.chunkDurationMs, env.AUDIO_CHUNK_MS, lowLatencyDefaults.chunkDurationMs),
    minChunkDurationMs: getNumber(overrides.minChunkDurationMs, env.MIN_AUDIO_CHUNK_MS, lowLatencyDefaults.minChunkDurationMs),
    overlapMs: getNumber(overrides.overlapMs, env.AUDIO_OVERLAP_MS, lowLatencyDefaults.overlapMs),
    voiceIdentityWindowMs: getNumber(overrides.voiceIdentityWindowMs, env.VOICE_IDENTITY_WINDOW_MS, 5000),
    voiceIdentityBlendFactor: getNumber(overrides.voiceIdentityBlendFactor, env.VOICE_IDENTITY_BLEND_FACTOR, 0.15),
    realtimeSilenceRmsThreshold: getNumber(overrides.realtimeSilenceRmsThreshold, env.REALTIME_SILENCE_RMS_THRESHOLD, 0.008),
    realtimeSpeechRmsThreshold: getNumber(overrides.realtimeSpeechRmsThreshold, env.REALTIME_SPEECH_RMS_THRESHOLD, 0.014),
    streamingSegmenter: parseBoolean(overrides.streamingSegmenter, parseBoolean(env.STREAMING_SEGMENTER, false)),
    streamingWindowMs: getNumber(overrides.streamingWindowMs, env.STREAMING_WINDOW_MS, lowLatencyDefaults.streamingWindowMs),
    streamingHopMs: getNumber(overrides.streamingHopMs, env.STREAMING_HOP_MS, lowLatencyDefaults.streamingHopMs),
    streamingCapacityMs: getNumber(overrides.streamingCapacityMs, env.STREAMING_CAPACITY_MS, 5000),
    streamingSkipSilentWindows: parseBoolean(overrides.streamingSkipSilentWindows, parseBoolean(env.STREAMING_SKIP_SILENT_WINDOWS, false)),
    realtimeMaxQueueDepth: getNumber(overrides.realtimeMaxQueueDepth, env.REALTIME_MAX_QUEUE_DEPTH, 4),
    realtimeTargetLatencyMs: getNumber(overrides.realtimeTargetLatencyMs, env.REALTIME_TARGET_LATENCY_MS, 0),
    realtimeForceCommitMs: getNumber(overrides.realtimeForceCommitMs, env.REALTIME_FORCE_COMMIT_MS, lowLatencyDefaults.forceCommitMs),
    realtimeSpeechConfidenceThreshold: getNumber(overrides.realtimeSpeechConfidenceThreshold, env.REALTIME_SPEECH_CONFIDENCE_THRESHOLD, 0.55),
    realtimeUtteranceMaxGapMs: getNumber(overrides.realtimeUtteranceMaxGapMs, env.REALTIME_UTTERANCE_MAX_GAP_MS, 1200),
    realtimeUtteranceSimilarityThreshold: getNumber(overrides.realtimeUtteranceSimilarityThreshold, env.REALTIME_UTTERANCE_SIMILARITY_THRESHOLD, 0.35),
    skipAllVadSilence: parseBoolean(overrides.skipAllVadSilence, parseBoolean(env.SKIP_ALL_VAD_SILENCE, false)),
    strictSpeechConfidenceGate: parseBoolean(overrides.strictSpeechConfidenceGate, parseBoolean(env.STRICT_SPEECH_CONFIDENCE_GATE, false)),
    maxRealtimeLatencyMs: getNumber(overrides.maxRealtimeLatencyMs, env.MAX_REALTIME_LATENCY_MS, lowLatencyDefaults.maxRealtimeLatencyMs),
    virtualDeviceName:
      normalizeString(overrides.virtualDeviceName) ||
      normalizeString(env.VIRTUAL_AUDIO_DEVICE) ||
      "CABLE Output (VB-Audio Virtual Cable)",
    voiceProfilesDir:
      normalizeString(overrides.voiceProfilesDir) ||
      (usesExternalWritableRuntime ? path.join(dataDir, "voice-profiles") : path.join(modelsDir, "voice-profiles")),
    argosPackagesDir:
      normalizeString(overrides.argosPackagesDir) ||
      (usesExternalWritableRuntime ? path.join(dataDir, "argos") : path.join(modelsDir, "argos")),
  };
}

function resolveCoreConfig(overrides = {}) {
  return getCoreConfig(overrides);
}

function getPythonEnv(configInput = {}) {
  const config = resolveCoreConfig(configInput);
  const env = { ...process.env };

  if (config.venvDir && fs.existsSync(config.venvDir)) {
    const venvScripts = path.join(config.venvDir, "Scripts");
    env.PATH = venvScripts + ";" + (env.PATH || "");
    env.VIRTUAL_ENV = config.venvDir;
    delete env.PYTHONHOME;
  }

  return env;
}

function resolvePythonPath({ venvDir, scriptsDir }) {
  if (venvDir && fs.existsSync(path.join(venvDir, "pyvenv.cfg"))) {
    const venvPython = path.join(venvDir, "Scripts", "python.exe");
    if (isRunnablePython(venvPython)) {
      return venvPython;
    }
  }

  const scriptsPython = path.join(scriptsDir, "python.exe");
  if (isRunnablePython(scriptsPython)) {
    return scriptsPython;
  }

  if (isRunnablePython("python")) {
    return "python";
  }

  if (isRunnablePython("py")) {
    return "py";
  }

  return scriptsPython;
}

function isRunnablePython(command) {
  try {
    const result = spawnSync(command, ["--version"], {
      encoding: "utf8",
      shell: false,
      timeout: 3000,
    });
    return result.status === 0;
  } catch {
    return false;
  }
}

function getNumber(overrideValue, envValue, fallback) {
  const value = overrideValue ?? envValue;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function normalizeString(value) {
  return typeof value === "string" ? value.trim() : "";
}

function parseBoolean(value, fallback) {
  if (typeof value === "boolean") return value;
  if (typeof value === "string") {
    if (value.trim().toLowerCase() === "true") return true;
    if (value.trim().toLowerCase() === "false") return false;
  }
  return fallback;
}

function getLatencyDefaults(profile) {
  if (profile === "stable") {
    return {
      chunkDurationMs: 1200,
      minChunkDurationMs: 500,
      overlapMs: 160,
      streamingWindowMs: 700,
      streamingHopMs: 200,
      forceCommitMs: 240,
      maxRealtimeLatencyMs: 1500,
    };
  }

  if (profile === "balanced") {
    return {
      chunkDurationMs: 700,
      minChunkDurationMs: 300,
      overlapMs: 100,
      streamingWindowMs: 480,
      streamingHopMs: 140,
      forceCommitMs: 180,
      maxRealtimeLatencyMs: 900,
    };
  }

  return {
    chunkDurationMs: 420,
    minChunkDurationMs: 160,
    overlapMs: 60,
    streamingWindowMs: 320,
    streamingHopMs: 100,
    forceCommitMs: 120,
    maxRealtimeLatencyMs: 500,
  };
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
  getPythonEnv,
  resolveCoreConfig,
};
