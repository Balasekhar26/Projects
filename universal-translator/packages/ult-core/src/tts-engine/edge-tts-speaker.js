const { EventEmitter } = require("events");
const { spawn } = require("child_process");
const readline = require("readline");
const path = require("path");
const fs = require("fs/promises");
const { getPythonEnv } = require("../config");

class EdgeTtsSpeaker extends EventEmitter {
  constructor(config) {
    super();
    this.config = config;
    this.proc = null;
    this.pending = new Map();
    this.nextId = 1;
    this.playQueue = Promise.resolve();
    this.spawnImpl = config?.spawnImpl || spawn;
  }

  _start() {
    if (this.proc) return;
    this.proc = this.spawnImpl(this.config.pythonPath, [this.config.edgeTtsWorkerPath], {
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
      if (msg.error) entry.reject(new Error(msg.error));
      else entry.resolve();
    });
    this.proc.stderr.on("data", (chunk) => this.emit("debug", chunk.toString().trim()));
    this.proc.on("close", () => {
      this.proc = null;
      for (const entry of this.pending.values()) entry.reject(new Error("edge-tts worker exited"));
      this.pending.clear();
    });
    this.proc.on("error", (error) => {
      for (const entry of this.pending.values()) entry.reject(error);
      this.pending.clear();
    });
  }

  speak(text, options = {}) {
    const trimmed = typeof text === "string" ? text.trim() : "";
    if (!trimmed) return Promise.resolve();

    this.playQueue = this.playQueue
      .then(() => this._synthesizeAndPlay(trimmed, options))
      .catch((error) => this.emit("debug", `edge-tts error: ${error.message}`));

    return Promise.resolve();
  }

  async synthesizeToFile(text, options = {}) {
    const trimmed = typeof text === "string" ? text.trim() : "";
    if (!trimmed) throw new Error("Text is required for synthesis");

    this._start();
    const lang = options.language || this.config.targetLanguage || "en";
    const outputPath = options.outputPath;
    if (!outputPath) throw new Error("outputPath is required");

    await fs.mkdir(path.dirname(outputPath), { recursive: true });
    const id = String(this.nextId++);
    await new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      const safeText = trimmed.replace(/[\u0000-\u001f\u007f-\u009f]/g, "");
      const payload = JSON.stringify({
        id,
        text: safeText,
        lang,
        output_path: outputPath,
        sample_rate: this.config.sampleRate,
      });
      this.proc.stdin.write(Buffer.from(payload + "\n", "utf8"));
    });
    return outputPath;
  }

  async _synthesizeAndPlay(text, options) {
    const lang = options.language || this.config.targetLanguage || "en";
    const device = options.outputDeviceName || this.config.ttsOutputDeviceName || "";
    const wavPath = path.join(
      this.config.tempDir,
      `edge-${Date.now()}-${Math.random().toString(16).slice(2, 8)}.wav`
    );

    await this.synthesizeToFile(text, { language: lang, outputPath: wavPath });
    try {
      await this._playWav(wavPath, device);
      this.emit("debug", `TTS OK [edge-tts] lang=${lang}`);
    } finally {
      await fs.rm(wavPath, { force: true }).catch(() => {});
    }
  }

  _playWav(wavPath, outputDeviceName) {
    return new Promise((resolve, reject) => {
      const args = outputDeviceName ? ["-q", wavPath, "-t", "waveaudio", outputDeviceName] : ["-q", wavPath, "-d"];
      const child = this.spawnImpl(this.config.soxPath, args, { stdio: ["ignore", "pipe", "pipe"] });
      let stderr = "";
      child.stderr.on("data", (chunk) => {
        stderr += chunk.toString();
      });
      child.on("error", reject);
      child.on("close", (code) => {
        if (code === 0) resolve();
        else reject(new Error(stderr.trim() || `SoX playback failed (exit ${code})`));
      });
    });
  }

  stop() {
    if (this.proc) {
      this.proc.stdin.end();
      this.proc = null;
    }
  }
}

module.exports = { EdgeTtsSpeaker };
