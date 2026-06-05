const { EventEmitter } = require("events");
const { spawn } = require("child_process");
const readline = require("readline");
const path = require("path");
const fs = require("fs/promises");
const { getPythonEnv } = require("../config");

/**
 * Persistent SAPI TTS speaker.
 * Uses a long-lived Python process (sapi_tts_worker.py) instead of
 * spawning PowerShell per call — reduces latency from ~1500ms to ~50ms.
 */
class Pyttsx3Speaker extends EventEmitter {
  constructor(config) {
    super();
    this.config = config;
    this.proc = null;
    this.pending = new Map();
    this.nextId = 1;
    this.queue = Promise.resolve();
    this.workerPath = path.join(config.scriptsDir, "sapi_tts_worker.py");
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
        else entry.resolve();
      });
    this.proc.stderr.on("data", (d) => this.emit("debug", d.toString().trim()));
    this.proc.on("close", () => {
      this.proc = null;
      for (const e of this.pending.values()) e.reject(new Error("SAPI worker exited"));
      this.pending.clear();
    });
    this.proc.on("error", (err) => {
      for (const e of this.pending.values()) e.reject(err);
      this.pending.clear();
    });
  }

  speak(text, options = {}) {
    const trimmed = typeof text === "string" ? text.trim() : "";
    if (!trimmed) return Promise.resolve();
    // Queue sequentially so each sentence plays fully before the next
    this.queue = this.queue
      .then(() => this._speak(trimmed, options))
      .catch((err) => this.emit("debug", `SAPI speak error: ${err.message}`));
    return Promise.resolve(); // pipeline never waits
  }

  async _speak(text, options) {
    this._start();
    const device = options.outputDeviceName || this.config.ttsOutputDeviceName || "";
    await fs.mkdir(this.config.tempDir, { recursive: true });
    const wavPath = path.join(
      this.config.tempDir,
      `sapi-${Date.now()}-${Math.random().toString(16).slice(2, 8)}.wav`
    );
    // Synthesize WAV
    await this._synthesize(text, wavPath);
    // Play fully — awaited so next sentence waits for this to finish
    try {
      await this._play(wavPath, device);
    } finally {
      await fs.rm(wavPath, { force: true }).catch(() => {});
    }
  }

  _synthesize(text, outputWavPath) {
    const id = String(this.nextId++);
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.proc.stdin.write(
        JSON.stringify({ id, text, output_path: outputWavPath, rate: 0 }) + "\n",
        "utf8"
      );
    });
  }

  // Expose _synthesize for TieredSpeechEngine prosody path
  async _synthesizeToWav(text, outputWavPath) {
    this._start();
    await fs.mkdir(this.config.tempDir, { recursive: true });
    return this._synthesize(text, outputWavPath);
  }

  _play(wavPath, outputDeviceName) {
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

module.exports = { Pyttsx3Speaker };
