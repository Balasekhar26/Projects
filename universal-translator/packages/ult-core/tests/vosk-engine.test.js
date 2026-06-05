const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs/promises");
const os = require("os");
const path = require("path");

const { VoskSttEngine } = require("../src/stt-engine/vosk");

test("Vosk engine fails fast when worker script is missing", async () => {
  const rootDir = await fs.mkdtemp(path.join(os.tmpdir(), "ult-vosk-"));
  const modelDir = path.join(rootDir, "model");
  await fs.mkdir(modelDir);

  const engine = new VoskSttEngine({
    scriptsDir: rootDir,
    voskWorkerPath: path.join(rootDir, "missing-worker.py"),
    voskModelPath: modelDir,
  });

  await assert.rejects(
    () => engine.transcribeChunk({ audioPath: path.join(rootDir, "sample.wav") }),
    /Vosk worker not found/
  );
});

test("Vosk engine fails fast when model path is missing", async () => {
  const rootDir = await fs.mkdtemp(path.join(os.tmpdir(), "ult-vosk-"));
  const workerPath = path.join(rootDir, "vosk_stream_worker.py");
  await fs.writeFile(workerPath, "print('ready')\n", "utf8");

  const engine = new VoskSttEngine({
    scriptsDir: rootDir,
    voskWorkerPath: workerPath,
    voskModelPath: path.join(rootDir, "missing-model"),
  });

  await assert.rejects(
    () => engine.transcribeChunk({ audioPath: path.join(rootDir, "sample.wav") }),
    /Vosk model path not found/
  );
});
