const test = require("node:test");
const assert = require("node:assert/strict");

const {
  LiveTranscript,
  RealtimeTranslator,
  computeDelta,
  findTranscriptOverlap,
} = require("../../../src/pipeline/realtime-translator");

test("findTranscriptOverlap matches overlapping tail/head word sequences", () => {
  assert.equal(findTranscriptOverlap("how are you", "are you doing"), "are you");
  assert.equal(findTranscriptOverlap("hello there", "general kenobi"), "");
});

test("LiveTranscript emits only the new delta from overlapping streaming transcripts", () => {
  const tracker = new LiveTranscript();

  const first = tracker.update("how are you");
  const second = tracker.update("are you doing today");

  assert.equal(first.deltaText, "how are you");
  assert.equal(first.isStable, true);
  assert.equal(second.deltaText, "doing today");
  assert.equal(second.isStable, true);
});

test("LiveTranscript suppresses duplicate spoken deltas", () => {
  const tracker = new LiveTranscript();

  assert.equal(tracker.shouldSpeak("ధన్యవాదాలు"), true);
  assert.equal(tracker.shouldSpeak("ధన్యవాదాలు"), false);
  assert.equal(tracker.shouldSpeak("చాలా మంచిది"), true);
});

test("computeDelta keeps only the translated extension when the phrase grows", () => {
  assert.equal(computeDelta("వెళ్తా", "వెళ్తాను"), "ను");
  assert.equal(computeDelta("hello there", "hello there friend"), "friend");
});

test("RealtimeTranslator buffers tiny translated fragments until a phrase boundary forms", () => {
  const translator = new RealtimeTranslator({
    config: { tempDir: "C:\\temp\\ult-test", sampleRate: 16000, channels: 1, bytesPerSample: 2, targetLanguage: "te" },
    capture: { on() {}, once() {}, start() {}, stop() {} },
    sttClient: { on() {} },
    translator: {},
    speaker: {},
  });

  assert.deepEqual(
    translator.bufferTranslatedPhrase("మీరు", { isStable: false, tokenCount: 1, nowMs: 0 }),
    { readyText: "మీరు", mode: "tentative" }
  );
  assert.deepEqual(
    translator.bufferTranslatedPhrase("బాగున్నారా", { isStable: false, tokenCount: 2, nowMs: 250 }),
    { readyText: "బాగున్నారా", mode: "tentative" }
  );
  assert.deepEqual(
    translator.bufferTranslatedPhrase("ఇప్పుడు.", { isStable: true, tokenCount: 1, nowMs: 700 }),
    { readyText: "ఇప్పుడు.", mode: "commit" }
  );
});

test("RealtimeTranslator forces a commit after the max-wait fuse", () => {
  const translator = new RealtimeTranslator({
    config: { tempDir: "C:\\temp\\ult-test", sampleRate: 16000, channels: 1, bytesPerSample: 2, targetLanguage: "te" },
    capture: { on() {}, once() {}, start() {}, stop() {} },
    sttClient: { on() {} },
    translator: {},
    speaker: {},
  });
  translator.lastSpeechAt = 1;

  assert.deepEqual(
    translator.bufferTranslatedPhrase("ఇది", { isStable: false, tokenCount: 1, nowMs: 100 }),
    { readyText: "", mode: "hold" }
  );
  assert.deepEqual(
    translator.bufferTranslatedPhrase("కొంత", { isStable: false, tokenCount: 1, nowMs: 700 }),
    { readyText: "ఇది కొంత", mode: "commit" }
  );
});

test("RealtimeTranslator keeps phrase metadata on commit events", () => {
  const translator = new RealtimeTranslator({
    config: { tempDir: "C:\\temp\\ult-test", sampleRate: 16000, channels: 1, bytesPerSample: 2, targetLanguage: "te" },
    capture: { on() {}, once() {}, start() {}, stop() {} },
    sttClient: { on() {} },
    translator: {},
    speaker: {},
  });

  const tentative = translator.buildPlaybackEvent({
    chunkNumber: 1,
    mode: "tentative",
    text: "నేను",
    fullText: "నేను",
  });
  const commit = translator.buildPlaybackEvent({
    chunkNumber: 2,
    mode: "commit",
    text: "నేను వెళ్తాను",
    fullText: "నేను వెళ్తాను",
  });

  assert.equal(tentative.phraseId, 1);
  assert.equal(tentative.revision, 1);
  assert.equal(commit.phraseId, 1);
  assert.equal(commit.revision, "final");
});
