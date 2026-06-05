const readline = require("readline");
const { spawn } = require("child_process");
const { resolveCoreConfig } = require("../config");

class GoogleTranslateClient {
  constructor(config = {}) {
    this.config = resolveCoreConfig(config);
    this.process = null;
    this.pending = new Map();
    this.requestId = 1;
  }

  _start() {
    if (this.process) return;

    this.process = spawn(
      this.config.pythonPath,
      [this.config.googleTranslateWorkerPath, this.config.argosPackagesDir],
      { stdio: ["pipe", "pipe", "pipe"] }
    );

    readline.createInterface({ input: this.process.stdout, crlfDelay: Infinity })
      .on("line", (line) => {
        if (!line.trim()) return;
        let msg;
        try { msg = JSON.parse(line); } catch { return; }
        const entry = this.pending.get(msg.id);
        if (!entry) return;
        this.pending.delete(msg.id);
        if (msg.error) entry.reject(new Error(msg.error));
        else entry.resolve(msg);
      });

    this.process.stderr.on("data", () => {});
    this.process.on("close", () => {
      this.process = null;
      for (const e of this.pending.values()) e.reject(new Error("Google translate worker exited"));
      this.pending.clear();
    });
    this.process.on("error", (err) => {
      for (const e of this.pending.values()) e.reject(err);
      this.pending.clear();
    });
  }

  translate({ text, sourceLanguage, targetLanguage }) {
    this._start();
    const id = String(this.requestId++);
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      const payload = { id, text, source: sourceLanguage || "auto", target: targetLanguage };
      this.process.stdin.write(JSON.stringify(payload) + "\n", "utf8");
    });
  }

  stop() {
    if (this.process) { this.process.stdin.end(); this.process = null; }
  }
}

module.exports = { GoogleTranslateClient };
