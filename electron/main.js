const path = require("path");
const fs = require("fs");
const { app, BrowserWindow, ipcMain } = require("electron");

// Load .env before anything else so getCoreConfig() sees the values
const dotenvPath = path.join(__dirname, "..", ".env");
if (fs.existsSync(dotenvPath)) {
  require("dotenv").config({ path: dotenvPath });
}

const { getCoreConfig } = require("../packages/ult-core/src/config");
const { listDeviceTopology } = require("../packages/ult-core/src/device-control/topology");
const { runBootstrapInspection } = require("../packages/ult-core/src/installer/bootstrap");
const { prepareRuntimeForSession } = require("../packages/ult-core/src/installer/provisioning");
const { listVoiceProfiles } = require("../packages/ult-core/src/voice-clone/registry");
const { MicrophoneRouter } = require("../packages/ult-core/src/mic-routing/router");
const { HybridSttEngine } = require("../packages/ult-core/src/stt-engine");
const { HybridTranslationEngine } = require("../packages/ult-core/src/translation-engine");
const { TieredSpeechEngine } = require("../packages/ult-core/src/tts-engine/tiered-speaker");
const { VirtualAudioCapture } = require("../src/audio/capture");
const { RealtimeTranslator } = require("../src/pipeline/realtime-translator");

let mainWindow = null;
let isRunning = false;
let runtimeCache = null;
let activePipeline = null;

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1240,
    height: 900,
    minWidth: 980,
    minHeight: 720,
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

function sendLog(message, level = "info") {
  if (!mainWindow || mainWindow.isDestroyed()) {
    return;
  }

  mainWindow.webContents.send("translator:log", {
    level,
    message,
    timestamp: new Date().toLocaleTimeString(),
  });
}

function sendEvent(payload) {
  if (!mainWindow || mainWindow.isDestroyed()) {
    return;
  }

  mainWindow.webContents.send("translator:event", payload);
}

function broadcastState() {
  if (!mainWindow || mainWindow.isDestroyed()) {
    return;
  }

  mainWindow.webContents.send("translator:state", {
    isRunning,
    runtime: runtimeCache,
  });
}

async function loadRuntime() {
  const config = getCoreConfig();
  const [topology, bootstrap, voiceProfiles] = await Promise.all([
    listDeviceTopology(config),
    runBootstrapInspection(config),
    listVoiceProfiles(config),
  ]);

  // Initialize microphone router
  const micRouter = new MicrophoneRouter(config);
  await micRouter.initialize().catch((error) => {
    console.warn("Microphone routing initialization warning:", error.message);
  });

  runtimeCache = {
    topology,
    bootstrap,
    voiceProfiles,
    microphoneRouter: micRouter,
  };
  return runtimeCache;
}

function pickDefaultInputDevice(topology, sessionKind) {
  const inputDevices = Array.isArray(topology?.inputDevices) ? topology.inputDevices : [];

  if (sessionKind === "system") {
    return (
      inputDevices.find((device) => /cable output|voicemeeter output/i.test(device.name))?.name ||
      inputDevices[0]?.name ||
      ""
    );
  }

  return (
    inputDevices.find((device) => !/cable|voicemeeter/i.test(device.name))?.name ||
    inputDevices[0]?.name ||
    ""
  );
}

function bindPipeline(pipeline) {
  pipeline.on("status", (message) => sendLog(message, "status"));
  pipeline.on("debug", (message) => sendLog(message, "info"));
  pipeline.on("translation", (event) => {
    sendEvent({
      type: "final_translation",
      ...event,
    });
    sendLog(
      `Translated chunk ${event.chunkNumber}: ${event.translatedText || "No text produced"}`,
      "success"
    );
  });
  pipeline.on("latency", (event) => {
    sendEvent({
      type: "latency_sample",
      ...event,
    });
    sendLog(`Chunk ${event.chunkNumber} latency: ${event.latencyMs} ms`, "status");
  });
  pipeline.on("error", async (error) => {
    sendLog(error.message, "error");
    sendEvent({ type: "error", message: error.message });
    await stopPipeline();
  });
}

async function stopPipeline() {
  if (!activePipeline) {
    isRunning = false;
    broadcastState();
    return;
  }

  const pipeline = activePipeline;
  activePipeline = null;
  isRunning = false;

  await pipeline.stop().catch(() => {});
  sendLog("Desktop capture session stopped", "warning");
  broadcastState();
}

ipcMain.handle("translator:get-state", async () => {
  if (!runtimeCache) {
    await loadRuntime();
  }

  return {
    isRunning,
    runtime: runtimeCache,
  };
});

ipcMain.handle("translator:refresh-runtime", async () => {
  const runtime = await loadRuntime();
  broadcastState();
  return runtime;
});

ipcMain.handle("translator:start", async (_event, payload) => {
  if (isRunning) {
    return { ok: true, isRunning };
  }

  const baseConfig = getCoreConfig();
  const sessionKind = payload?.sessionKind || "microphone";
  const preparation = await prepareRuntimeForSession({
    config: baseConfig,
    sourceLanguage: payload?.sourceLanguage || "en",
    targetLanguage: payload?.targetLanguage || "te",
    onlinePolicy: payload?.onlinePolicy || "auto",
  });
  for (const action of preparation.actions) {
    sendLog(`Prepare ${action.step}: ${action.status} - ${action.detail}`, "status");
  }

  const runtime = await loadRuntime();
  const inputDeviceName = payload?.inputDeviceId || pickDefaultInputDevice(runtime.topology, sessionKind);
  const outputDeviceName =
    payload?.outputDeviceId || baseConfig.ttsOutputDeviceName || runtime.topology.outputDevices[0]?.name || "";
  const voiceProfile =
    runtime.voiceProfiles.find((profile) => profile.id === payload?.voiceProfileId) ||
    runtime.voiceProfiles[0] ||
    null;

  const pipelineConfig = {
    ...baseConfig,
    sourceLanguage: payload?.sourceLanguage || "en",
    targetLanguage: payload?.targetLanguage || "te",
    onlinePolicy: payload?.onlinePolicy || "auto",
    virtualDeviceName: inputDeviceName,
    ttsOutputDeviceName: outputDeviceName,
    voiceProfile,
  };

  activePipeline = new RealtimeTranslator({
    config: pipelineConfig,
    capture: new VirtualAudioCapture(pipelineConfig),
    sttClient: new HybridSttEngine(pipelineConfig),
    translator: new HybridTranslationEngine(pipelineConfig),
    speaker: new TieredSpeechEngine(pipelineConfig),
  });
  bindPipeline(activePipeline);

  await activePipeline.start();
  isRunning = true;
  sendLog(
    `Desktop capture session started: ${inputDeviceName} -> ${payload?.targetLanguage || "te"}`,
    "success"
  );
  broadcastState();

  return { ok: true, isRunning };
});

ipcMain.handle("translator:stop", async () => {
  await stopPipeline();
  return { ok: true, isRunning };
});

ipcMain.handle("microphone:setup", async () => {
  if (!runtimeCache?.microphoneRouter) {
    return { ok: false, error: "Microphone router not initialized" };
  }
  const result = await runtimeCache.microphoneRouter.setupMicrophoneRouting();
  return result;
});

ipcMain.handle("microphone:status", async () => {
  if (!runtimeCache?.microphoneRouter) {
    return null;
  }
  return await runtimeCache.microphoneRouter.getRoutingStatus();
});

ipcMain.handle("microphone:list-physical", async () => {
  if (!runtimeCache?.microphoneRouter) {
    return [];
  }
  return await runtimeCache.microphoneRouter.getPhysicalMicrophones();
});

ipcMain.handle("microphone:list-virtual", async () => {
  if (!runtimeCache?.microphoneRouter) {
    return [];
  }
  return await runtimeCache.microphoneRouter.getVirtualMicrophones();
});

ipcMain.handle("microphone:check-driver", async () => {
  if (!runtimeCache?.microphoneRouter) {
    return false;
  }
  return await runtimeCache.microphoneRouter.checkVirtualMicDriver();
});

app.whenReady().then(async () => {
  await loadRuntime().catch((error) => {
    sendLog(error.message, "error");
  });
  createWindow();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on("window-all-closed", async () => {
  await stopPipeline();
  if (process.platform !== "darwin") {
    app.quit();
  }
});
