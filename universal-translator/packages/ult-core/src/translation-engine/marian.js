const { spawn } = require("child_process");
const readline = require("readline");
const path = require("path");
const { getPythonEnv, resolveCoreConfig } = require("../config");

class MarianTranslateClient {
  constructor(config = {}) {
    this.config = resolveCoreConfig(config);
    this.proc = null;
    this.pending = new Map();
    this.nextId = 1;
    this.workerPath = this.config.marianWorkerPath || path.join(this.config.scriptsDir, "marian_translate_worker.py");
  }

  _start() {
    if (this.proc) return;
    const env = {
      ...getPythonEnv(this.config),
      ULT_MARIAN_MODELS_DIR: path.join(this.config.modelsDir, "marian"),
    };
    this.proc = spawn(this.config.pythonPath, [this.workerPath], {
      stdio: ["pipe", "pipe", "pipe"],
      env,
    });
    readline.createInterface({ input: this.proc.stdout, crlfDelay: Infinity })
      .on("line", (line) => {
        if (!line.trim()) return;
        let msg;
        try { msg = JSON.parse(line); } catch { return; }
        const entry = this.pending.get(msg.id);
        if (!entry) return;
        this.pending.delete(msg.id);
        if (msg.error) entry.reject(new Error(msg.error));
        else entry.resolve(msg.translated_text || "");
      });
    this.proc.stderr.on("data", () => {});
    this.proc.on("close", () => {
      this.proc = null;
      for (const e of this.pending.values()) e.reject(new Error("MarianMT worker exited"));
      this.pending.clear();
    });
    this.proc.on("error", (err) => {
      for (const e of this.pending.values()) e.reject(err);
      this.pending.clear();
    });
  }

  translate({ text, sourceLanguage, targetLanguage }) {
    this._start();
    const id = String(this.nextId++);
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.proc.stdin.write(
        JSON.stringify({ id, text, source: sourceLanguage || "en", target: targetLanguage }) + "\n",
        "utf8"
      );
    });
  }

  stop() {
    if (this.proc) { this.proc.stdin.end(); this.proc = null; }
  }
}

module.exports = { MarianTranslateClient };
