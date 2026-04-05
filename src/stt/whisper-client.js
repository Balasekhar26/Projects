const { EventEmitter } = require("events");
const { spawn } = require("child_process");
const readline = require("readline");

class WhisperClient extends EventEmitter {
  constructor(config) {
    super();
    this.config = config;
    this.process = null;
    this.nextRequestId = 1;
    this.pendingRequests = new Map();
  }

  start() {
    if (this.process) {
      return;
    }

    this.process = spawn(
      this.config.pythonPath,
      [this.config.whisperWorkerPath, this.config.whisperModelPath],
      {
        stdio: ["pipe", "pipe", "pipe"],
      }
    );

    const lineReader = readline.createInterface({
      input: this.process.stdout,
      crlfDelay: Infinity,
    });

    lineReader.on("line", (line) => {
      this.handleWorkerMessage(line);
    });

    this.process.stderr.on("data", (chunk) => {
      const message = chunk.toString().trim();
      if (message) {
        this.emit("debug", message);
      }
    });

    this.process.on("error", (error) => {
      this.rejectPending(error);
      this.emit("error", error);
    });

    this.process.on("close", (code, signal) => {
      this.rejectPending(
        new Error(`Whisper worker exited unexpectedly (code=${code}, signal=${signal || "none"}).`)
      );
      this.process = null;
      this.emit("close", { code, signal });
    });
  }

  stop() {
    if (!this.process) {
      return;
    }

    this.process.stdin.end();
  }

  transcribeChunk({ audioPath, sourceLanguage, targetLanguage }) {
    this.start();

    const requestId = String(this.nextRequestId++);
    const payload = {
      id: requestId,
      audio_path: audioPath,
      source_language: sourceLanguage,
      target_language: targetLanguage,
    };

    return new Promise((resolve, reject) => {
      this.pendingRequests.set(requestId, { resolve, reject });
      this.process.stdin.write(`${JSON.stringify(payload)}\n`, "utf8");
    });
  }

  handleWorkerMessage(rawLine) {
    if (!rawLine) {
      return;
    }

    let message;
    try {
      message = JSON.parse(rawLine);
    } catch {
      this.emit("debug", `Invalid worker output: ${rawLine}`);
      return;
    }

    const request = this.pendingRequests.get(message.id);
    if (!request) {
      return;
    }

    this.pendingRequests.delete(message.id);
    if (message.error) {
      request.reject(new Error(message.error));
      return;
    }

    request.resolve(message);
  }

  rejectPending(error) {
    for (const request of this.pendingRequests.values()) {
      request.reject(error);
    }

    this.pendingRequests.clear();
  }
}

module.exports = {
  WhisperClient,
};
