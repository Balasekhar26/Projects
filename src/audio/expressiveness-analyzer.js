/**
 * Voice Expressiveness Analyzer
 * 
 * Analyzes audio characteristics to detect emotion and speaking style,
 * then provides instructions to TTS engines to preserve these qualities.
 */

const { EventEmitter } = require("events");

class VoiceExprexivenessAnalyzer extends EventEmitter {
  constructor(config = {}) {
    super();
    this.config = config;
    this.emotionMap = this.initializeEmotionMap();
  }

  /**
   * Emotion classification model
   */
  initializeEmotionMap() {
    return {
      // Emotional states with characteristic audio features
      anger: {
        pitch: "high",
        speed: "fast",
        intensity: "high",
        pauseFrequency: "low",
        ttsInstructions: "speak with intensity and urgency, faster pace, higher pitch",
        energyLevel: 0.9
      },
      happiness: {
        pitch: "high-varied",
        speed: "moderate-fast",
        intensity: "moderate",
        pauseFrequency: "moderate",
        ttsInstructions: "speak with enthusiasm, uplifted tone, natural variations in pitch",
        energyLevel: 0.8
      },
      sadness: {
        pitch: "low",
        speed: "slow",
        intensity: "low",
        pauseFrequency: "high",
        ttsInstructions: "speak softly with melancholy tone, slower pace, lower pitch",
        energyLevel: 0.3
      },
      fear: {
        pitch: "high",
        speed: "fast",
        intensity: "high",
        pauseFrequency: "high",
        ttsInstructions: "speak with urgency and concern, nervous energy, higher pitch",
        energyLevel: 0.85
      },
      surprise: {
        pitch: "high",
        speed: "moderate",
        intensity: "moderate-high",
        pauseFrequency: "high",
        ttsInstructions: "speak with astonishment, brief pauses, higher pitch variations",
        energyLevel: 0.7
      },
      neutral: {
        pitch: "moderate",
        speed: "moderate",
        intensity: "moderate",
        pauseFrequency: "moderate",
        ttsInstructions: "speak in neutral, professional tone with natural pacing",
        energyLevel: 0.5
      }
    };
  }

  /**
   * Analyze audio characteristics from chunk metadata
   */
  analyzeExpressiveness(audioAnalysis = {}, transcript = "") {
    const analysis = {
      detectedEmotion: "neutral",
      confidence: 0,
      characteristics: {},
      ttsInstructions: "",
      recommendations: []
    };

    if (!audioAnalysis || Object.keys(audioAnalysis).length === 0) {
      // Use transcript-based heuristics if audio analysis unavailable
      return this.analyzeFromTranscript(transcript);
    }

    try {
      // Analyze audio features
      const emotionScores = this.classifyEmotion(audioAnalysis);
      const topEmotion = Object.entries(emotionScores)
        .sort(([, a], [, b]) => b - a)[0];

      if (topEmotion) {
        analysis.detectedEmotion = topEmotion[0];
        analysis.confidence = topEmotion[1];
      }

      // Get emotion characteristics
      const emotionData = this.emotionMap[analysis.detectedEmotion] || this.emotionMap.neutral;
      analysis.characteristics = {
        pitch: emotionData.pitch,
        speed: emotionData.speed,
        intensity: emotionData.intensity,
        pauseFrequency: emotionData.pauseFrequency
      };

      analysis.ttsInstructions = emotionData.ttsInstructions;

      // Add recommendations
      analysis.recommendations = this.generateRecommendations(audioAnalysis, analysis.detectedEmotion);

      this.emit("analysis", analysis);
      return analysis;
    } catch (error) {
      this.emit("error", error);
      return analysis;
    }
  }

  /**
   * Classify emotion from audio features
   */
  classifyEmotion(audioAnalysis = {}) {
    const scores = {
      anger: 0,
      happiness: 0,
      sadness: 0,
      fear: 0,
      surprise: 0,
      neutral: 0.5 // Default baseline
    };

    // Extract features
    const pitchMean = audioAnalysis.pitchMean || 150;
    const pitchVariance = audioAnalysis.pitchVariance || 50;
    const energy = audioAnalysis.energy || 0.5;
    const energyVariance = audioAnalysis.energyVariance || 0.1;
    const speechRate = audioAnalysis.speechRate || 0.5;
    const pauseRatio = audioAnalysis.pauseRatio || 0.2;

    // Emotion scoring logic (simplified)
    
    // High pitch + high energy + fast = anger
    if (pitchMean > 180 && energy > 0.7 && speechRate > 0.6) {
      scores.anger = 0.8;
    }

    // High pitch + high pitch variance + moderate energy = happiness
    if (pitchMean > 160 && pitchVariance > 50 && energy > 0.5) {
      scores.happiness = 0.75;
    }

    // Low pitch + low energy + slow = sadness
    if (pitchMean < 120 && energy < 0.4 && speechRate < 0.4) {
      scores.sadness = 0.7;
    }

    // High pitch + high energy + high pauses = fear
    if (pitchMean > 180 && energy > 0.6 && pauseRatio > 0.3) {
      scores.fear = 0.7;
    }

    // High pitch variations + sudden energy changes = surprise
    if (pitchVariance > 80 && energyVariance > 0.2) {
      scores.surprise = 0.6;
    }

    // Moderate values = neutral
    if (
      pitchMean > 130 &&
      pitchMean < 170 &&
      energy > 0.4 &&
      energy < 0.6 &&
      speechRate > 0.4 &&
      speechRate < 0.6
    ) {
      scores.neutral = 0.9;
    }

    // Normalize scores
    const total = Object.values(scores).reduce((a, b) => a + b, 0);
    if (total > 0) {
      Object.keys(scores).forEach((key) => {
        scores[key] = scores[key] / total;
      });
    }

    return scores;
  }

  /**
   * Fallback: Analyze emotion from transcript text
   */
  analyzeFromTranscript(transcript = "") {
    const analysis = {
      detectedEmotion: "neutral",
      confidence: 0.3,
      characteristics: this.emotionMap.neutral,
      ttsInstructions: this.emotionMap.neutral.ttsInstructions,
      recommendations: ["Use audio analysis for better emotion detection"]
    };

    if (!transcript) {
      return analysis;
    }

    // Simple keyword-based detection
    const lowerTranscript = transcript.toLowerCase();

    const emotionKeywords = {
      anger: ["!!", "!!!", "angry", "furious", "hate", "disgusting"],
      happiness: ["!!!", ":)", "love", "happy", "wonderful", "excellent"],
      sadness: [":(", "sad", "crying", "depressed", "miserable"],
      fear: ["?!", "scared", "terrified", "afraid", "panic"]
    };

    for (const [emotion, keywords] of Object.entries(emotionKeywords)) {
      const matchCount = keywords.filter((kw) => lowerTranscript.includes(kw)).length;
      if (matchCount > 0) {
        analysis.detectedEmotion = emotion;
        analysis.confidence = Math.min(0.7, matchCount * 0.2);
        break;
      }
    }

    const emotionData = this.emotionMap[analysis.detectedEmotion] || this.emotionMap.neutral;
    analysis.characteristics = {
      pitch: emotionData.pitch,
      speed: emotionData.speed,
      intensity: emotionData.intensity
    };
    analysis.ttsInstructions = emotionData.ttsInstructions;

    return analysis;
  }

  /**
   * Generate TTS recommendations
   */
  generateRecommendations(audioAnalysis = {}, detectedEmotion = "neutral") {
    const recommendations = [];

    const emotionData = this.emotionMap[detectedEmotion];
    const energyLevel = emotionData?.energyLevel || 0.5;

    // Recommend voice settings based on emotion
    if (energyLevel > 0.8) {
      recommendations.push("Enable high energy TTS voice");
      recommendations.push("Use faster speech rate");
    } else if (energyLevel < 0.4) {
      recommendations.push("Use softer TTS voice");
      recommendations.push("Reduce speech rate");
    }

    if (audioAnalysis.pitchVariance > 60) {
      recommendations.push("Preserve natural pitch variations in translation");
    }

    if (audioAnalysis.pauseRatio > 0.25) {
      recommendations.push("Maintain natural pausing in translated speech");
    }

    return recommendations;
  }

  /**
   * Get emotion statistics from multiple samples
   */
  getEmotionStatistics(samples = []) {
    const stats = {
      dominantEmotion: "neutral",
      emotionDistribution: {},
      averageConfidence: 0,
      emotionTransitions: []
    };

    if (samples.length === 0) {
      return stats;
    }

    const emotionCounts = {};
    let totalConfidence = 0;

    samples.forEach((sample) => {
      const emotion = sample.detectedEmotion || "neutral";
      emotionCounts[emotion] = (emotionCounts[emotion] || 0) + 1;
      totalConfidence += sample.confidence || 0;
    });

    stats.emotionDistribution = emotionCounts;
    stats.dominantEmotion = Object.entries(emotionCounts).sort(
      ([, a], [, b]) => b - a
    )[0]?.[0] || "neutral";
    stats.averageConfidence = samples.length > 0 ? totalConfidence / samples.length : 0;

    // Detect emotion transitions
    for (let i = 1; i < samples.length; i++) {
      if (samples[i].detectedEmotion !== samples[i - 1].detectedEmotion) {
        stats.emotionTransitions.push({
          from: samples[i - 1].detectedEmotion,
          to: samples[i].detectedEmotion,
          index: i
        });
      }
    }

    return stats;
  }
}

module.exports = {
  VoiceExprexivenessAnalyzer
};
