const fs = require("fs/promises");
const path = require("path");
const { spawn } = require("child_process");
const { synthesizeSpeech } = require("../openai/audio");

class WindowsSpeaker {
  constructor(config) {
    this.config = config;
    this.queue = Promise.resolve();
  }

  speak(text, options = {}) {
    const trimmedText = typeof text === "string" ? text.trim() : "";
    if (!trimmedText) {
      return Promise.resolve();
    }

    this.queue = this.queue
      .then(() => this.runSpeech(trimmedText, options))
      .catch(() => this.runSpeech(trimmedText, options));

    return this.queue;
  }

  runSpeech(text, options) {
    const outputDeviceName = typeof this.config.ttsOutputDeviceName === "string"
      ? this.config.ttsOutputDeviceName.trim()
      : "";

    const wavFilePath = path.join(
      this.config.tempDir,
      `tts-${Date.now()}-${Math.random().toString(16).slice(2)}.wav`
    );

    return fs
      .mkdir(this.config.tempDir, { recursive: true })
      .then(async () => {
        const audioBuffer = await synthesizeSpeech({
          input: text,
          voice: options.voiceId || this.config.ttsVoiceName,
          instructions: options.instructions || "",
          language: options.language || this.config.ttsLanguage || undefined,
          speed: typeof options.speed === "number" ? options.speed : 1,
          format: "wav",
        });

        await fs.writeFile(wavFilePath, audioBuffer);
      })
      .then(() =>
        outputDeviceName
          ? this.playWaveFileOnDevice(wavFilePath, outputDeviceName)
          : this.playWaveFileOnDefaultDevice(wavFilePath)
      )
      .finally(() => fs.rm(wavFilePath, { force: true }).catch(() => {}));
  }

  playWaveFileOnDevice(wavFilePath, outputDeviceName) {
    return this.runProcess(
      this.config.soxPath,
      ["-q", wavFilePath, "-t", "waveaudio", outputDeviceName],
      `Audio routing failed for output device "${outputDeviceName}"`
    );
  }

  playWaveFileOnDefaultDevice(wavFilePath) {
    return this.runProcess(
      this.config.soxPath,
      ["-q", wavFilePath, "-d"],
      "Audio playback failed on the default device"
    );
  }

  runProcess(command, args, fallbackMessage) {
    return new Promise((resolve, reject) => {
      const child = spawn(command, args, {
        stdio: ["ignore", "pipe", "pipe"],
      });

      let stderr = "";

      child.stderr.on("data", (chunk) => {
        stderr += chunk.toString();
      });

      child.on("error", reject);
      child.on("close", (code) => {
        if (code === 0) {
          resolve();
          return;
        }

        reject(new Error(stderr.trim() || `${fallbackMessage} with exit code ${code}.`));
      });
    });
  }
}

module.exports = {
  WindowsSpeaker,
};
