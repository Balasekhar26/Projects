/**
 * Speech-to-Text Engine Module
 *
 * Provides hybrid STT capabilities:
 * - Offline: Faster Whisper with CPU optimization
 * - Online: OpenAI Whisper API
 * - Automatic fallback and policy-based selection
 */

const { EventEmitter } = require("events");
const path = require("path");
const { spawn } = require("child_process");

/**
 * Base STT Engine Interface
 */
class BaseSttEngine extends EventEmitter {
  constructor(config) {
    super();
    this.config = config;
    this.isProcessing = false;
  }

  async transcribeChunk(input) {
    throw new Error("transcribeChunk must be implemented by subclass");
  }

  stop() {
    this.isProcessing = false;
  }

  validateInput(input) {
    if (!input.pcmBuffer) {
      throw new Error("Input must contain pcmBuffer");
    }
    if (!Buffer.isBuffer(input.pcmBuffer)) {
      throw new Error("pcmBuffer must be a Buffer");
    }
  }
}

/**
 * Faster Whisper STT Engine (Offline)
 */
class FasterWhisperSttEngine extends BaseSttEngine {
  constructor(config) {
    super(config);
    this.workerPath = config.whisperWorkerPath || path.join(config.scriptsDir, "whisper_stream_worker.py");
    this.modelPath = config.whisperModelPath || path.join(config.modelsDir, "whisper_tiny");
    this.process = null;
    this.pendingRequests = new Map();
    this.requestId = 0;
  }

  async transcribeChunk(input) {
    this.validateInput(input);

    return new Promise((resolve, reject) => {
      if (!this.process) {
        this.startWorker();
      }

      const requestId = ++this.requestId;
      const request = {
        id: requestId,
        pcmBuffer: input.pcmBuffer,
        language: input.language,
        resolve,
        reject
      };

      this.pendingRequests.set(requestId, request);

      // Send request to worker
      const message = {
        id: requestId,
        pcmData: input.pcmBuffer.toString("base64"),
        language: input.language || "auto"
      };

      this.process.stdin.write(JSON.stringify(message) + "\n");
    });
  }

  startWorker() {
    this.process = spawn(this.config.pythonPath, [this.workerPath], {
      stdio: ["pipe", "pipe", "pipe"],
      env: {
        ...process.env,
        WHISPER_MODEL_PATH: this.modelPath
      }
    });

    this.process.stdout.on("data", (data) => {
      this.handleWorkerResponse(data);
    });

    this.process.stderr.on("data", (data) => {
      const message = data.toString().trim();
      if (message) {
        this.emit("debug", `Whisper worker: ${message}`);
      }
    });

    this.process.on("error", (error) => {
      this.emit("error", error);
      this.cleanupPendingRequests(error);
    });

    this.process.on("close", (code) => {
      this.emit("debug", `Whisper worker exited with code ${code}`);
      this.process = null;
      this.cleanupPendingRequests(new Error(`Worker exited with code ${code}`));
    });
  }

  handleWorkerResponse(data) {
    try {
      const lines = data.toString().split("\n").filter(line => line.trim());
      for (const line of lines) {
        const response = JSON.parse(line.trim());
        const request = this.pendingRequests.get(response.id);

        if (request) {
          this.pendingRequests.delete(response.id);

          if (response.error) {
            request.reject(new Error(response.error));
          } else {
            request.resolve({
              transcript: response.transcript,
              translatedText: response.translated_text,
              detectedLanguage: response.detected_language,
              confidence: response.confidence || 1.0
            });
          }
        }
      }
    } catch (error) {
      this.emit("error", new Error(`Failed to parse worker response: ${error.message}`));
    }
  }

  cleanupPendingRequests(error) {
    for (const [id, request] of this.pendingRequests) {
      request.reject(error);
    }
    this.pendingRequests.clear();
  }

  stop() {
    super.stop();
    if (this.process) {
      this.process.kill();
      this.process = null;
    }
    this.cleanupPendingRequests(new Error("STT engine stopped"));
  }
}

/**
 * OpenAI Whisper STT Engine (Online)
 */
class OpenAiWhisperSttEngine extends BaseSttEngine {
  constructor(config) {
    super(config);
    this.apiKey = config.openAiApiKey;
    this.endpoint = "https://api.openai.com/v1/audio/transcriptions";
  }

  async transcribeChunk(input) {
    this.validateInput(input);

    if (!this.apiKey) {
      throw new Error("OpenAI API key not configured");
    }

    const formData = new FormData();
    formData.append("file", new Blob([input.pcmBuffer], { type: "audio/pcm" }), "audio.pcm");
    formData.append("model", "whisper-1");
    if (input.language && input.language !== "auto") {
      formData.append("language", input.language);
    }

    const response = await fetch(this.endpoint, {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${this.apiKey}`
      },
      body: formData
    });

    if (!response.ok) {
      throw new Error(`OpenAI API error: ${response.status} ${response.statusText}`);
    }

    const result = await response.json();
    return {
      transcript: result.text,
      translatedText: input.translate ? result.text : null, // Whisper API doesn't do translation
      detectedLanguage: result.language || input.language,
      confidence: 1.0 // OpenAI doesn't provide confidence scores
    };
  }

  stop() {
    super.stop();
    // No persistent connections to clean up
  }
}

/**
 * Hybrid STT Engine with automatic fallback
 */
class HybridSttEngine extends EventEmitter {
  constructor(config) {
    super();
    this.config = config;
    this.offline = new FasterWhisperSttEngine(config);
    this.online = new OpenAiWhisperSttEngine(config);

    // Forward events from engines
    this.offline.on("debug", (message) => this.emit("debug", message));
    this.offline.on("error", (error) => this.emit("error", error));
    this.online.on("debug", (message) => this.emit("debug", message));
    this.online.on("error", (error) => this.emit("error", error));
  }

  async transcribeChunk(input) {
    const onlinePolicy = input.onlinePolicy || "auto";

    if (onlinePolicy !== "offline-only") {
      try {
        this.emit("debug", "Trying online STT...");
        const result = await this.online.transcribeChunk(input);
        this.emit("debug", "Online STT successful");
        return result;
      } catch (error) {
        this.emit("debug", `Online STT failed: ${error.message}`);
        if (onlinePolicy === "online-only") {
          throw error;
        }
      }
    }

    this.emit("debug", "Using offline STT");
    return this.offline.transcribeChunk(input);
  }

  stop() {
    this.offline.stop();
    this.online.stop();
  }
}

/**
 * STT Engine Factory
 */
class SttEngineFactory {
  static createEngine(type, config) {
    switch (type) {
      case "faster-whisper":
        return new FasterWhisperSttEngine(config);
      case "openai-whisper":
        return new OpenAiWhisperSttEngine(config);
      case "hybrid":
      default:
        return new HybridSttEngine(config);
    }
  }

  static getAvailableEngines() {
    return [
      {
        id: "hybrid",
        name: "Hybrid (Online + Offline Fallback)",
        requiresApiKey: true,
        supportsOffline: true
      },
      {
        id: "faster-whisper",
        name: "Faster Whisper (Offline Only)",
        requiresApiKey: false,
        supportsOffline: true
      },
      {
        id: "openai-whisper",
        name: "OpenAI Whisper (Online Only)",
        requiresApiKey: true,
        supportsOffline: false
      }
    ];
  }
}

module.exports = {
  BaseSttEngine,
  FasterWhisperSttEngine,
  OpenAiWhisperSttEngine,
  HybridSttEngine,
  SttEngineFactory
};