const fs = require("fs/promises");
const path = require("path");
const { EventEmitter } = require("events");

class ElevenLabsSpeaker extends EventEmitter {
  constructor(config) {
    super();
    this.config = config;
    this.apiKey = config.elevenlabsApiKey;
    this.baseUrl = "https://api.elevenlabs.io/v1";
  }

  async synthesizeToWave({ text, voiceId, outputPath, model = "eleven_multilingual_v2" }) {
    if (!this.apiKey) {
      throw new Error("ElevenLabs API key not configured");
    }

    if (!voiceId) {
      throw new Error("Voice ID required for ElevenLabs synthesis");
    }

    await fs.mkdir(path.dirname(outputPath), { recursive: true });

    const response = await fetch(`${this.baseUrl}/text-to-speech/${voiceId}`, {
      method: "POST",
      headers: {
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
        "xi-api-key": this.apiKey,
      },
      body: JSON.stringify({
        text,
        model_id: model,
        voice_settings: {
          stability: 0.35,
          similarity_boost: 0.8,
          style: 0.45,
          use_speaker_boost: true,
        },
      }),
    });

    if (!response.ok) {
      const error = await response.text();
      throw new Error(`ElevenLabs API error: ${response.status} ${error}`);
    }

    const arrayBuffer = await response.arrayBuffer();
    const buffer = Buffer.from(arrayBuffer);

    await fs.writeFile(outputPath, buffer);
    return outputPath;
  }

  async getVoices() {
    if (!this.apiKey) {
      throw new Error("ElevenLabs API key not configured");
    }

    const response = await fetch(`${this.baseUrl}/voices`, {
      headers: {
        "xi-api-key": this.apiKey,
      },
    });

    if (!response.ok) {
      throw new Error(`ElevenLabs API error: ${response.status}`);
    }

    return await response.json();
  }

  async cloneVoice({ name, description, files }) {
    if (!this.apiKey) {
      throw new Error("ElevenLabs API key not configured");
    }

    const formData = new FormData();
    formData.append("name", name);
    formData.append("description", description || "");

    for (const file of files) {
      formData.append("files", file);
    }

    const response = await fetch(`${this.baseUrl}/voices/add`, {
      method: "POST",
      headers: {
        "xi-api-key": this.apiKey,
      },
      body: formData,
    });

    if (!response.ok) {
      const error = await response.text();
      throw new Error(`ElevenLabs voice cloning error: ${response.status} ${error}`);
    }

    return await response.json();
  }
}

module.exports = {
  ElevenLabsSpeaker,
};
