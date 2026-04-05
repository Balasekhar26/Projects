const fs = require("fs/promises");
const path = require("path");
const { EventEmitter } = require("events");

const { writePcmAsWavFile } = require("../utils/wav");

class RealtimeTranslator extends EventEmitter {
  constructor({ config, capture, sttClient, translator, speaker }) {
    super();
    this.config = config;
    this.capture = capture;
    this.sttClient = sttClient;
    this.translator = translator;
    this.speaker = speaker;
    this.chunkSequence = 0;
    this.lastSpokenText = "";
    this.processingQueue = Promise.resolve();
    this.isBound = false;
    this.captureClosedPromise = null;
  }

  async start() {
    await fs.mkdir(this.config.tempDir, { recursive: true });
    this.bindEvents();
    this.captureClosedPromise = new Promise((resolve) => {
      this.capture.once("close", resolve);
    });
    this.capture.start();
  }

  async stop() {
    this.capture.stop();
    await this.captureClosedPromise;
    await this.processingQueue.catch(() => {});
    this.sttClient.stop();
  }

  bindEvents() {
    if (this.isBound) {
      return;
    }

    this.isBound = true;
    this.capture.on("start", (details) => this.emit("status", `Capturing from ${details.device}`));
    this.capture.on("debug", (message) => this.emit("debug", `capture: ${message}`));
    this.capture.on("error", (error) => this.emit("error", error));
    this.capture.on("close", ({ code }) => this.emit("status", `Capture stopped (code=${code ?? "none"})`));
    this.sttClient.on("debug", (message) => this.emit("debug", `whisper: ${message}`));
    this.sttClient.on("error", (error) => this.emit("error", error));

    this.capture.on("chunk", (chunk) => {
      this.processingQueue = this.processingQueue
        .then(() => this.processChunk(chunk))
        .catch((error) => this.emit("error", error));
    });
  }

  async processChunk(chunk) {
    const chunkNumber = ++this.chunkSequence;
    const wavFilePath = path.join(this.config.tempDir, `chunk-${chunkNumber}.wav`);
    const startedAt = Date.now();

    await writePcmAsWavFile(wavFilePath, chunk.pcmBuffer, {
      sampleRate: this.config.sampleRate,
      channels: this.config.channels,
      bitsPerSample: this.config.bytesPerSample * 8,
    });

    this.emit(
      "status",
      `Processing chunk ${chunkNumber}${chunk.reason ? ` (${chunk.reason})` : ""}`
    );

    try {
      const transcriptionResult = await this.sttClient.transcribeChunk({
        audioPath: wavFilePath,
        sourceLanguage: this.config.sourceLanguage,
        targetLanguage: this.config.targetLanguage,
        onlinePolicy: this.config.onlinePolicy || "auto",
      });

      const translationResult = await this.translator.translate({
        transcript: transcriptionResult.transcript,
        whisperTranslation: transcriptionResult.translated_text,
        detectedLanguage: transcriptionResult.detected_language,
        sourceLanguage: this.config.sourceLanguage,
        targetLanguage: this.config.targetLanguage,
        onlinePolicy: this.config.onlinePolicy || "auto",
      });

      const translatedText = translationResult.translatedText.trim();
      if (!translatedText || translatedText === this.lastSpokenText) {
        this.emit("latency", {
          chunkNumber,
          latencyMs: Date.now() - startedAt,
          durationMs: chunk.durationMs,
        });
        return;
      }

      this.lastSpokenText = translatedText;
      this.emit("translation", {
        chunkNumber,
        detectedLanguage: transcriptionResult.detected_language || "unknown",
        transcript: transcriptionResult.transcript || "",
        translatedText,
        backend: translationResult.backend,
      });

      await this.speaker.speak(translatedText, {
        language: this.config.targetLanguage,
        onlinePolicy: this.config.onlinePolicy || "auto",
        outputDeviceName: this.config.ttsOutputDeviceName,
        voiceProfile: this.config.voiceProfile || null,
        analysis: chunk.analysis,
        transcript: transcriptionResult.transcript || translatedText,
        preserveEmotion: true,
      });

      this.emit("latency", {
        chunkNumber,
        latencyMs: Date.now() - startedAt,
        durationMs: chunk.durationMs,
      });
    } finally {
      await fs.rm(wavFilePath, { force: true });
    }
  }
}

module.exports = {
  RealtimeTranslator,
};
