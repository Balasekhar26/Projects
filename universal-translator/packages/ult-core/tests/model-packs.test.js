const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs/promises");
const os = require("os");
const path = require("path");

const {
  buildLanguagePairPackId,
  hasArgosLanguagePair,
  listModelPacks,
} = require("../src/catalog/model-packs");

test("language pair model pack ids are stable", () => {
  assert.equal(buildLanguagePairPackId("en", "te"), "pair:en-te");
});

test("model pack listing includes pair-specific offline pack", () => {
  const packs = listModelPacks({
    rootDir: path.resolve(__dirname, "../../.."),
    sourceLanguage: "en",
    targetLanguage: "te",
  });

  assert.ok(packs.some((pack) => pack.id === "pair:en-te"));
});

test("model pack listing detects installed Argos language pairs from package metadata", async () => {
  const rootDir = await fs.mkdtemp(path.join(os.tmpdir(), "ult-model-packs-"));
  const argosPackageDir = path.join(rootDir, "models", "argos", "translate-en_te");

  await fs.mkdir(argosPackageDir, { recursive: true });
  await fs.writeFile(
    path.join(argosPackageDir, "metadata.json"),
    JSON.stringify({
      from_code: "en",
      to_code: "te",
    }),
    "utf8"
  );

  assert.equal(hasArgosLanguagePair(path.join(rootDir, "models", "argos"), "en", "te"), true);

  const packs = listModelPacks({
    rootDir,
    sourceLanguage: "en",
    targetLanguage: "te",
  });

  const pairPack = packs.find((pack) => pack.id === "pair:en-te");
  assert.equal(pairPack?.installState, "installed");
});
