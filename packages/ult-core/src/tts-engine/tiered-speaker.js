const fs = require("fs/promises");
const path = require("path");
const { EventEmitter } = require("events");

const { describeExpressiveness } = require("../../../../src/audio/expressiveness");
const { VoiceExprexivenessAnalyzer } = require("../../../../src/audio/expressiveness-analyzer");
const { OpenAiWindowsSpeaker, playWaveFile } = require("./openai-speaker");
const { WindowsSystemSpeaker } = require("./system-speaker");
const { XttsVoiceCloneEngine } = require("../voice-clone/xtts");
const { Pyttsx3Speaker } = require("./pyttsx3-speaker");

class TieredSpeechEngine extends EventEmitter {
  constructor(config) {
    super();
    this.config = config;
    this.openAiSpeaker = new OpenAiWindowsSpeaker(config);
    this.systemSpeaker = new WindowsSystemSpeaker(config);
    this.pyttsx3Speaker = new Pyttsx3Speaker(config);
    this.xttsEngine = new XttsVoiceCloneEngine(config);
    this.emotionAnalyzer = new VoiceExprexivenessAnalyzer(config);
    this.fallbackLog = [];
  }

  /**
   * Enhanced speak with comprehensive fallback chain
   * Priority: XTTS (voice clone) → OpenAI TTS → System TTS → Silent
   */
  async speak(text, options = {}) {
    const trimmedText = typeof text === "string" ? text.trim() : "";
    if (!trimmedText) {
      return;
    }

    const sessionId = `tts-${Date.now()}-${Math.random().toString(16).slice(2, 8)}`;
    const logEntry = {
      sessionId,
      text: trimmedText.substring(0, 100),
      timestamp: new Date().toISOString(),
      attempts: []
    };

    try {
      // Analyze emotion if enabled and audio analysis provided
      let emotionAnalysis = null;
      let emotionInstructions = "";
      
      if (options.preserveEmotion) {
        emotionAnalysis = this.emotionAnalyzer.analyzeExpressiveness(
          options.analysis,
          options.transcript || trimmedText
        );
        logEntry.emotion = emotionAnalysis;
        emotionInstructions = emotionAnalysis.ttsInstructions || "";
        this.emit("emotion-detected", {
          sessionId,
          emotion: emotionAnalysis.detectedEmotion,
          confidence: emotionAnalysis.confidence
        });
      }

      const instructions =
        options.instructions ||
        emotionInstructions ||
        (options.preserveEmotion
          ? describeExpressiveness({
              analysis: options.analysis,
              transcript: options.transcript || trimmedText,
              targetLanguage: options.language || this.config.ttsLanguage,
            })
          : "");

      // Tier 1: XTTS Voice Clone (offline, highest quality for custom voices)
      if (options.voiceProfile?.provider === "xtts" && options.voiceProfile.samplePath) {
        logEntry.attempts.push("xtts");
        try {
          const wavFilePath = path.join(
            this.config.tempDir,
            `tts-xtts-${sessionId}.wav`
          );
          await this.xttsEngine.synthesizeToWave({
            text: trimmedText,
            language: options.language || this.config.ttsLanguage || "en",
            samplePath: options.voiceProfile.samplePath,
            outputPath: wavFilePath,
          });

          try {
            await playWaveFile(this.config, wavFilePath, options.outputDeviceName || this.config.ttsOutputDeviceName);
            logEntry.success = "xtts";
            this.emit("tts-method", { method: "xtts", sessionId });
            this.fallbackLog.push(logEntry);
            return;
          } finally {
            await fs.rm(wavFilePath, { force: true }).catch(() => {});
          }
        } catch (error) {
          this.emit("debug", `XTTS synthesis failed: ${error.message}`);
          if (options.onlinePolicy === "offline-only") {
            throw error;
          }
          // Continue to next tier
        }
      }

      // Tier 2: OpenAI TTS (online, high quality)
      if (this.config.openAiApiKey && options.onlinePolicy !== "offline-only") {
        logEntry.attempts.push("openai");
        try {
          await this.openAiSpeaker.speak(trimmedText, {
            voiceId: normalizeVoiceId(options.voiceProfile?.id || options.voiceId),
            instructions,
            language: options.language,
            speed: options.speed,
            outputDeviceName: options.outputDeviceName,
          });
          logEntry.success = "openai";
          this.emit("tts-method", { method: "openai", sessionId });
          this.fallbackLog.push(logEntry);
          return;
        } catch (error) {
          this.emit("debug", `OpenAI TTS failed: ${error.message}`);
          if (options.onlinePolicy === "online-only") {
            throw error;
          }
        }
      }

      // Tier 3: pyttsx3 offline TTS (free, no SoX, speaks to default speaker)
      logEntry.attempts.push("pyttsx3");
      try {
        await this.pyttsx3Speaker.speak(trimmedText, { rate: options.rate });
        logEntry.success = "pyttsx3";
        this.emit("tts-method", { method: "pyttsx3", sessionId });
        this.fallbackLog.push(logEntry);
        return;
      } catch (error) {
        this.emit("debug", `pyttsx3 TTS failed: ${error.message}`);
      }

      // Tier 4: Windows System TTS via SoX WAV route
      logEntry.attempts.push("system");
      try {
        await this.systemSpeaker.speak(trimmedText, {
          systemVoiceName: options.voiceProfile?.systemVoiceName || "",
          outputDeviceName: options.outputDeviceName,
          rate: options.rate,
        });
        logEntry.success = "system";
        this.emit("tts-method", { method: "system-tts", sessionId });
        this.fallbackLog.push(logEntry);
        return;
      } catch (error) {
        this.emit("debug", `System TTS failed: ${error.message}`);
        // Continue to final fallback
      }

      // Tier 4: Silent playback (no error thrown, but logs the failure)
      logEntry.success = "silent";
      logEntry.warning = "All TTS engines unavailable; playback skipped";
      this.emit("warn", `Could not produce audio output: all TTS methods failed. Text: "${trimmedText.substring(0, 50)}..."`);
      this.fallbackLog.push(logEntry);
    } catch (error) {
      logEntry.error = error.message;
      this.fallbackLog.push(logEntry);
      this.emit("error", error);
    }
  }

  /**
   * Get TTS fallback statistics
   */
  getStatistics() {
    const stats = {
      totalSessions: this.fallbackLog.length,
      successByMethod: {},
      failureCount: 0,
      averageFallbacksPerSession: 0,
      emotionStats: this.getEmotionStatistics()
    };

    let totalFallbacks = 0;

    for (const entry of this.fallbackLog) {
      if (entry.success) {
        stats.successByMethod[entry.success] = (stats.successByMethod[entry.success] || 0) + 1;
      } else {
        stats.failureCount++;
      }
      totalFallbacks += entry.attempts.length;
    }

    if (stats.totalSessions > 0) {
      stats.averageFallbacksPerSession = totalFallbacks / stats.totalSessions;
    }

    return stats;
  }

  /**
   * Get emotion detection statistics
   */
  getEmotionStatistics() {
    const emotionCounts = {};
    let totalConfidence = 0;
    let analyzedSessions = 0;

    for (const entry of this.fallbackLog) {
      if (entry.emotion) {
        const emotion = entry.emotion.detectedEmotion || "neutral";
        emotionCounts[emotion] = (emotionCounts[emotion] || 0) + 1;
        totalConfidence += entry.emotion.confidence || 0;
        analyzedSessions++;
      }
    }

    return {
      totalAnalyzed: analyzedSessions,
      emotionDistribution: emotionCounts,
      averageConfidence: analyzedSessions > 0 ? totalConfidence / analyzedSessions : 0,
      dominantEmotion: Object.entries(emotionCounts).sort(
        ([, a], [, b]) => b - a
      )[0]?.[0] || "neutral"
    };
  }

  /**
   * Clear fallback log
   */
  clearLog() {
    this.fallbackLog = [];
  }

  /**
   * Get recent fallback entries
   */
  getRecentFallbacks(count = 10) {
    return this.fallbackLog.slice(-count);
  }
}

function normalizeVoiceId(voiceId) {
  if (!voiceId) {
    return "alloy";
  }

  if (voiceId.startsWith("builtin:")) {
    return voiceId.replace("builtin:", "");
  }

  return voiceId;
}

module.exports = {
  TieredSpeechEngine,
};
