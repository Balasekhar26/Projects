const path = require("path");
const fs = require("fs");

const dotenvPath = path.join(__dirname, "..", ".env");
if (fs.existsSync(dotenvPath)) {
  require("dotenv").config({ path: dotenvPath });
}

const { getCoreConfig } = require("../packages/ult-core/src/config");
const { prepareRuntimeForSession } = require("../packages/ult-core/src/installer/provisioning");
const { HybridSttEngine } = require("../packages/ult-core/src/stt-engine");
const { HybridTranslationEngine } = require("../packages/ult-core/src/translation-engine");
const { TieredSpeechEngine } = require("../packages/ult-core/src/tts-engine/tiered-speaker");
const { RealtimeTranslator } = require("../src/pipeline/realtime-translator");
const {
  MicrophoneCapture,
  VirtualAudioCapture,
  WasapiLoopbackCapture,
} = require("../modules/audio-capture");

async function main() {
  const captureMode = normalizeMode(process.env.ULT_CAPTURE_MODE);
  const config = getCoreConfig({
    runtimeTier: process.env.ULT_RUNTIME_TIER || "free",
    sourceLanguage: process.env.SOURCE_LANGUAGE || "en",
    targetLanguage: process.env.TARGET_LANGUAGE || "te",
    onlinePolicy: process.env.ONLINE_POLICY || "auto",
    ttsOutputDeviceName: process.env.TTS_OUTPUT_DEVICE || "",
    virtualDeviceName:
      process.env.ULT_CAPTURE_DEVICE ||
      process.env.VIRTUAL_AUDIO_DEVICE ||
      "CABLE Output (VB-Audio Virtual Cable)",
    streamingSegmenter: true,
    streamingWindowMs: Number(process.env.ULT_STREAMING_WINDOW_MS || 600),
    streamingHopMs: Number(process.env.ULT_STREAMING_HOP_MS || 200),
    streamingCapacityMs: Number(process.env.ULT_STREAMING_CAPACITY_MS || 5000),
    streamingSkipSilentWindows: true,
    minChunkDurationMs: Number(process.env.ULT_MIN_CHUNK_MS || 600),
    chunkDurationMs: Number(process.env.ULT_CHUNK_MS || 600),
    overlapMs: Number(process.env.ULT_OVERLAP_MS || 200),
    realtimeMaxQueueDepth: Number(process.env.ULT_MAX_QUEUE_DEPTH || 4),
    realtimeTargetLatencyMs: Number(process.env.ULT_TARGET_LATENCY_MS || 0),
    realtimeForceCommitMs: Number(process.env.ULT_FORCE_COMMIT_MS || 200),
    realtimeSpeechConfidenceThreshold: Number(process.env.ULT_SPEECH_CONFIDENCE_THRESHOLD || 0.45),
    skipAllVadSilence: true,
  });
  config.microphoneDeviceName =
    process.env.MICROPHONE_DEVICE_NAME ||
    process.env.ULT_MIC_DEVICE ||
    config.microphoneDeviceName ||
    "";

  const capture = createCapture(captureMode, config);
  const pipeline = new RealtimeTranslator({
    config,
    capture,
    sttClient: new HybridSttEngine(config),
    translator: new HybridTranslationEngine(config),
    speaker: new TieredSpeechEngine(config),
  });

  pipeline.on("status", (message) => {
    console.log(`[status] ${message}`);
  });
  pipeline.on("debug", (message) => {
    console.log(`[debug] ${message}`);
  });
  pipeline.on("translation", (event) => {
    console.log(
      `\n[chunk ${event.chunkNumber}] ${event.detectedLanguage} -> ${config.targetLanguage} (${event.backend}, ${event.mode})`
    );
    if (event.transcript) {
      console.log(`source: ${event.transcript}`);
    }
    console.log(`translated: ${event.translatedText}`);
  });
  pipeline.on("latency", (event) => {
    console.log(
      `[latency] chunk ${event.chunkNumber}: ${event.latencyMs}ms` +
        (event.durationMs ? ` / ${event.durationMs}ms audio` : "")
    );
  });
  pipeline.on("metric", (event) => {
    if (event?.type !== "latency") {
      return;
    }
    if (event.scope === "chunk") {
      console.log(
        `[metric] chunk ${event.chunkNumber}: speech_start->audio=${formatMetric(event.speechStartToFirstAudioMs)} ` +
        `stt=${formatMetric(event.sttReadyMs)} translate=${formatMetric(event.translationReadyMs)} ` +
        `queue=${formatMetric(event.playbackQueueDelayMs)} tts_start=${formatMetric(event.ttsStartDelayMs)}`
      );
      return;
    }
    if (event.scope === "phrase" && event.interruptReactionMs !== null) {
      console.log(
        `[metric] phrase ${event.phraseId}:${event.revision} interrupt=${formatMetric(event.interruptReactionMs)}`
      );
    }
  });
  pipeline.on("error", async (error) => {
    console.error("[error]", error.message);
    await stopPipeline(pipeline);
    process.exitCode = 1;
  });

  const preparation = await prepareRuntimeForSession({
    config,
    sourceLanguage: config.sourceLanguage,
    targetLanguage: config.targetLanguage,
    onlinePolicy: config.onlinePolicy,
  });
  for (const action of preparation.actions) {
    console.log(`[prepare] ${action.step}: ${action.status} - ${action.detail}`);
  }

  console.log("Starting ear-pass runner...");
  console.log(`Capture mode: ${captureMode}`);
  if (captureMode === "mic") {
    console.log(`Microphone: ${config.microphoneDeviceName || "(default/fallback)"}`);
  } else if (captureMode === "loopback") {
    console.log(`Loopback device id: ${process.env.ULT_LOOPBACK_DEVICE_ID || "(default render device)"}`);
  } else {
    console.log(`Virtual device: ${config.virtualDeviceName}`);
  }
  console.log(`Languages: ${config.sourceLanguage} -> ${config.targetLanguage} (${config.onlinePolicy})`);
  console.log(`Audio dumps: ${process.env.ULT_DUMP_AUDIO === "1" ? "enabled" : "disabled"}`);
  console.log("Press Ctrl+C to stop.\n");

  process.on("SIGINT", async () => {
    console.log("\nStopping ear-pass runner...");
    await stopPipeline(pipeline);
    process.exit(0);
  });

  await pipeline.start();
}

function createCapture(mode, config) {
  if (mode === "mic") {
    return new MicrophoneCapture(config);
  }
  if (mode === "loopback") {
    const capture = new WasapiLoopbackCapture(config);
    const originalStart = capture.start.bind(capture);
    capture.start = () => originalStart(process.env.ULT_LOOPBACK_DEVICE_ID || null);
    return capture;
  }
  return new VirtualAudioCapture(config);
}

async function stopPipeline(pipeline) {
  await pipeline.stop().catch(() => {});
  pipeline.speaker?.stop?.();
  pipeline.sttClient?.stop?.();
  pipeline.translator?.stop?.();
}

function normalizeMode(value) {
  const normalized = typeof value === "string" ? value.trim().toLowerCase() : "";
  if (normalized === "mic" || normalized === "loopback" || normalized === "virtual") {
    return normalized;
  }
  return "mic";
}

main().catch((error) => {
  console.error("[fatal]", error.message);
  process.exit(1);
});

function formatMetric(value) {
  return Number.isFinite(value) ? `${Math.round(value)}ms` : "n/a";
}
