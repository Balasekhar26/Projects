const { EventEmitter } = require("events");
const { spawn } = require("child_process");
const readline = require("readline");
const path = require("path");
const fs = require("fs/promises");
const { getPythonEnv } = require("../config");

class GTtsSpeaker extends EventEmitter {
  constructor(config) {
    super();
    this.config = config;
    this.proc    = null;
    this.pending = new Map();
    this.nextId  = 1;
  }

  _start() {
    if (this.proc) return;
    this.proc = spawn(this.config.pythonPath, [this.config.gTtsWorkerPath], {
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
        else entry.resolve();
      });
    this.proc.stderr.on("data", (d) => this.emit("debug", d.toString().trim()));
    this.proc.on("close", () => {
      this.proc = null;
      for (const e of this.pending.values()) e.reject(new Error("gTTS worker exited"));
      this.pending.clear();
    });
    this.proc.on("error", (err) => {
      for (const e of this.pending.values()) e.reject(err);
      this.pending.clear();
    });
  }

  /**
   * speak() returns immediately — synthesis + playback run fully in background.
   * This means the pipeline is NEVER blocked waiting for TTS.
   */
  speak(text, options = {}) {
    const trimmed = typeof text === "string" ? text.trim() : "";
    if (!trimmed) return Promise.resolve();

    // Fire-and-forget — do NOT await, do NOT queue
    this._synthesizeAndPlay(trimmed, options)
      .catch((err) => this.emit("debug", `gTTS bg error: ${err.message}`));

    // Return resolved immediately so pipeline continues
    return Promise.resolve();
  }

  async _synthesizeAndPlay(text, options) {
    this._start();
    const lang   = options.language || this.config.targetLanguage || "en";
    const device = options.outputDeviceName || this.config.ttsOutputDeviceName || "";
    await fs.mkdir(this.config.tempDir, { recursive: true });

    const wavPath = path.join(
      this.config.tempDir,
      `gtts-${Date.now()}-${Math.random().toString(16).slice(2, 8)}.wav`
    );

    const id = String(this.nextId++);

    // Step 1: synthesize WAV (gTTS network call + PyAV decode)
    await new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.proc.stdin.write(
        JSON.stringify({ id, text, lang, output_path: wavPath }) + "\n",
        "utf8"
      );
    });

    // Step 2: play WAV via SoX
    try {
      await this._playWav(wavPath, device);
      this.emit("debug", `TTS OK [gTTS] lang=${lang}`);
    } finally {
      await fs.rm(wavPath, { force: true }).catch(() => {});
    }
  }

  _playWav(wavPath, outputDeviceName) {
    return new Promise((resolve, reject) => {
      const args = outputDeviceName
        ? ["-q", wavPath, "-t", "waveaudio", outputDeviceName]
        : ["-q", wavPath, "-d"];
      const child = spawn(this.config.soxPath, args, { stdio: ["ignore", "pipe", "pipe"] });
      let stderr = "";
      child.stderr.on("data", (d) => { stderr += d.toString(); });
      child.on("error", reject);
      child.on("close", (code) => {
        if (code === 0) resolve();
        else reject(new Error(stderr.trim() || `SoX playback failed (exit ${code})`));
      });
    });
  }

  stop() {
    if (this.proc) { this.proc.stdin.end(); this.proc = null; }
  }
}

module.exports = { GTtsSpeaker };
