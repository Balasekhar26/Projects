const { EventEmitter } = require("events");
const { WhisperHttpClient } = require("../../../../src/stt/whisper-http-client");

class FasterWhisperSttEngine extends EventEmitter {
  constructor(config) {
    super();
    this.client = new WhisperHttpClient(config);
    this.client.on("debug", (message) => this.emit("debug", message));
    this.client.on("error", (error) => this.emit("error", error));
  }

  async transcribeChunk(input) {
    const result = await this.client.transcribeChunk(input);
    return { ...result, backend: "faster-whisper" };
  }

  stop() {
    this.client.stop();
  }
}

module.exports = { FasterWhisperSttEngine };
