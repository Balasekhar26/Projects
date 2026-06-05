const { EventEmitter } = require("events");
const { FasterWhisperSttEngine } = require("./faster-whisper");
const { OpenAiWhisperSttEngine } = require("./openai-whisper");
const { VoskSttEngine } = require("./vosk");
const { resolveCoreConfig } = require("../config");

class HybridSttEngine extends EventEmitter {
  constructor(config = {}) {
    super();
    this.config = resolveCoreConfig(config);
    this.offline = new FasterWhisperSttEngine(this.config);
    this.vosk = null;
    this.online = null;
    this.offline.on("debug", (message) => this.emit("debug", message));
    this.offline.on("error", (error) => this.emit("error", error));
  }

  async transcribeChunk(input = {}) {
    const policy = this._resolveOnlinePolicy(input.onlinePolicy || this.config.onlinePolicy || "offline-only");
    const sourceLanguage = typeof input.sourceLanguage === "string" ? input.sourceLanguage.trim().toLowerCase() : "";
    const prefersPremium = this._prefersPremiumStt(policy);

    if (prefersPremium) {
      try {
        return await this._getOnline().transcribeChunk(input);
      } catch (error) {
        this.emit("debug", `premium stt fallback to local: ${error.message}`);
      }
    }

    if (this._shouldUseVosk(input, sourceLanguage)) {
      try {
        return await this._getVosk().transcribeChunk(input);
      } catch (error) {
        this.emit("debug", `vosk fallback to whisper: ${error.message}`);
      }
    }

    if (policy === "offline-only") {
      return this.offline.transcribeChunk(input);
    }

    if (policy === "online-only") {
      return this._getOnline().transcribeChunk(input);
    }

    if (this.config.openAiApiKey) {
      try {
        return await this._getOnline().transcribeChunk(input);
      } catch {
        // Experimental online STT is optional; offline is still authoritative.
      }
    }

    return this.offline.transcribeChunk(input);
  }

  _resolveOnlinePolicy(policy) {
    if (!this.config.allowExperimentalOnline) {
      return "offline-only";
    }

    return policy;
  }

  _getOnline() {
    if (this.config.freeOnlyProviders) {
      throw new Error("Paid online STT providers are disabled in free-only mode.");
    }

    if (!this.online) {
      this.online = new OpenAiWhisperSttEngine(this.config);
    }

    return this.online;
  }

  _shouldUseVosk(input, sourceLanguage) {
    if (!this.config.enableVoskRealtime) {
      return false;
    }

    if (input.realtimeMode === false) {
      return false;
    }

    return sourceLanguage === "en";
  }

  _getVosk() {
    if (!this.vosk) {
      this.vosk = new VoskSttEngine(this.config);
      this.vosk.on("debug", (message) => this.emit("debug", message));
      this.vosk.on("error", (error) => this.emit("error", error));
    }

    return this.vosk;
  }

  _prefersPremiumStt(policy) {
    const tier = String(this.config.runtimeTier || "").toLowerCase();
    return tier === "paid" && policy !== "offline-only" && Boolean(this.config.openAiApiKey);
  }

  stop() {
    this.offline.stop();
    this.vosk?.stop();
    this.online?.stop();
  }
}

module.exports = { HybridSttEngine };
