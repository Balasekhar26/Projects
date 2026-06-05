const fs = require("fs/promises");

class OpenAiWhisperSttEngine {
  constructor(config) {
    this.config = config;
  }

  async transcribeChunk({ audioPath, sourceLanguage, targetLanguage }) {
    if (!this.config.openAiApiKey) {
      throw new Error("OPENAI_API_KEY is not configured.");
    }

    const audioBuffer = await fs.readFile(audioPath);
    const blob = new Blob([audioBuffer], { type: "audio/wav" });
    const formData = new FormData();
    formData.append("file", blob, "chunk.wav");
    formData.append("model", "whisper-1");
    if (sourceLanguage) {
      formData.append("language", sourceLanguage);
    }

    const response = await fetch("https://api.openai.com/v1/audio/transcriptions", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${this.config.openAiApiKey}`,
      },
      body: formData,
    });

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`OpenAI transcription failed: ${errorText}`);
    }

    const transcription = await response.json();
    return {
      transcript: transcription.text || "",
      translated_text: "",
      detected_language: sourceLanguage || "",
      target_language: targetLanguage || "",
      backend: "openai-whisper",
    };
  }

  stop() {}
}

module.exports = {
  OpenAiWhisperSttEngine,
};
