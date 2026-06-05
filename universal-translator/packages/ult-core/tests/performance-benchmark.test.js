const assert = require("assert");
const path = require("path");
const fs = require("fs/promises");
const { getCoreConfig } = require("../src/config");
const { HybridSttEngine } = require("../src/stt-engine");
const { HybridTranslationEngine } = require("../src/translation-engine");
const { TieredSpeechEngine } = require("../src/tts-engine/tiered-speaker");

/**
 * Performance Benchmark Tests
 * Measures latency, accuracy, and system performance
 */

function createBenchmarkConfig() {
  return {
    ...getCoreConfig(),
    tempDir: path.join(process.env.TEMP || "/tmp", "ult-benchmarks"),
    onlinePolicy: "auto" // Use best available for benchmarks
  };
}

async function createTestAudioFile(config, content = "Hello world", durationMs = 2000) {
  // Create a simple test audio file (placeholder - in real implementation,
  // this would generate actual speech audio)
  const testAudioPath = path.join(config.tempDir, `test-${Date.now()}.wav`);

  // For now, create a minimal WAV header (this is just for testing file operations)
  const wavHeader = Buffer.concat([
    Buffer.from("RIFF", "ascii"),
    Buffer.from([0x24, 0x08, 0x00, 0x00]), // Chunk size
    Buffer.from("WAVE", "ascii"),
    Buffer.from("fmt ", "ascii"),
    Buffer.from([0x10, 0x00, 0x00, 0x00]), // Subchunk size
    Buffer.from([0x01, 0x00, 0x01, 0x00, 0x40, 0x1f, 0x00, 0x00, 0x80, 0x3e, 0x00, 0x00, 0x02, 0x00, 0x10, 0x00]),
    Buffer.from("data", "ascii"),
    Buffer.from([0x00, 0x08, 0x00, 0x00]) // Data size
  ]);

  await fs.writeFile(testAudioPath, wavHeader);
  return testAudioPath;
}

module.exports = {
  // Latency Benchmark
  "latency-benchmark": async () => {
    const config = createBenchmarkConfig();
    await fs.mkdir(config.tempDir, { recursive: true });

    try {
      const sttEngine = new HybridSttEngine(config);
      const translationEngine = new HybridTranslationEngine(config);
      const ttsEngine = new TieredSpeechEngine(config);

      const samples = [];
      const iterations = 5; // Run multiple times for averaging

      for (let i = 0; i < iterations; i++) {
        const startTime = Date.now();

        // Create test audio
        const audioPath = await createTestAudioFile(config, "Hello world", 1000);

        // STT Phase
        const sttStart = Date.now();
        const sttResult = await sttEngine.transcribeChunk({
          audioPath,
          sourceLanguage: "en",
          targetLanguage: "es",
          onlinePolicy: config.onlinePolicy
        });
        const sttTime = Date.now() - sttStart;

        // Translation Phase
        const transStart = Date.now();
        const transResult = await translationEngine.translate({
          transcript: sttResult.transcript || "Hello world",
          whisperTranslation: sttResult.translated_text || "",
          detectedLanguage: sttResult.detected_language || "en",
          sourceLanguage: "en",
          targetLanguage: "es",
          onlinePolicy: config.onlinePolicy
        });
        const transTime = Date.now() - transStart;

        // TTS Phase (mock - don't actually speak)
        const ttsStart = Date.now();
        // Simulate TTS time (actual TTS would be measured)
        await new Promise(resolve => setTimeout(resolve, 100));
        const ttsTime = Date.now() - ttsStart;

        const totalTime = Date.now() - startTime;

        samples.push({
          iteration: i + 1,
          total: totalTime,
          stt: sttTime,
          translation: transTime,
          tts: ttsTime
        });

        // Cleanup
        await fs.rm(audioPath, { force: true });
      }

      // Calculate statistics
      const avgTotal = samples.reduce((sum, s) => sum + s.total, 0) / samples.length;
      const avgStt = samples.reduce((sum, s) => sum + s.stt, 0) / samples.length;
      const avgTrans = samples.reduce((sum, s) => sum + s.translation, 0) / samples.length;
      const avgTts = samples.reduce((sum, s) => sum + s.tts, 0) / samples.length;

      const targetLatency = 1500; // 1.5 seconds
      const withinTarget = avgTotal < targetLatency;

      return {
        passed: withinTarget,
        metrics: {
          averageLatency: Math.round(avgTotal),
          targetLatency,
          withinTarget,
          breakdown: {
            stt: Math.round(avgStt),
            translation: Math.round(avgTrans),
            tts: Math.round(avgTts)
          },
          samples: samples.length
        }
      };
    } catch (error) {
      return { passed: false, error: error.message };
    } finally {
      // Cleanup temp directory
      try {
        await fs.rm(config.tempDir, { recursive: true, force: true });
      } catch {}
    }
  },

  // Accuracy Benchmark
  "accuracy-benchmark": async () => {
    const config = createBenchmarkConfig();
    await fs.mkdir(config.tempDir, { recursive: true });

    try {
      const translationEngine = new HybridTranslationEngine(config);

      // Test cases with known translations
      const testCases = [
        {
          input: "Hello world",
          expected: "Hola mundo",
          source: "en",
          target: "es"
        },
        {
          input: "Good morning",
          expected: "Buenos días",
          source: "en",
          target: "es"
        },
        {
          input: "Thank you",
          expected: "Gracias",
          source: "en",
          target: "es"
        }
      ];

      const results = [];

      for (const testCase of testCases) {
        try {
          const result = await translationEngine.translate({
            transcript: testCase.input,
            whisperTranslation: "",
            detectedLanguage: testCase.source,
            sourceLanguage: testCase.source,
            targetLanguage: testCase.target,
            onlinePolicy: config.onlinePolicy
          });

          // Simple accuracy check (contains expected words)
          const translated = result.translatedText.toLowerCase();
          const expected = testCase.expected.toLowerCase();

          // Check if key words are present (basic accuracy metric)
          const accuracy = expected.split(' ').every(word =>
            translated.includes(word) || word.length < 3 // Skip short words
          ) ? 1 : 0;

          results.push({
            input: testCase.input,
            expected: testCase.expected,
            actual: result.translatedText,
            accuracy,
            backend: result.backend
          });
        } catch (error) {
          results.push({
            input: testCase.input,
            expected: testCase.expected,
            actual: null,
            accuracy: 0,
            error: error.message
          });
        }
      }

      const avgAccuracy = results.reduce((sum, r) => sum + r.accuracy, 0) / results.length;
      const targetAccuracy = 0.85; // 85%
      const withinTarget = avgAccuracy >= targetAccuracy;

      return {
        passed: withinTarget,
        metrics: {
          averageAccuracy: Math.round(avgAccuracy * 100) / 100,
          targetAccuracy,
          withinTarget,
          testCases: results.length,
          results
        }
      };
    } catch (error) {
      return { passed: false, error: error.message };
    } finally {
      try {
        await fs.rm(config.tempDir, { recursive: true, force: true });
      } catch {}
    }
  },

  // Memory Usage Test
  "memory-usage-test": async () => {
    const config = createBenchmarkConfig();

    try {
      const initialMemory = process.memoryUsage();

      // Load engines
      const sttEngine = new HybridSttEngine(config);
      const translationEngine = new HybridTranslationEngine(config);
      const ttsEngine = new TieredSpeechEngine(config);

      // Force garbage collection if available
      if (global.gc) {
        global.gc();
      }

      const loadedMemory = process.memoryUsage();

      const memoryIncrease = {
        rss: loadedMemory.rss - initialMemory.rss,
        heapUsed: loadedMemory.heapUsed - initialMemory.heapUsed,
        heapTotal: loadedMemory.heapTotal - initialMemory.heapTotal
      };

      // Convert to MB
      const memoryMB = {
        rss: Math.round(memoryIncrease.rss / 1024 / 1024),
        heapUsed: Math.round(memoryIncrease.heapUsed / 1024 / 1024),
        heapTotal: Math.round(memoryIncrease.heapTotal / 1024 / 1024)
      };

      // Reasonable memory limits (adjust based on system)
      const maxMemoryMB = 500; // 500MB max increase
      const withinLimits = memoryMB.heapUsed < maxMemoryMB;

      return {
        passed: withinLimits,
        metrics: {
          memoryIncrease: memoryMB,
          maxAllowed: maxMemoryMB,
          withinLimits
        }
      };
    } catch (error) {
      return { passed: false, error: error.message };
    }
  },

  // Continuous Operation Test
  "continuous-operation-test": async () => {
    const config = createBenchmarkConfig();
    await fs.mkdir(config.tempDir, { recursive: true });

    try {
      const translationEngine = new HybridTranslationEngine(config);
      const testDuration = 30000; // 30 seconds
      const startTime = Date.now();
      let operations = 0;
      let errors = 0;

      while (Date.now() - startTime < testDuration) {
        try {
          await translationEngine.translate({
            transcript: `Test message ${operations + 1}`,
            whisperTranslation: "",
            detectedLanguage: "en",
            sourceLanguage: "en",
            targetLanguage: "es",
            onlinePolicy: config.onlinePolicy
          });
          operations++;
        } catch (error) {
          errors++;
        }

        // Small delay to prevent overwhelming
        await new Promise(resolve => setTimeout(resolve, 100));
      }

      const uptime = Date.now() - startTime;
      const successRate = operations / (operations + errors);
      const targetUptime = testDuration * 0.95; // 95% uptime
      const withinTarget = uptime >= targetUptime && successRate >= 0.9;

      return {
        passed: withinTarget,
        metrics: {
          duration: uptime,
          operations,
          errors,
          successRate: Math.round(successRate * 100) / 100,
          opsPerSecond: Math.round(operations / (uptime / 1000)),
          targetUptime: targetUptime,
          withinTarget
        }
      };
    } catch (error) {
      return { passed: false, error: error.message };
    } finally {
      try {
        await fs.rm(config.tempDir, { recursive: true, force: true });
      } catch {}
    }
  }
};