const { EventEmitter } = require("events");
const { spawn } = require("child_process");
const fs = require("fs");
const readline = require("readline");
const path = require("path");
const { getPythonEnv, resolveCoreConfig } = require("../config");

class VoskSttEngine extends EventEmitter {
  constructor(config = {}) {
    super();
    this.config = resolveCoreConfig(config);
    this.proc = null;
    this.pending = new Map();
    this.nextId = 1;
    this.workerPath = this.config.voskWorkerPath || path.join(this.config.scriptsDir, "vosk_stream_worker.py");
    this.requestTimeoutMs = Number.isFinite(this.config.voskRequestTimeoutMs)
      ? this.config.voskRequestTimeoutMs
      : 30000;
  }

  _start() {
    if (this.proc) return;
    if (!fs.existsSync(this.workerPath)) {
      throw new Error(`Vosk worker not found: ${this.workerPath}`);
    }
    if (!this.config.voskModelPath || !fs.existsSync(this.config.voskModelPath)) {
      throw new Error(`Vosk model path not found: ${this.config.voskModelPath || "(unset)"}`);
    }

    this.proc = spawn(this.config.pythonPath, [this.workerPath, this.config.voskModelPath], {
      stdio: ["pipe", "pipe", "pipe"],
      env: getPythonEnv(this.config),
    });

    readline.createInterface({ input: this.proc.stdout, crlfDelay: Infinity }).on("line", (line) => {
      if (!line.trim()) return;
      let msg;
      try {
        msg = JSON.parse(line);
      } catch {
        return;
      }

      const entry = this.pending.get(msg.id);
      if (!entry) return;
      this.pending.delete(msg.id);
      clearTimeout(entry.timer);
      if (msg.error) entry.reject(new Error(msg.error));
      else entry.resolve({ ...msg, backend: "vosk" });
    });

    this.proc.stderr.on("data", (chunk) => {
      const message = chunk.toString().trim();
      if (message) this.emit("debug", message);
    });

    this.proc.on("close", () => {
      this.proc = null;
      for (const entry of this.pending.values()) {
        clearTimeout(entry.timer);
        entry.reject(new Error("Vosk worker exited"));
      }
      this.pending.clear();
    });

    this.proc.on("error", (error) => {
      for (const entry of this.pending.values()) {
        clearTimeout(entry.timer);
        entry.reject(error);
      }
      this.pending.clear();
      this.emit("error", error);
    });
  }

  transcribeChunk({ audioPath, sourceLanguage, targetLanguage }) {
    try {
      this._start();
    } catch (error) {
      return Promise.reject(error);
    }
    const id = String(this.nextId++);

    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error(`Vosk request timed out after ${this.requestTimeoutMs}ms`));
      }, this.requestTimeoutMs);
      this.pending.set(id, { resolve, reject, timer });
      this.proc.stdin.write(
        JSON.stringify({
          id,
          audio_path: audioPath,
          source_language: sourceLanguage || "en",
          target_language: targetLanguage || "en",
        }) + "\n",
        "utf8"
      );
    });
  }

  stop() {
    if (this.proc) {
      this.proc.stdin.end();
      this.proc.kill();
      this.proc = null;
    }
    for (const entry of this.pending.values()) {
      clearTimeout(entry.timer);
      entry.reject(new Error("Vosk worker stopped"));
    }
    this.pending.clear();
  }
}

module.exports = {
  VoskSttEngine,
};
