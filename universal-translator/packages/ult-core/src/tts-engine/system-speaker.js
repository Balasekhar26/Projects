const fs = require("fs/promises");
const path = require("path");
const { spawn } = require("child_process");

const { playWaveFile } = require("./openai-speaker");

class WindowsSystemSpeaker {
  constructor(config) {
    this.config = config;
  }

  async speak(text, options = {}) {
    const trimmedText = typeof text === "string" ? text.trim() : "";
    if (!trimmedText) {
      return;
    }

    const wavFilePath = path.join(
      this.config.tempDir,
      `tts-system-${Date.now()}-${Math.random().toString(16).slice(2)}.wav`
    );

    await fs.mkdir(this.config.tempDir, { recursive: true });
    await synthesizeSpeech(this.config, {
      text: trimmedText,
      voiceName: options.systemVoiceName || "",
      rate: Number.isFinite(options.rate) ? options.rate : 0,
      outputWaveFilePath: wavFilePath,
    });

    try {
      await playWaveFile(this.config, wavFilePath, options.outputDeviceName || this.config.ttsOutputDeviceName);
    } finally {
      await fs.rm(wavFilePath, { force: true }).catch(() => {});
    }
  }
}

function synthesizeSpeech(config, options) {
  return new Promise((resolve, reject) => {
    const child = spawn("powershell", [
      "-NoProfile",
      "-ExecutionPolicy",
      "Bypass",
      "-File",
      config.speakScriptPath,
      "-Text",
      options.text,
      "-VoiceName",
      options.voiceName || "",
      "-Rate",
      String(options.rate || 0),
      "-OutputWaveFilePath",
      options.outputWaveFilePath,
    ]);

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

      reject(new Error(stderr.trim() || `System speech synthesis failed with exit code ${code}.`));
    });
  });
}

module.exports = {
  WindowsSystemSpeaker,
};
