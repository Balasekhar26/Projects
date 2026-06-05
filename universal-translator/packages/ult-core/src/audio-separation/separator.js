const { spawn } = require("child_process");
const readline = require("readline");
const path = require("path");
const { getPythonEnv, resolveCoreConfig } = require("../config");

class AudioSeparator {
  constructor(config = {}) {
    this.config = resolveCoreConfig(config);
    this.proc = null;
    this.pending = new Map();
    this.nextId = 1;
    this.workerPath = this.config.audioSeparatorPath || path.join(this.config.scriptsDir, "audio_separator_worker.py");
  }

  _start() {
    if (this.proc) return;
    this.proc = spawn(this.config.pythonPath, [this.workerPath], {
      stdio: ["pipe", "pipe", "pipe"],
      env: getPythonEnv(this.config),
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
        else entry.resolve(msg);
      });
    this.proc.on("close", () => {
      for (const e of this.pending.values()) e.reject(new Error("Separator worker exited"));
      this.pending.clear();
      this.proc = null;
    });
  }

  /**
   * Separate speech from background audio.
   * Returns { has_speech, speech_ratio, speechPath, bgPath }
   */
  separate({ audioPath, speechPath, bgPath }) {
    this._start();
    const id = String(this.nextId++);
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.proc.stdin.write(
        JSON.stringify({ id, audio_path: audioPath, output_speech: speechPath, output_bg: bgPath }) + "\n",
        "utf8"
      );
    }).then((result) => ({ ...result, speechPath, bgPath }));
  }

  stop() {
    if (this.proc) { this.proc.stdin.end(); this.proc = null; }
  }
}

module.exports = { AudioSeparator };
