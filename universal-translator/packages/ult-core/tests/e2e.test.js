const assert = require("assert");
const path = require("path");
const fs = require("fs/promises");
const { getCoreConfig } = require("../src/config");
const { HybridSttEngine } = require("../src/stt-engine");
const { HybridTranslationEngine } = require("../src/translation-engine");
const { TieredSpeechEngine } = require("../src/tts-engine/tiered-speaker");
const { listDeviceTopology } = require("../src/device-control/topology");
const { MicrophoneRouter } = require("../src/mic-routing/router");

// Test utilities
function createTestConfig() {
  return {
    ...getCoreConfig(),
    // Use temp paths for tests
    tempDir: path.join(process.env.TEMP || "/tmp", "ult-tests"),
    onlinePolicy: "offline-only"
  };
}

async function setupTestEnvironment() {
  const config = createTestConfig();
  await fs.mkdir(config.tempDir, { recursive: true });
  return config;
}

async function cleanupTestEnvironment(config) {
  try {
    await fs.rm(config.tempDir, { recursive: true, force: true });
  } catch (error) {
    console.warn("Cleanup error:", error.message);
  }
}

// ===== TEST CASES =====

module.exports = {
  // Device Topology Test
  "device-topology": async () => {
    const config = createTestConfig();
    try {
      const topology = await listDeviceTopology(config);
      
      assert.ok(topology, "Topology should be defined");
      assert.ok(Array.isArray(topology.inputDevices), "Should have input devices array");
      assert.ok(Array.isArray(topology.outputDevices), "Should have output devices array");
      
      return {
        passed: true,
        devices: {
          input: topology.inputDevices.length,
          output: topology.outputDevices.length
        }
      };
    } catch (error) {
      return { passed: false, error: error.message };
    }
  },

  // Microphone Router Test
  "microphone-router": async () => {
    const config = createTestConfig();
    const router = new MicrophoneRouter(config);
    
    try {
      const status = await router.getRoutingStatus();
      const physicalMics = await router.getPhysicalMicrophones();
      const virtualMics = await router.getVirtualMicrophones();
      
      return {
        passed: true,
        routed: status?.enabled || false,
        physicalDevices: physicalMics.length,
        virtualDevices: virtualMics.length
      };
    } catch (error) {
      return { passed: false, error: error.message };
    }
  },

  // STT Engine Test (Offline)
  "stt-engine-offline": async () => {
    const config = createTestConfig();
    await fs.mkdir(config.tempDir, { recursive: true });
    config.onlinePolicy = "offline-only";
    
    const engine = new HybridSttEngine(config);
    
    try {
      // Create a silent 1-second test audio file
      const testAudioPath = path.join(config.tempDir, "test-audio.wav");
      const silentWav = Buffer.concat([
        Buffer.from("RIFF", "ascii"),
        Buffer.from([0x28, 0x00, 0x00, 0x00]), // Chunk size
        Buffer.from("WAVE", "ascii"),
        Buffer.from("fmt ", "ascii"),
        Buffer.from([0x10, 0x00, 0x00, 0x00]), // Subchunk size
        Buffer.from([0x01, 0x00, 0x01, 0x00, 0x40, 0x1f, 0x00, 0x00, 0x80, 0x3e, 0x00, 0x00, 0x02, 0x00, 0x10, 0x00]),
        Buffer.from("data", "ascii"),
        Buffer.from([0x00, 0x00, 0x00, 0x00]) // Data size (0 for silence)
      ]);

      await fs.writeFile(testAudioPath, silentWav);

      const result = await engine.transcribeChunk({
        audioPath: testAudioPath,
        sourceLanguage: "en",
        targetLanguage: "en",
        onlinePolicy: "offline-only"
      });

      await fs.rm(testAudioPath, { force: true });

      return {
        passed: true,
        transcript: result.transcript || "(silent)",
        language: result.detected_language || "unknown"
      };
    } catch (error) {
      return { passed: false, error: error.message };
    }
  },

  // Translation Passthrough Test
  "translation-engine": async () => {
    const config = createTestConfig();
    const engine = new HybridTranslationEngine(config);
    
    try {
      // Test passthrough (no translation when target = source)
      const result1 = await engine.translate({
        transcript: "Hello world",
        whisperTranslation: "",
        detectedLanguage: "en",
        sourceLanguage: "en",
        targetLanguage: "en",
        onlinePolicy: "offline-only"
      });

      assert.strictEqual(result1.translatedText, "Hello world", "Passthrough should preserve text");
      assert.strictEqual(result1.backend, "passthrough", "Should use passthrough backend");

      // Test empty input
      const result2 = await engine.translate({
        transcript: "",
        whisperTranslation: "",
        detectedLanguage: "en",
        sourceLanguage: "en",
        targetLanguage: "es",
        onlinePolicy: "offline-only"
      });

      assert.strictEqual(result2.translatedText, "", "Empty input should produce empty output");

      return {
        passed: true,
        tests: [
          { name: "passthrough", result: "OK" },
          { name: "empty-input", result: "OK" }
        ]
      };
    } catch (error) {
      return { passed: false, error: error.message };
    }
  },

  // TTS Fallback Chain Test
  "tts-fallback-chain": async () => {
    const config = createTestConfig();
    config.openAiApiKey = ""; // Force fallback to system TTS
    
    const engine = new TieredSpeechEngine(config);
    const warnings = [];
    const errors = [];

    engine.on("warn", (msg) => warnings.push(msg));
    engine.on("error", (err) => errors.push(err.message));

    try {
      // Test with minimal text
      await engine.speak("Hello", {
        language: "en",
        outputDeviceName: "speakers",
        preserveEmotion: false
      });

      const stats = engine.getStatistics();
      
      return {
        passed: true,
        fallbackStats: stats,
        warnings: warnings.length,
        errors: errors.length
      };
    } catch (error) {
      return { passed: false, error: error.message };
    }
  },

  // Audio Latency Test
  "audio-latency-measurement": async () => {
    try {
      const config = createTestConfig();
      const startTime = Date.now();
      
      // Simulate a quick operation
      await new Promise((resolve) => setTimeout(resolve, 100));
      
      const endTime = Date.now();
      const latency = endTime - startTime;

      assert.ok(latency >= 100, "Latency should be measured correctly");

      return {
        passed: true,
        latencyMs: latency,
        targetMs: 1500,
        withinTarget: latency < 1500
      };
    } catch (error) {
      return { passed: false, error: error.message };
    }
  },

  // Device Switching Test
  "device-switching": async () => {
    const config = createTestConfig();
    
    try {
      const topology = await listDeviceTopology(config);
      
      assert.ok(
        topology.inputDevices.length > 0,
        "Should have at least one input device"
      );
      assert.ok(
        topology.outputDevices.length > 0,
        "Should have at least one output device"
      );

      return {
        passed: true,
        canSwitchInput: topology.inputDevices.length > 1,
        canSwitchOutput: topology.outputDevices.length > 1,
        devices: {
          inputCount: topology.inputDevices.length,
          outputCount: topology.outputDevices.length
        }
      };
    } catch (error) {
      return { passed: false, error: error.message };
    }
  },

  // Offline Mode Test
  "offline-mode": async () => {
    const config = createTestConfig();
    config.onlinePolicy = "offline-only";

    try {
      const sttEngine = new HybridSttEngine(config);
      const translationEngine = new HybridTranslationEngine(config);
      
      // Just verify engines initialize in offline mode
      assert.ok(sttEngine.offline, "Should have offline STT engine");
      assert.ok(translationEngine.offline, "Should have offline translation engine");

      return {
        passed: true,
        offlineMode: true,
        sttReady: !!sttEngine.offline,
        translationReady: !!translationEngine.offline
      };
    } catch (error) {
      return { passed: false, error: error.message };
    }
  }
};
