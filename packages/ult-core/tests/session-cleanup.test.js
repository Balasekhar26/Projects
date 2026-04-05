const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs/promises");
const path = require("path");
const os = require("os");

const { UniversalLiveSession } = require("../src/session/live-session");

class FakeSttEngine {
  async transcribeChunk() {
    return {
      transcript: "hello world",
      translated_text: "",
      detected_language: "en",
    };
  }

  stop() {}
}

class FakeTranslationEngine {
  async translate() {
    return {
      translatedText: "namaste world",
      backend: "fake",
    };
  }

  stop() {}
}

class FakeSpeechEngine {
  async speak() {}
}

test("live sessions remove temp files when stopped", async () => {
  const tempDir = await fs.mkdtemp(path.join(os.tmpdir(), "ult-session-"));

  const session = new UniversalLiveSession(
    {
      sourceLanguage: "en",
      targetLanguage: "te",
      voiceProfileId: "builtin:alloy",
    },
    {
      config: {
        tempDir,
        voiceProfilesDir: tempDir,
      },
      sttEngine: new FakeSttEngine(),
      translationEngine: new FakeTranslationEngine(),
      speechEngine: new FakeSpeechEngine(),
    }
  );

  await session.start();
  await session.enqueueChunk({
    audioBuffer: Buffer.from("RIFFfake"),
    fileExtension: "wav",
    analysis: { rms: 0.1, peak: 0.2, zeroCrossingRate: 0.1 },
  });
  await session.stop();

  const sessionPath = path.join(tempDir, "sessions", session.id);
  const existsAfterStop = await fs
    .access(sessionPath)
    .then(() => true)
    .catch(() => false);

  assert.equal(existsAfterStop, false);
});
