const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs/promises");
const os = require("os");
const path = require("path");

const { UniversalLiveSession } = require("../src/session/live-session");

class FakeFailingSttEngine {
  async transcribeChunk() {
    return {
      transcript: "source speech",
      translated_text: "",
      detected_language: "en",
      backend: "fake-stt",
    };
  }
  stop() {}
}

class FakeEmptyTranslationEngine {
  async translate() {
    return { translatedText: "", backend: "fake-translation" };
  }
  stop() {}
}

class FakeSpeechEngine {
  async speak() {}
  stop() {}
}

test("live sessions fail closed when translation produces no output", async () => {
  const tempDir = await fs.mkdtemp(path.join(os.tmpdir(), "ult-fail-closed-"));

  const session = new UniversalLiveSession(
    {
      sourceLanguage: "en",
      targetLanguage: "te",
      sessionKind: "browser_debug",
    },
    {
      config: {
        tempDir,
        voiceProfilesDir: tempDir,
      },
      sttEngine: new FakeFailingSttEngine(),
      translationEngine: new FakeEmptyTranslationEngine(),
      speechEngine: new FakeSpeechEngine(),
    }
  );

  await session.start();
  await session.enqueueChunk({
    audioBuffer: Buffer.from("RIFFfake"),
    fileExtension: "wav",
    analysis: null,
  });
  await session.processingQueue.catch(() => {});

  assert.equal(session.getSnapshot().health.failClosed, true);
  assert.match(session.getSnapshot().health.failClosedReason, /Translation produced no output/i);

  await session.stop();
});
