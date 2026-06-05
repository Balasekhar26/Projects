/**
 * Translation Engine Module
 *
 * Provides hybrid translation capabilities:
 * - Online: LibreTranslate API
 * - Offline: Argos Translate
 * - Smart fallback and language normalization
 */

const { EventEmitter } = require("events");
const { spawn } = require("child_process");
const path = require("path");
const { getPythonEnv } = require("../../packages/ult-core/src/config");

/**
 * Base Translation Engine Interface
 */
class BaseTranslationEngine extends EventEmitter {
  constructor(config) {
    super();
    this.config = config;
  }

  async translate(input) {
    throw new Error("translate must be implemented by subclass");
  }

  stop() {
    // Default no-op
  }

  normalizeText(value) {
    return typeof value === "string" ? value.trim() : "";
  }

  normalizeLanguage(value) {
    return typeof value === "string" ? value.trim().toLowerCase() : "";
  }
}

/**
 * LibreTranslate Online Engine
 */
class LibreTranslateEngine extends BaseTranslationEngine {
  constructor(config) {
    super(config);
    this.endpoint = config.libreTranslateEndpoint || "https://libretranslate.com/translate";
  }

  async translate(input) {
    const { text, sourceLanguage, targetLanguage } = input;

    const normalizedText = this.normalizeText(text);
    const normalizedSource = this.normalizeLanguage(sourceLanguage);
    const normalizedTarget = this.normalizeLanguage(targetLanguage);

    if (!normalizedText) {
      return { translatedText: "", backend: "none" };
    }

    if (!normalizedTarget || normalizedTarget === normalizedSource) {
      return { translatedText: normalizedText, backend: "passthrough" };
    }

    const response = await fetch(this.endpoint, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        q: normalizedText,
        source: normalizedSource === "auto" ? "auto" : normalizedSource,
        target: normalizedTarget,
        format: "text"
      })
    });

    if (!response.ok) {
      throw new Error(`LibreTranslate API error: ${response.status} ${response.statusText}`);
    }

    const result = await response.json();
    return {
      translatedText: result.translatedText,
      backend: "libretranslate",
      detectedLanguage: result.detectedLanguage
    };
  }
}

/**
 * Argos Translate Offline Engine
 */
class ArgosTranslateEngine extends BaseTranslationEngine {
  constructor(config) {
    super(config);
    this.workerPath = config.argosWorkerPath || path.join(config.scriptsDir, "argos_translate_worker.py");
    this.packagesDir = config.argosPackagesDir || path.join(config.modelsDir, "argos");
    this.process = null;
    this.pendingRequests = new Map();
    this.requestId = 0;
  }

  async translate(input) {
    const { text, sourceLanguage, targetLanguage } = input;

    const normalizedText = this.normalizeText(text);
    const normalizedSource = this.normalizeLanguage(sourceLanguage);
    const normalizedTarget = this.normalizeLanguage(targetLanguage);

    if (!normalizedText) {
      return { translatedText: "", backend: "none" };
    }

    if (!normalizedTarget || normalizedTarget === normalizedSource) {
      return { translatedText: normalizedText, backend: "passthrough" };
    }

    return new Promise((resolve, reject) => {
      if (!this.process) {
        this.startWorker();
      }

      const requestId = ++this.requestId;
      const request = {
        id: requestId,
        text: normalizedText,
        sourceLanguage: normalizedSource,
        targetLanguage: normalizedTarget,
        resolve,
        reject
      };

      this.pendingRequests.set(requestId, request);

      // Send request to worker
      const message = {
        id: requestId,
        text: normalizedText,
        from: normalizedSource,
        to: normalizedTarget
      };

      this.process.stdin.write(JSON.stringify(message) + "\n");
    });
  }

  startWorker() {
    const pythonEnv = getPythonEnv(this.config);

    this.process = spawn(this.config.pythonPath, [this.workerPath], {
      stdio: ["pipe", "pipe", "pipe"],
      env: {
        ...pythonEnv,
        ARGOS_PACKAGES_DIR: this.packagesDir
      }
    });

    this.process.stdout.on("data", (data) => {
      this.handleWorkerResponse(data);
    });

    this.process.stderr.on("data", (data) => {
      const message = data.toString().trim();
      if (message) {
        this.emit("debug", `Argos worker: ${message}`);
      }
    });

    this.process.on("error", (error) => {
      this.emit("error", error);
      this.cleanupPendingRequests(error);
    });

    this.process.on("close", (code) => {
      this.emit("debug", `Argos worker exited with code ${code}`);
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
              translatedText: response.translated_text,
              backend: "argos"
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
    if (this.process) {
      this.process.kill();
      this.process = null;
    }
    this.cleanupPendingRequests(new Error("Translation engine stopped"));
  }
}

/**
 * Hybrid Translation Engine with automatic fallback
 */
class HybridTranslationEngine extends EventEmitter {
  constructor(config) {
    super(config);
    this.config = config;
    this.online = new LibreTranslateEngine(config);
    this.offline = new ArgosTranslateEngine(config);

    // Forward events
    this.offline.on("debug", (message) => this.emit("debug", message));
    this.offline.on("error", (error) => this.emit("error", error));
  }

  async translate(input) {
    const {
      transcript,
      whisperTranslation,
      detectedLanguage,
      sourceLanguage,
      targetLanguage,
      onlinePolicy = "auto"
    } = input;

    const normalizedTranscript = this.normalizeText(transcript);
    const normalizedWhisper = this.normalizeText(whisperTranslation);
    const normalizedSource = this.normalizeLanguage(sourceLanguage);
    const normalizedTarget = this.normalizeLanguage(targetLanguage);
    const normalizedDetected = this.normalizeLanguage(detectedLanguage) || normalizedSource || "auto";

    // Early returns for edge cases
    if (!normalizedTranscript && !normalizedWhisper) {
      return { translatedText: "", backend: "none" };
    }

    if (!normalizedTarget || normalizedTarget === normalizedSource) {
      return { translatedText: normalizedTranscript, backend: "passthrough" };
    }

    // Use Whisper translation if available and targeting English
    if (normalizedTarget === "en" && normalizedWhisper) {
      return { translatedText: normalizedWhisper, backend: "whisper" };
    }

    if (!normalizedTranscript) {
      return { translatedText: "", backend: "none" };
    }

    // Try online translation first (unless offline-only)
    if (onlinePolicy !== "offline-only") {
      try {
        this.emit("debug", "Trying online translation...");
        const result = await this.online.translate({
          text: normalizedTranscript,
          sourceLanguage: normalizedDetected,
          targetLanguage: normalizedTarget
        });
        this.emit("debug", "Online translation successful");
        return result;
      } catch (error) {
        this.emit("debug", `Online translation failed: ${error.message}`);
        if (onlinePolicy === "online-only") {
          throw error;
        }
      }
    }

    // Fall back to offline translation
    this.emit("debug", "Using offline translation");
    return this.offline.translate({
      text: normalizedTranscript,
      sourceLanguage: normalizedDetected,
      targetLanguage: normalizedTarget
    });
  }

  stop() {
    this.offline.stop();
    this.online.stop();
  }

  // Utility methods
  normalizeText(value) {
    return typeof value === "string" ? value.trim() : "";
  }

  normalizeLanguage(value) {
    return typeof value === "string" ? value.trim().toLowerCase() : "";
  }
}

/**
 * Translation Engine Factory
 */
class TranslationEngineFactory {
  static createEngine(type, config) {
    switch (type) {
      case "libretranslate":
        return new LibreTranslateEngine(config);
      case "argos":
        return new ArgosTranslateEngine(config);
      case "hybrid":
      default:
        return new HybridTranslationEngine(config);
    }
  }

  static getAvailableEngines() {
    return [
      {
        id: "hybrid",
        name: "Hybrid (Online + Offline Fallback)",
        requiresApiKey: false,
        supportsOffline: true
      },
      {
        id: "libretranslate",
        name: "LibreTranslate (Online Only)",
        requiresApiKey: false,
        supportsOffline: false
      },
      {
        id: "argos",
        name: "Argos Translate (Offline Only)",
        requiresApiKey: false,
        supportsOffline: true
      }
    ];
  }

  static getSupportedLanguages() {
    return [
      { code: "en", name: "English" },
      { code: "es", name: "Spanish" },
      { code: "fr", name: "French" },
      { code: "de", name: "German" },
      { code: "it", name: "Italian" },
      { code: "pt", name: "Portuguese" },
      { code: "ru", name: "Russian" },
      { code: "ja", name: "Japanese" },
      { code: "ko", name: "Korean" },
      { code: "zh", name: "Chinese" },
      { code: "ar", name: "Arabic" },
      { code: "hi", name: "Hindi" },
      // Add more as needed
    ];
  }
}

module.exports = {
  BaseTranslationEngine,
  LibreTranslateEngine,
  ArgosTranslateEngine,
  HybridTranslationEngine,
  TranslationEngineFactory
};