const { EventEmitter } = require("events");
const { FasterWhisperSttEngine } = require("./faster-whisper");
const { OpenAiWhisperSttEngine } = require("./openai-whisper");

class HybridSttEngine extends EventEmitter {
  constructor(config) {
    super();
    this.config = config;
    this.offline = new FasterWhisperSttEngine(config);
    this.online = new OpenAiWhisperSttEngine(config);
    this.offline.on("debug", (message) => this.emit("debug", message));
    this.offline.on("error", (error) => this.emit("error", error));
  }

  async transcribeChunk(input) {
    const onlinePolicy = input.onlinePolicy || "auto";

    if (onlinePolicy !== "offline-only") {
      try {
        return await this.online.transcribeChunk(input);
      } catch (error) {
        if (onlinePolicy === "online-only") {
          throw error;
        }
      }
    }

    return this.offline.transcribeChunk(input);
  }

  stop() {
    this.offline.stop();
    this.online.stop();
  }
}

module.exports = {
  HybridSttEngine,
};
