const fs = require("fs/promises");
const path = require("path");
const { spawn } = require("child_process");

class OpenAiWindowsSpeaker {
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
      `tts-openai-${Date.now()}-${Math.random().toString(16).slice(2)}.wav`
    );

    await fs.mkdir(this.config.tempDir, { recursive: true });
    const audioBuffer = await synthesizeSpeech({
      openAiApiKey: this.config.openAiApiKey,
      model: this.config.openAiTtsModel,
      input: trimmedText,
      voice: options.voiceId || this.config.ttsVoiceName,
      instructions: options.instructions || "",
      language: options.language || this.config.ttsLanguage || undefined,
      speed: typeof options.speed === "number" ? options.speed : 1,
    });
    await fs.writeFile(wavFilePath, audioBuffer);

    try {
      await playWaveFile(this.config, wavFilePath, options.outputDeviceName || this.config.ttsOutputDeviceName);
    } finally {
      await fs.rm(wavFilePath, { force: true }).catch(() => {});
    }
  }
}

async function synthesizeSpeech({ openAiApiKey, model, input, voice, instructions, language, speed }) {
  if (!openAiApiKey) {
    throw new Error("OPENAI_API_KEY is not configured.");
  }

  const response = await fetch("https://api.openai.com/v1/audio/speech", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${openAiApiKey}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      model,
      voice,
      input,
      instructions,
      language,
      format: "wav",
      speed,
    }),
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`OpenAI speech generation failed: ${errorText}`);
  }

  return Buffer.from(await response.arrayBuffer());
}

function playWaveFile(config, wavFilePath, outputDeviceName) {
  return new Promise((resolve, reject) => {
    const args = outputDeviceName
      ? ["-q", wavFilePath, "-t", "waveaudio", outputDeviceName]
      : ["-q", wavFilePath, "-d"];

    const child = spawn(config.soxPath, args, {
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

      reject(new Error(stderr.trim() || `Audio playback failed with exit code ${code}.`));
    });
  });
}

module.exports = {
  OpenAiWindowsSpeaker,
  playWaveFile,
};
