const path = require("path");
const fs = require("fs");

const dotenvPath = path.join(__dirname, "..", ".env");
if (fs.existsSync(dotenvPath)) {
  require("dotenv").config({ path: dotenvPath });
}

const { VirtualAudioCapture } = require("./audio/capture");
const { config } = require("./runtime");
const { RealtimeTranslator } = require("./pipeline/realtime-translator");
const { HybridSttEngine } = require("../packages/ult-core/src/stt-engine");
const { HybridTranslationEngine } = require("../packages/ult-core/src/translation-engine");
const { TieredSpeechEngine } = require("../packages/ult-core/src/tts-engine/tiered-speaker");
const { prepareRuntimeForSession } = require("../packages/ult-core/src/installer/provisioning");

async function main() {
  const pipeline = new RealtimeTranslator({
    config,
    capture: new VirtualAudioCapture(config),
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
      `\n[chunk ${event.chunkNumber}] ${event.detectedLanguage} -> ${config.targetLanguage} (${event.backend})`
    );
    if (event.transcript) {
      console.log(`source: ${event.transcript}`);
    }
    console.log(`translated: ${event.translatedText}`);
  });

  pipeline.on("latency", (event) => {
    console.log(
      `[latency] chunk ${event.chunkNumber}: ${event.latencyMs}ms end-to-end` +
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
    await pipeline.stop();
    process.exitCode = 1;
  });

  process.on("SIGINT", async () => {
    console.log("\nStopping real-time translator...");
    await pipeline.stop();
    process.exit(0);
  });

  console.log("Starting real-time translator...");
  console.log(`Virtual device: ${config.virtualDeviceName}`);
  console.log(`Whisper model: ${config.whisperModelPath}`);
  console.log(`Chunk length: ${config.chunkDurationMs}ms`);
  console.log(`Languages: ${config.sourceLanguage} -> ${config.targetLanguage} (policy: ${config.onlinePolicy})`);
  const preparation = await prepareRuntimeForSession({
    config,
    sourceLanguage: config.sourceLanguage,
    targetLanguage: config.targetLanguage,
    onlinePolicy: config.onlinePolicy,
  });
  for (const action of preparation.actions) {
    console.log(`[prepare] ${action.step}: ${action.status} - ${action.detail}`);
  }
  await pipeline.start();
}

main().catch((error) => {
  console.error("[fatal]", error.message);
  process.exit(1);
});

function formatMetric(value) {
  return Number.isFinite(value) ? `${Math.round(value)}ms` : "n/a";
}
