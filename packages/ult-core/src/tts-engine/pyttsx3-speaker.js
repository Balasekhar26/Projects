const { EventEmitter } = require("events");
const { spawn } = require("child_process");
const readline = require("readline");

class Pyttsx3Speaker extends EventEmitter {
  constructor(config) {
    super();
    this.config = config;
    this.process = null;
    this.pending = new Map();
    this.nextId = 1;
    this.queue = Promise.resolve();
  }

  _start() {
    if (this.process) return;

    const workerPath = require("path").join(
      this.config.scriptsDir,
      "pyttsx3_worker.py"
    );

    this.process = spawn(this.config.pythonPath, [workerPath], {
      stdio: ["pipe", "pipe", "pipe"],
    });

    readline.createInterface({ input: this.process.stdout, crlfDelay: Infinity })
      .on("line", (line) => {
        if (!line.trim()) return;
        let msg;
        try { msg = JSON.parse(line); } catch { return; }
        const entry = this.pending.get(msg.id);
        if (!entry) return;
        this.pending.delete(msg.id);
        if (msg.error) entry.reject(new Error(msg.error));
        else entry.resolve();
      });

    this.process.stderr.on("data", (chunk) => {
      this.emit("debug", chunk.toString().trim());
    });

    this.process.on("close", () => {
      this.process = null;
      for (const entry of this.pending.values()) {
        entry.reject(new Error("pyttsx3 worker exited unexpectedly."));
      }
      this.pending.clear();
    });
  }

  speak(text, options = {}) {
    const trimmed = typeof text === "string" ? text.trim() : "";
    if (!trimmed) return Promise.resolve();

    this.queue = this.queue.then(() => this._send(trimmed, options)).catch(() => {});
    return this.queue;
  }

  _send(text, options) {
    this._start();
    const id = String(this.nextId++);
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      const payload = { id, text };
      if (options.rate) payload.rate = options.rate;
      this.process.stdin.write(JSON.stringify(payload) + "\n", "utf8");
    });
  }

  stop() {
    if (this.process) {
      this.process.stdin.end();
      this.process = null;
    }
  }
}

module.exports = { Pyttsx3Speaker };
