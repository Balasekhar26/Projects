const test = require("node:test");
const assert = require("node:assert/strict");
const { EventEmitter } = require("events");

const { RealtimeTranslator } = require("../../../src/pipeline/realtime-translator");

class FakeCapture extends EventEmitter {
  start() {
    this.emit("start", { device: "fake-device" });
  }

  stop() {
    this.emit("close", { code: 0 });
  }
}

class FakeStt extends EventEmitter {
  async transcribeChunk() {
    throw new Error("STT should not run for silence chunks");
  }
}

class FakeTranslator {
  async translate() {
    return { translatedText: "x", backend: "fake" };
  }
}

class FakeSpeaker {
  async speak() {}

  createSpeechJob(event) {
    let onStart = null;
    let onEnd = null;
    return {
      get onStart() {
        return onStart;
      },
      set onStart(handler) {
        onStart = handler;
      },
      get onEnd() {
        return onEnd;
      },
      set onEnd(handler) {
        onEnd = handler;
      },
      async play() {
        onStart?.();
        onEnd?.();
      },
      abort() {},
      async fadeOut() {},
      phraseId: event.phraseId,
      continuityScore: event.continuityScore,
      tempo: event.tempo,
      volumeBoost: event.volumeBoost,
      pitchCents: event.pitchCents,
      cadence: event.cadence,
      emotionalTilt: event.emotionalTilt,
      mode: event.mode,
    };
  }
}

test("realtime translator skips silence chunks before STT", async () => {
  const capture = new FakeCapture();
  const translator = new RealtimeTranslator({
    config: {
      tempDir: process.env.TEMP || "C:\\temp",
      sampleRate: 16000,
      channels: 1,
      bytesPerSample: 2,
      targetLanguage: "te",
      onlinePolicy: "offline-only",
      realtimeSilenceRmsThreshold: 0.008,
      realtimeSpeechRmsThreshold: 0.014,
      maxRealtimeLatencyMs: 1500,
    },
    capture,
    sttClient: new FakeStt(),
    translator: new FakeTranslator(),
    speaker: new FakeSpeaker(),
  });

  const latencies = [];
  translator.on("latency", (event) => latencies.push(event));

  await translator.start();
  capture.emit("chunk", {
    capturedAt: new Date().toISOString(),
    pcmBuffer: Buffer.alloc(3200),
    analysis: { rms: 0.001 },
    durationMs: 300,
    reason: "vad-silence",
  });
  await translator.processingQueue;
  await translator.stop();

  assert.equal(latencies.length, 1);
  assert.equal(latencies[0].skipped, true);
});

test("realtime translator front-loads confident partials and primes pre-speech presence", async () => {
  const capture = new FakeCapture();
  const stt = new (class extends EventEmitter {
    async transcribeChunk() {
      return {
        transcript: "hello there",
        detected_language: "en",
      };
    }
  })();
  const translationCalls = [];
  const fakeTranslator = {
    async translate(input) {
      translationCalls.push(input);
      return { translatedText: "namaste there", backend: "fake" };
    },
  };
  const translator = new RealtimeTranslator({
    config: {
      tempDir: process.env.TEMP || "C:\\temp",
      sampleRate: 16000,
      channels: 1,
      bytesPerSample: 2,
      targetLanguage: "hi",
      sourceLanguage: "auto",
      onlinePolicy: "offline-only",
      realtimeSpeechRmsThreshold: 0.014,
    },
    capture,
    sttClient: stt,
    translator: fakeTranslator,
    speaker: new FakeSpeaker(),
  });

  const presenceSignals = [];
  translator.playbackController.noteSpeechDetected = (payload) => {
    presenceSignals.push(payload);
  };

  const translations = [];
  translator.on("translation", (event) => translations.push(event));

  await translator.start();
  capture.emit("chunk", {
    capturedAt: new Date().toISOString(),
    pcmBuffer: Buffer.alloc(3200),
    analysis: { rms: 0.03, zeroCrossingRate: 0.08 },
    durationMs: 300,
    reason: "vad-speech",
  });
  await translator.processingQueue;
  await translator.stop();

  assert.equal(presenceSignals.length, 1);
  assert.equal(translationCalls.length, 1);
  assert.equal(translations.length, 1);
  assert.equal(translations[0].mode, "commit");
});

test("realtime translator emits chunk latency metrics when playback becomes audible", async () => {
  const capture = new FakeCapture();
  const stt = new (class extends EventEmitter {
    async transcribeChunk() {
      return {
        transcript: "metrics now",
        detected_language: "en",
      };
    }
  })();
  const translatorEngine = {
    async translate() {
      return { translatedText: "metrics now", backend: "fake" };
    },
  };
  const translator = new RealtimeTranslator({
    config: {
      tempDir: process.env.TEMP || "C:\\temp",
      sampleRate: 16000,
      channels: 1,
      bytesPerSample: 2,
      targetLanguage: "hi",
      sourceLanguage: "auto",
      onlinePolicy: "offline-only",
      realtimeSpeechRmsThreshold: 0.014,
    },
    capture,
    sttClient: stt,
    translator: translatorEngine,
    speaker: new FakeSpeaker(),
  });

  const metrics = [];
  translator.on("metric", (event) => metrics.push(event));

  await translator.start();
  capture.emit("chunk", {
    capturedAt: new Date().toISOString(),
    pcmBuffer: Buffer.alloc(3200),
    analysis: { rms: 0.03, zeroCrossingRate: 0.08 },
    durationMs: 300,
    reason: "vad-speech",
  });
  await translator.processingQueue;
  await translator.stop();

  const chunkMetric = metrics.find((event) => event.scope === "chunk");
  assert.equal(Boolean(chunkMetric), true);
  assert.equal(Number.isFinite(chunkMetric.speechStartToFirstAudioMs), true);
  assert.equal(Number.isFinite(chunkMetric.sttReadyMs), true);
  assert.equal(Number.isFinite(chunkMetric.ttsStartDelayMs), true);
});
