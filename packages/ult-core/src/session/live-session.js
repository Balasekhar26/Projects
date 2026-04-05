const fs = require("fs/promises");
const path = require("path");
const { EventEmitter } = require("events");
const { randomUUID } = require("crypto");

const { HybridSttEngine } = require("../stt-engine");
const { HybridTranslationEngine } = require("../translation-engine");
const { TieredSpeechEngine } = require("../tts-engine/tiered-speaker");
const { getCoreConfig } = require("../config");
const { createSessionEvent, normalizeStartSessionRequest, SESSION_EVENT_TYPES } = require("../contracts");
const { getVoiceProfile } = require("../voice-clone/registry");

class UniversalLiveSession extends EventEmitter {
  constructor(request, options = {}) {
    super();
    this.config = options.config || getCoreConfig();
    this.request = normalizeStartSessionRequest(request);
    this.id = randomUUID();
    this.createdAt = new Date().toISOString();
    this.tempDir = path.join(this.config.tempDir, "sessions", this.id);
    this.sttEngine = options.sttEngine || new HybridSttEngine(this.config);
    this.translationEngine = options.translationEngine || new HybridTranslationEngine(this.config);
    this.speechEngine = options.speechEngine || new TieredSpeechEngine(this.config);
    this.processingQueue = Promise.resolve();
    this.recentEvents = [];
    this.lastTranslatedText = "";
    this.chunkSequence = 0;
    this.stopped = false;
  }

  async start() {
    await fs.mkdir(this.tempDir, { recursive: true });
    this.publish(SESSION_EVENT_TYPES.STATUS, {
      message: `Session ready: ${this.request.sourceLanguage} -> ${this.request.targetLanguage}`,
    });
    this.publish(SESSION_EVENT_TYPES.ROUTING_STATE, {
      routeProfileId: this.request.routeProfileId,
      inputDeviceId: this.request.inputDeviceId,
      outputDeviceId: this.request.outputDeviceId,
      sessionKind: this.request.sessionKind,
    });
  }

  getSnapshot() {
    return {
      id: this.id,
      createdAt: this.createdAt,
      request: this.request,
      events: this.recentEvents,
    };
  }

  async enqueueChunk({ audioBuffer, fileExtension, analysis }) {
    if (this.stopped) {
      throw new Error("Session is already stopped.");
    }

    const chunkNumber = ++this.chunkSequence;
    const chunkPath = path.join(this.tempDir, `chunk-${chunkNumber}.${fileExtension || "wav"}`);
    await fs.writeFile(chunkPath, audioBuffer);

    this.processingQueue = this.processingQueue
      .then(() => this.processChunk({ chunkNumber, chunkPath, analysis }))
      .catch((error) => {
        this.publish(SESSION_EVENT_TYPES.ERROR, {
          chunkNumber,
          message: error instanceof Error ? error.message : String(error),
        });
      });

    return { chunkNumber };
  }

  async stop() {
    if (this.stopped) {
      return;
    }

    this.stopped = true;
    await this.processingQueue.catch(() => {});
    this.sttEngine.stop();
    this.translationEngine.stop();
    await fs.rm(this.tempDir, { recursive: true, force: true }).catch(() => {});
    this.publish(SESSION_EVENT_TYPES.STATUS, {
      message: "Session stopped",
    });
  }

  async processChunk({ chunkNumber, chunkPath, analysis }) {
    const startedAt = Date.now();
    this.publish(SESSION_EVENT_TYPES.STATUS, {
      message: `Processing chunk ${chunkNumber}`,
      chunkNumber,
    });

    try {
      const transcription = await this.sttEngine.transcribeChunk({
        audioPath: chunkPath,
        sourceLanguage: this.request.sourceLanguage,
        targetLanguage: this.request.targetLanguage,
        onlinePolicy: this.request.onlinePolicy,
      });
      const transcript = (transcription.transcript || "").trim();

      if (transcript) {
        this.publish(SESSION_EVENT_TYPES.PARTIAL_TRANSCRIPT, {
          chunkNumber,
          transcript,
          detectedLanguage: transcription.detected_language || this.request.sourceLanguage,
          backend: transcription.backend || "stt",
        });
      }

      const translation = await this.translationEngine.translate({
        transcript,
        whisperTranslation: transcription.translated_text,
        detectedLanguage: transcription.detected_language,
        sourceLanguage: this.request.sourceLanguage,
        targetLanguage: this.request.targetLanguage,
        onlinePolicy: this.request.onlinePolicy,
      });

      const translatedText = (translation.translatedText || "").trim();
      if (translatedText) {
        this.publish(SESSION_EVENT_TYPES.PARTIAL_TRANSLATION, {
          chunkNumber,
          transcript,
          translatedText,
          detectedLanguage: transcription.detected_language || this.request.sourceLanguage,
          backend: translation.backend,
        });
      }

      this.publish(SESSION_EVENT_TYPES.FINAL_TRANSLATION, {
        chunkNumber,
        transcript,
        translatedText,
        detectedLanguage: transcription.detected_language || this.request.sourceLanguage,
        backend: translation.backend,
      });

      if (translatedText && translatedText !== this.lastTranslatedText) {
        this.lastTranslatedText = translatedText;
        const voiceProfile = await getVoiceProfile(this.config, this.request.voiceProfileId);
        this.publish(SESSION_EVENT_TYPES.TTS_STARTED, {
          chunkNumber,
          translatedText,
          voiceProfileId: voiceProfile?.id || this.request.voiceProfileId,
        });
        await this.speechEngine.speak(translatedText, {
          onlinePolicy: this.request.onlinePolicy,
          language: this.request.targetLanguage,
          outputDeviceName: this.request.outputDeviceId,
          voiceProfile,
          analysis,
          transcript,
          preserveEmotion: this.request.preserveEmotion,
        });
        this.publish(SESSION_EVENT_TYPES.TTS_FINISHED, {
          chunkNumber,
          translatedText,
          voiceProfileId: voiceProfile?.id || this.request.voiceProfileId,
        });
      }

      this.publish(SESSION_EVENT_TYPES.LATENCY_SAMPLE, {
        chunkNumber,
        latencyMs: Date.now() - startedAt,
      });
    } finally {
      await fs.rm(chunkPath, { force: true }).catch(() => {});
    }
  }

  publish(type, payload = {}) {
    const event = createSessionEvent(type, {
      sessionId: this.id,
      ...payload,
    });

    this.recentEvents.push(event);
    if (this.recentEvents.length > 100) {
      this.recentEvents.shift();
    }

    this.emit("event", event);
  }
}

module.exports = {
  UniversalLiveSession,
};
