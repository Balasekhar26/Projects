const path = require("path");
const fs = require("fs");
const { app, BrowserWindow, ipcMain } = require("electron");

const dotenvPath = path.join(__dirname, "..", ".env");
if (fs.existsSync(dotenvPath)) require("dotenv").config({ path: dotenvPath });

const { getCoreConfig } = require("../packages/ult-core/src/config");
const { listDeviceTopology } = require("../packages/ult-core/src/device-control/topology");
const { runBootstrapInspection } = require("../packages/ult-core/src/installer/bootstrap");
const { listVoiceProfiles, isConsentedLocalVoiceProfile } = require("../packages/ult-core/src/voice-clone/registry");
const { HybridSttEngine } = require("../packages/ult-core/src/stt-engine");
const { WhisperHttpClient } = require("../src/stt/whisper-http-client");
const { HybridTranslationEngine } = require("../packages/ult-core/src/translation-engine");
const { TieredSpeechEngine } = require("../packages/ult-core/src/tts-engine/tiered-speaker");
const { AudioBlocker } = require("../packages/ult-core/src/audio-blocking/blocker");
const { validateRouteProfile } = require("../packages/ult-core/src/audio-routing/validator");
const { VirtualAudioCapture } = require("../src/audio/capture");
const { MicrophoneCapture } = require("../modules/audio-capture");
const { RealtimeTranslator } = require("../src/pipeline/realtime-translator");
const { writePcmAsWavFile } = require("../src/utils/wav");

// Import database
const Database = require("better-sqlite3");
const dbPath = path.join(__dirname, "..", ".ult-runtime", "universal-translator.db");
const sqlite = new Database(dbPath);
sqlite.pragma("journal_mode = WAL");
sqlite.pragma("foreign_keys = ON");

const CABLE_OUTPUT = "CABLE Output (VB-Audio Virtual Cable)";
const LINE1_IN = "Line 1 (Virtual Audio Cable)";
const DESKTOP_SETTINGS_PATH = path.join(__dirname, "..", ".ult-runtime", "desktop-settings.json");

let mainWindow = null;
let isRunning = false;
let runtimeCache = null;
let speakerPipeline = null;
let micPipeline = null;
let micWatcher = null;
let audioBlocker = null;
let sttSpk = null;
let sttMic = null;
let whisperReady = false;
const MIC_WAKE_ENERGY_THRESHOLD = 0.01;
const MIC_STANDBY_TIMEOUT_MS = 1500;
const IS_WINDOWS = process.platform === "win32";

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function getProviderReadiness(config) {
  return {
    nvidia: false,
    deepL: false,
    openAi: false,
    elevenlabs: false,
  };
}

function canUseOnlineProviders(config) {
  return false;
}

function pickPreferredVoiceProfile(runtime) {
  const profiles = Array.isArray(runtime?.voiceProfiles) ? runtime.voiceProfiles : [];
  return profiles.find((profile) => isConsentedLocalVoiceProfile(profile)) || null;
}

function getDefaultDesktopSettings() {
  return {
    mode: "free",
    translationProvider: "local",
    nvidiaNimApiKey: "",
    nvidiaNimModel: "",
    deepLApiKey: "",
    openAiApiKey: "",
    elevenlabsApiKey: "",
    elevenlabsVoiceId: "",
  };
}

function readDesktopSettings() {
  try {
    const raw = fs.readFileSync(DESKTOP_SETTINGS_PATH, "utf8");
    return {
      ...getDefaultDesktopSettings(),
      ...JSON.parse(raw),
    };
  } catch {
    return getDefaultDesktopSettings();
  }
}

function writeDesktopSettings(nextSettings) {
  fs.mkdirSync(path.dirname(DESKTOP_SETTINGS_PATH), { recursive: true });
  fs.writeFileSync(
    DESKTOP_SETTINGS_PATH,
    JSON.stringify(
      {
        ...getDefaultDesktopSettings(),
        ...nextSettings,
      },
      null,
      2
    ),
    "utf8"
  );
}

function getRuntimeConfig(overrides = {}) {
  const desktopSettings = readDesktopSettings();
  const merged = {
    ...overrides,
    runtimeTier: "free",
    nvidiaNimApiKey: "",
    nvidiaNimModel: "",
    translationProvider: "local",
    deepLApiKey: "",
    openAiApiKey: "",
    elevenlabsApiKey: "",
    elevenlabsVoiceId: "",
    onlinePolicy: "offline-only",
  };
  merged.freeOnlyProviders = true;
  merged.allowExperimentalOnline = false;
  return getCoreConfig(merged);
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 960,
    height: 700,
    minWidth: 700,
    minHeight: 520,
    backgroundColor: "#07111d",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  mainWindow.loadFile(path.join(__dirname, "index.html"));
  mainWindow.on("closed", () => {
    mainWindow = null;
  });
}

function sendLog(msg, level = "info") {
  if (!mainWindow || mainWindow.isDestroyed()) return;
  mainWindow.webContents.send("translator:log", {
    level,
    message: msg,
    timestamp: new Date().toLocaleTimeString(),
  });
}

function sendEvent(payload) {
  if (!mainWindow || mainWindow.isDestroyed()) return;
  mainWindow.webContents.send("translator:event", payload);
}

function broadcastState() {
  if (!mainWindow || mainWindow.isDestroyed()) return;
  mainWindow.webContents.send("translator:state", { isRunning });
}

async function warmWhisper(config) {
  if (whisperReady) return;

  // Use HTTP client for both engines — 15x faster than pipe IPC
  if (!sttSpk) sttSpk = new HybridSttEngine(config);
  if (!sttMic) sttMic = new HybridSttEngine(config);

  const warmWav = path.join(config.tempDir, "warmup.wav");
  fs.mkdirSync(config.tempDir, { recursive: true });
  await writePcmAsWavFile(warmWav, Buffer.alloc(16000 * 3), {
    sampleRate: 16000,
    channels: 1,
    bitsPerSample: 16,
  });

  await Promise.all([
    sttSpk.transcribeChunk({
      audioPath: warmWav,
      sourceLanguage: "en",
      targetLanguage: "en",
      onlinePolicy: "auto",
    }),
    sttMic.transcribeChunk({
      audioPath: warmWav,
      sourceLanguage: "en",
      targetLanguage: "en",
      onlinePolicy: "auto",
    }),
  ]);

  try { fs.unlinkSync(warmWav); } catch {}

  whisperReady = true;
  sendLog("Whisper ready — both engines warmed", "status");
}

async function loadRuntime() {
  const config = getRuntimeConfig();
  const [topology, bootstrap, voiceProfiles] = await Promise.all([
    listDeviceTopology(config),
    runBootstrapInspection(config),
    listVoiceProfiles(config),
  ]);

  runtimeCache = { topology, bootstrap, voiceProfiles };

  if (!audioBlocker) {
    audioBlocker = new AudioBlocker(config);
    audioBlocker.on("debug", (m) => sendLog(`[blocker] ${m}`, "info"));
    audioBlocker.on("status", (m) => sendLog(`[blocker] ${m}`, "status"));
    audioBlocker.on("error", (e) => sendLog(`[blocker] ${e.message}`, "error"));
  }

  warmWhisper(config).catch(() => {});

  const warmTts = new TieredSpeechEngine(config);
  warmTts.warmup({ language: "en", outputDeviceName: "" }).catch((error) => {
    sendLog(`TTS warmup skipped: ${error.message}`, "info");
  });
  setTimeout(() => warmTts.stop(), 5000);

  const warmTrans = new HybridTranslationEngine(config);
  warmTrans
    .translate({
      transcript: "hello",
      sourceLanguage: "en",
      targetLanguage: "te",
      onlinePolicy: "auto",
    })
    .then(() => {
      sendLog("MarianMT ready - Telugu warmed", "status");
      warmTrans.stop();
    })
    .catch(() => {
      warmTrans.stop();
    });

  return runtimeCache;
}

function buildPipeline(pipelineConfig, captureInstance, sttEngine, label) {
  const pipeline = new RealtimeTranslator({
    config: pipelineConfig,
    capture: captureInstance,
    sttClient: sttEngine,
    translator: new HybridTranslationEngine(pipelineConfig),
    speaker: new TieredSpeechEngine(pipelineConfig),
  });

  pipeline.on("status", (msg) => sendLog(`[${label}] ${msg}`, "status"));
  pipeline.on("debug", (msg) => sendLog(`[${label}] ${msg}`, "info"));
  pipeline.on("translation", (event) => {
    sendEvent({ type: "final_translation", source: label, ...event });
    sendLog(
      `[${label}] ${event.mode === "tentative" ? "partial" : "translated"}: ${event.translatedText}`,
      event.mode === "tentative" ? "info" : "success"
    );
  });
  pipeline.on("latency", (e) => {
    sendLog(`[${label}] chunk ${e.chunkNumber} - ${e.latencyMs}ms`, "status");
    sendEvent({ type: "latency", source: label, latencyMs: e.latencyMs });
  });
  pipeline.on("error", (e) => sendLog(`[${label}] Error: ${e.message}`, "error"));

  return pipeline;
}

function buildMicWatcher(config, physicalMic, startMicPipeline) {
  const watcherConfig = {
    ...config,
    microphoneDeviceName: physicalMic,
    virtualDeviceName: physicalMic,
    chunkDurationMs: 220,
    minChunkDurationMs: 180,
    overlapMs: 40,
  };

  const watcher = new MicrophoneCapture(watcherConfig);
  let activated = false;
  let rearmTimer = null;

  watcher.on("start", () => sendLog(`[MIC] Standby on ${physicalMic} - auto activation armed`, "status"));
  watcher.on("debug", (message) => sendLog(`[MIC][WATCH] ${message}`, "info"));
  watcher.on("error", (error) => sendLog(`[MIC][WATCH] ${error.message}`, "error"));
  watcher.on("close", () => sendLog("[MIC][WATCH] standby stopped", "warning"));
  watcher.on("chunk", async (chunk) => {
    const analysis = chunk?.analysis || {};
    const rms = Number.isFinite(analysis.rms) ? analysis.rms : 0;
    const isSpeechLikely = Boolean(analysis.isSpeechLikely);
    const durationMs = Number.isFinite(chunk?.durationMs) ? chunk.durationMs : 0;

    if (!isSpeechLikely && rms < MIC_WAKE_ENERGY_THRESHOLD) {
      return;
    }

    if (durationMs < 120) {
      return;
    }

    clearTimeout(rearmTimer);
    rearmTimer = setTimeout(() => {
      activated = false;
    }, MIC_STANDBY_TIMEOUT_MS);

    if (activated) return;
    activated = true;
    sendLog("[MIC] Activity detected - enabling mic translation pipeline", "status");
    watcher.stop();

    try {
      await startMicPipeline();
    } catch (error) {
      sendLog(`[MIC] Failed to activate pipeline: ${error.message}`, "error");
      activated = false;
      try {
        watcher.start();
      } catch {}
    }
  });

  watcher.start();
  return watcher;
}

async function stopAll() {
  isRunning = false;
  const stops = [];

  if (micWatcher) {
    stops.push(Promise.resolve().then(() => micWatcher.stop()).catch(() => {}));
    micWatcher = null;
  }
  if (speakerPipeline) {
    stops.push(speakerPipeline.stop().catch(() => {}));
    speakerPipeline = null;
  }
  if (micPipeline) {
    stops.push(micPipeline.stop().catch(() => {}));
    micPipeline = null;
  }

  await Promise.all(stops);

  if (audioBlocker) {
    await audioBlocker.unblockAudio().catch(() => {});
    sendLog("Original audio restored", "status");
  }

  sendLog("Stopped", "warning");
  broadcastState();
}

// NeuroSeed IPC handlers for consent-first memory reinforcement
ipcMain.handle("neuroseed:get-state", async () => {
  try {
    const initDb = require("../lib/migrate").initializeDatabase;
    initDb();

    const seeds = sqlite.prepare("SELECT * FROM neuroseed_seeds ORDER BY created_at DESC").all();
    const sessions = sqlite.prepare("SELECT * FROM neuroseed_sessions ORDER BY started_at DESC").all();
    const consentLogs = sqlite.prepare("SELECT * FROM neuroseed_consent_logs ORDER BY timestamp DESC LIMIT 100").all();
    const recallResults = sqlite.prepare("SELECT * FROM neuroseed_recall_results ORDER BY checked_at DESC").all();

    return {
      ok: true,
      seeds: seeds.map(s => ({
        ...s,
        keywords: JSON.parse(s.keywords || "[]"),
        cue: JSON.parse(s.cue || "{}")
      })),
      sessions: sessions.map(s => ({
        ...s,
        approvedSeedIds: JSON.parse(s.approved_seed_ids || "[]"),
        cueEvents: JSON.parse(s.cue_events || "[]"),
        uncuedSeedIds: JSON.parse(s.uncued_seed_ids || "[]"),
        settings: JSON.parse(s.settings || "{}"),
        safetyBoundary: JSON.parse(s.safety_boundary || "{}")
      })),
      consentLogs,
      recallResults
    };
  } catch (error) {
    console.error("neuroseed:get-state error:", error);
    return { ok: false, error: error.message };
  }
});

ipcMain.handle("neuroseed:put-state", async (_event, payload) => {
  try {
    const initDb = require("../lib/migrate").initializeDatabase;
    initDb();

    // Handle reset
    if (payload.dataModel?.resetRequested) {
      sqlite.prepare("DELETE FROM neuroseed_seeds").run();
      sqlite.prepare("DELETE FROM neuroseed_sessions").run();
      sqlite.prepare("DELETE FROM neuroseed_consent_logs").run();
      sqlite.prepare("DELETE FROM neuroseed_recall_results").run();
      return { ok: true, consentLogs: [] };
    }

    // Upsert seeds
    const seedStmt = sqlite.prepare(`
      INSERT OR REPLACE INTO neuroseed_seeds 
      (id, title, text, keywords, cue, approved, consent_status, consent_model, approved_at, created_at)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    `);

    (payload.seeds || []).forEach(seed => {
      seedStmt.run(
        seed.id,
        seed.title,
        seed.text,
        JSON.stringify(seed.keywords || []),
        JSON.stringify(seed.cue || {}),
        seed.approved ? 1 : 0,
        seed.consent?.status || "pending",
        seed.consent?.model || "pilot-consent-v1",
        seed.consent?.approvedAt || null,
        seed.createdAt || new Date().toISOString()
      );
    });

    // Upsert sessions
    const sessionStmt = sqlite.prepare(`
      INSERT OR REPLACE INTO neuroseed_sessions 
      (id, started_at, ended_at, status, approved_seed_ids, cue_events, uncued_seed_ids, settings, safety_boundary, created_at)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    `);

    (payload.sessions || []).forEach(session => {
      sessionStmt.run(
        session.id,
        session.startedAt,
        session.endedAt || null,
        session.status,
        JSON.stringify(session.approvedSeedIds || []),
        JSON.stringify(session.cueEvents || []),
        JSON.stringify(session.uncuedSeedIds || []),
        JSON.stringify(session.settings || {}),
        JSON.stringify(session.safetyBoundary || {}),
        session.startedAt
      );
    });

    // Log consent actions
    (payload.consentLogs || []).forEach(log => {
      sqlite.prepare(`
        INSERT OR IGNORE INTO neuroseed_consent_logs 
        (id, seed_id, action, consent_status, model_version, timestamp)
        VALUES (?, ?, ?, ?, ?, ?)
      `).run(
        log.id || `${Date.now()}-${Math.random()}`,
        log.seedId,
        log.action,
        log.consentStatus,
        log.modelVersion,
        log.timestamp || new Date().toISOString()
      );
    });

    // Upsert recall results
    const recallStmt = sqlite.prepare(`
      INSERT OR REPLACE INTO neuroseed_recall_results 
      (id, seed_id, session_id, seed_title, condition, score, answer, checked_at, consent_model)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    `);

    (payload.recallResults || []).forEach(result => {
      recallStmt.run(
        result.id,
        result.seedId,
        result.sessionId,
        result.seedTitle,
        result.condition,
        result.score,
        result.answer,
        result.checkedAt,
        result.consentModel || "pilot-consent-v1"
      );
    });

    // Return updated consent logs
    const updatedLogs = sqlite.prepare("SELECT * FROM neuroseed_consent_logs ORDER BY timestamp DESC LIMIT 50").all();
    return { ok: true, consentLogs: updatedLogs };
  } catch (error) {
    console.error("neuroseed:put-state error:", error);
    return { ok: false, error: error.message };
  }
});

ipcMain.handle("translator:get-state", async () => {
  if (!runtimeCache) await loadRuntime().catch(() => {});
  const config = getRuntimeConfig();
  return {
    isRunning,
    runtime: runtimeCache,
    settings: readDesktopSettings(),
    providerReadiness: getProviderReadiness(config),
  };
});

ipcMain.handle("translator:refresh-runtime", async () => {
  runtimeCache = null;
  whisperReady = false;
  sttSpk?.stop?.();
  sttMic?.stop?.();
  sttSpk = null;
  sttMic = null;
  const runtime = await loadRuntime();
  const config = getRuntimeConfig();
  return {
    ok: true,
    runtime,
    settings: readDesktopSettings(),
    providerReadiness: getProviderReadiness(config),
  };
});

ipcMain.handle("translator:get-settings", async () => {
  return readDesktopSettings();
});

ipcMain.handle("translator:save-settings", async (_event, payload) => {
  const current = readDesktopSettings();
  const nextSettings = {
    ...current,
    mode: "free",
    translationProvider: "local",
    nvidiaNimApiKey: "",
    nvidiaNimModel: "",
    deepLApiKey: "",
    openAiApiKey: "",
    elevenlabsApiKey: "",
    elevenlabsVoiceId: "",
  };
  writeDesktopSettings(nextSettings);
  runtimeCache = null;
  whisperReady = false;
  sttSpk?.stop?.();
  sttMic?.stop?.();
  sttSpk = null;
  sttMic = null;
  return { ok: true, settings: nextSettings };
});

ipcMain.handle("translator:get-devices", async () => {
  try {
    const t = await listDeviceTopology(getCoreConfig());
    return {
      outputDevices: t.outputDevices.filter((d) => !/cable|voicemeeter|line 1/i.test(d.name)),
      inputDevices: t.inputDevices.filter((d) => !/cable|voicemeeter|line 1/i.test(d.name)),
    };
  } catch {
    return { outputDevices: [], inputDevices: [] };
  }
});

ipcMain.handle("translator:start", async (_event, payload) => {
  if (isRunning) return { ok: true, isRunning };

  try {
    const config = getRuntimeConfig();
    const runtime = runtimeCache || (await loadRuntime());
    const topology = runtime.topology;
    const preferredVoiceProfile = pickPreferredVoiceProfile(runtime);

    const physicalMic =
      payload?.micDevice ||
      topology.inputDevices.find((d) => !/cable|voicemeeter|line 1/i.test(d.name))?.name;
    const physicalSpk =
      payload?.spkDevice ||
      topology.outputDevices.find((d) => !/cable|voicemeeter|line 1/i.test(d.name))?.name;

    if (!physicalMic) throw new Error("No physical microphone found.");
    if (!physicalSpk) throw new Error("No physical speaker found.");

    const micLang = payload?.micLang || "hi";
    const spkLang = payload?.spkLang || "te";
    const micSrcLang = payload?.micSrcLang || "auto";
    const spkSrcLang = payload?.spkSrcLang || "auto";
    const effectiveSpkSrcLang = spkSrcLang === "auto" ? "en" : spkSrcLang;
    const requestedPolicy = "offline-only";
    const desktopSettings = readDesktopSettings();
    const engineMode = "free";
    const canUseOnline = canUseOnlineProviders(config);
    let onlinePolicy = "offline-only";

    const routingCheck = validateRouteProfile({
      request: {
        platform: process.platform,
        sessionKind: "desktop_runtime",
        routeProfileId: IS_WINDOWS ? "windows-desktop-runtime" : "browser-debug",
      },
      topology,
    });

    if (!IS_WINDOWS) {
      throw new Error(
        "Desktop audio interception is currently Windows-only. This build opens on this OS, but live fail-closed routing needs a native audio adapter before translation can start."
      );
    }

    if (!routingCheck.ok) {
      throw new Error(routingCheck.diagnostics.join(" "));
    }

    if (!whisperReady) {
      sendLog("Waiting for Whisper to warm up...", "status");
      await warmWhisper(config);
    }

    if (spkSrcLang === "auto") {
      sendLog("[SPK] Fast speaker mode seeded with English for first-pass translation", "status");
    }
    sendLog(
      `[ULT] Free/offline stack active | policy=${onlinePolicy}`,
      "status"
    );
    if (preferredVoiceProfile) {
      sendLog(`[ULT] Consented local voice profile ready: ${preferredVoiceProfile.speakerLabel}`, "status");
    }
    sendLog(`[SPK] IN=${CABLE_OUTPUT} OUT=${physicalSpk} LANG=${spkLang}`, "status");
    sendLog(`[MIC] IN=${physicalMic} OUT=${LINE1_IN} LANG=${micLang}`, "status");

    if (audioBlocker) {
      sendLog("Blocking original audio...", "status");
      const blocked = await audioBlocker.blockAudio().catch(() => false);
      if (!blocked) {
        throw new Error("Fail-closed route protection could not be established.");
      }
      await delay(200);
      sendLog("Original audio blocked", "status");
    }

    const spkConfig = {
      ...config,
      runtimeTier: engineMode,
      sourceLanguage: effectiveSpkSrcLang,
      targetLanguage: spkLang,
      onlinePolicy,
      allowExperimentalOnline: canUseOnline,
      chunkDurationMs: 600,
      minChunkDurationMs: 600,
      overlapMs: 200,
      streamingSegmenter: true,
      streamingWindowMs: 600,
      streamingHopMs: 200,
      streamingCapacityMs: 5000,
      streamingSkipSilentWindows: true,
      maxRealtimeLatencyMs: 1200,
      realtimeMaxQueueDepth: 2,
      enableVoskRealtime: true,
      speechFocus: true,
      trailingSilenceMs: 100,
      preserveEmotion: false,
      preserveBackgroundAudio: false,
      directPlayNonSpeech: false,
      allowSpeakerLatePassthrough: false,
      skipAllVadSilence: true,
      skipNonSpeechWindows: true,
      realtimeWindowSkipRmsThreshold: 0.04,
      strictSpeechConfidenceGate: true,
      realtimeSpeechConfidenceThreshold: 0.55,
      virtualDeviceName: CABLE_OUTPUT,
      ttsOutputDeviceName: physicalSpk,
      voiceProfile: preferredVoiceProfile,
    };
    speakerPipeline = buildPipeline(spkConfig, new VirtualAudioCapture(spkConfig), sttSpk, "SPK");
    speakerPipeline.once("translation", () => {
      speakerPipeline.config.preserveBackgroundAudio = true;
      speakerPipeline.config.preserveEmotion = true;
      sendLog("[SPK] Translation audio engaged - strict mute released to translated output only", "status");
    });
    await speakerPipeline.start();

    const startMicPipeline = async () => {
      if (micPipeline) {
        return;
      }

      const micConfig = {
        ...config,
        runtimeTier: engineMode,
        sourceLanguage: micSrcLang,
        targetLanguage: micLang,
        onlinePolicy,
        allowExperimentalOnline: canUseOnline,
        virtualDeviceName: physicalMic,
        microphoneDeviceName: physicalMic,
        ttsOutputDeviceName: LINE1_IN,
        voiceProfile: preferredVoiceProfile,
      };
      micPipeline = buildPipeline(micConfig, new MicrophoneCapture(micConfig), sttMic, "MIC");
      let standbyTimer = null;
      const resetStandby = () => {
        clearTimeout(standbyTimer);
        standbyTimer = setTimeout(async () => {
          if (!micPipeline) {
            return;
          }

          const activePipeline = micPipeline;
          micPipeline = null;
          sendLog("[MIC] Silence detected - returning to standby watch", "status");
          await activePipeline.stop().catch(() => {});
          if (!micWatcher) {
            micWatcher = buildMicWatcher(config, physicalMic, startMicPipeline);
          }
        }, MIC_STANDBY_TIMEOUT_MS);
      };

      micPipeline.capture.on("chunk", (chunk) => {
        const analysis = chunk?.analysis || {};
        const rms = Number.isFinite(analysis.rms) ? analysis.rms : 0;
        if (analysis.isSpeechLikely || rms >= MIC_WAKE_ENERGY_THRESHOLD) {
          resetStandby();
        }
      });

      await micPipeline.start();
      resetStandby();
    };

    micWatcher = buildMicWatcher(config, physicalMic, startMicPipeline);

    isRunning = true;
    sendLog("Running - speaker path is fail-closed silent until translation audio begins", "success");
    broadcastState();
    return { ok: true, isRunning };
  } catch (error) {
    sendLog(`Failed to start: ${error.message}`, "error");
    await stopAll().catch(() => {});
    return { ok: false, error: error.message, isRunning: false };
  }
});

ipcMain.handle("translator:stop", async () => {
  await stopAll();
  return { ok: true, isRunning };
});

ipcMain.handle("translator:transcribe-video", async (_event, payload) => {
  const { spawn } = require("child_process");
  return new Promise((resolve) => {
    const scriptPath = path.join(__dirname, "..", "memo-transcribe.py");
    if (!fs.existsSync(scriptPath)) {
      return resolve({ error: "transcribe script not found at " + scriptPath });
    }

    sendLog(`Starting Memo AI transcription for: ${payload.filePath} (Target: ${payload.targetLang})`, "status");
    
    let pyPath = "python";
    const localKattappaPy = "C:\\Users\\balu\\Projects\\kattappa\\ai_system_env\\Scripts\\python.exe";
    if (fs.existsSync(localKattappaPy)) {
      pyPath = localKattappaPy;
    }

    const pyProcess = spawn(pyPath, [scriptPath, payload.filePath, payload.targetLang || "te"]);
    
    let stdoutData = "";
    let stderrData = "";
    
    pyProcess.stdout.on("data", (data) => {
      stdoutData += data.toString();
    });
    
    pyProcess.stderr.on("data", (data) => {
      stderrData += data.toString();
    });
    
    pyProcess.on("close", (code) => {
      if (code !== 0) {
        sendLog(`Memo transcription failed: ${stderrData}`, "error");
        return resolve({ error: stderrData || `process exited with code ${code}` });
      }
      try {
        const parsed = JSON.parse(stdoutData);
        sendLog(`Memo transcription completed successfully!`, "success");
        resolve(parsed);
      } catch (err) {
        resolve({ error: `failed to parse json output: ${err.message}`, raw: stdoutData });
      }
    });
  });
});

app.whenReady().then(async () => {
  // Initialize database first
  try {
    const initDb = require("../lib/migrate").initializeDatabase;
    initDb();
  } catch (e) {
    console.error("Database initialization:", e.message);
  }
  
  await loadRuntime().catch((e) => console.error("Runtime:", e.message));
  createWindow();
  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("window-all-closed", async () => {
  await stopAll();
  if (process.platform !== "darwin") app.quit();
});
