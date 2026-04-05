const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs/promises");
const os = require("os");
const path = require("path");

const { prepareRuntimeForSession } = require("../src/installer/provisioning");

test("runtime preparation cleans transient audio and skips offline packs for online-only sessions", async () => {
  const rootDir = await fs.mkdtemp(path.join(os.tmpdir(), "ult-runtime-"));
  const tempDir = path.join(rootDir, "temp");
  const notesPath = path.join(tempDir, "notes.txt");
  const wavPath = path.join(tempDir, "chunk-1.wav");

  await fs.mkdir(tempDir, { recursive: true });
  await fs.writeFile(notesPath, "keep", "utf8");
  await fs.writeFile(wavPath, "audio", "utf8");

  const report = await prepareRuntimeForSession({
    config: {
      dataDir: path.join(rootDir, "data"),
      tempDir,
      voiceProfilesDir: path.join(rootDir, "voice-profiles"),
      argosPackagesDir: path.join(rootDir, "argos"),
    },
    sourceLanguage: "en",
    targetLanguage: "te",
    onlinePolicy: "online-only",
  });

  const removed = await fs
    .access(wavPath)
    .then(() => false)
    .catch(() => true);
  const preserved = await fs
    .readFile(notesPath, "utf8")
    .then((value) => value)
    .catch(() => "");

  assert.equal(removed, true);
  assert.equal(preserved, "keep");
  assert.equal(report.actions.some((action) => action.step === "offline-pack"), true);
  assert.equal(
    report.actions.find((action) => action.step === "offline-pack")?.status,
    "skipped"
  );
});
