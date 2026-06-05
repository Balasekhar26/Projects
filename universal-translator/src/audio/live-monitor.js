const { EventEmitter } = require("events");
const { spawn } = require("child_process");

class LiveAudioMonitor extends EventEmitter {
  constructor(config = {}) {
    super();
    this.config = config;
    this.process = null;
    this.isRunning = false;
  }

  start({ inputDeviceName, outputDeviceName }) {
    if (this.isRunning) {
      return;
    }

    const args = [
      "-q",
      "-t",
      "waveaudio",
      inputDeviceName,
      "-t",
      "waveaudio",
      outputDeviceName,
    ];

    this.process = spawn(this.config.soxPath, args, {
      stdio: ["ignore", "pipe", "pipe"],
    });
    this.isRunning = true;
    this.emit("start", { inputDeviceName, outputDeviceName });

    this.process.stderr.on("data", (chunk) => {
      const message = chunk.toString().trim();
      if (message) {
        this.emit("debug", message);
      }
    });

    this.process.on("error", (error) => {
      this.emit("error", error);
    });

    this.process.on("close", (code, signal) => {
      this.isRunning = false;
      this.process = null;
      this.emit("close", { code, signal });
    });
  }

  stop() {
    if (!this.process) {
      return;
    }

    this.process.kill("SIGINT");
    this.process = null;
    this.isRunning = false;
  }
}

module.exports = {
  LiveAudioMonitor,
};
