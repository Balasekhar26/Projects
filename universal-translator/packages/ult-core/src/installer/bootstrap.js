const { getCoreConfig } = require("../config");
const { detectHardwareProfile, listModelPacks } = require("../catalog/model-packs");
const { listDeviceTopology } = require("../device-control/topology");
const { ensureRuntimeLayout, pruneTempArtifacts } = require("./runtime-layout");

async function runBootstrapInspection(config = getCoreConfig()) {
  await ensureRuntimeLayout(config);
  const tempCleanup = await pruneTempArtifacts(config);
  const hardware = detectHardwareProfile();
  const topology = await listDeviceTopology(config).catch((error) => ({
    platform: process.platform,
    inputDevices: [],
    outputDevices: [],
    systemVoices: [],
    routeProfiles: [],
    diagnostics: [error.message],
  }));

  const modelPacks = listModelPacks({
    rootDir: config.rootDir,
    scriptsDir: config.scriptsDir,
    argosPackagesDir: config.argosPackagesDir,
    voiceProfilesDir: config.voiceProfilesDir,
    sourceLanguage: "en",
    targetLanguage: "te",
  });

  const selfTest = await runSelfTest(config);

  return {
    inspectedAt: new Date().toISOString(),
    hardware,
    topology,
    modelPacks,
    selfTest,
    tempCleanup,
  };
}

async function runSelfTest(config = getCoreConfig()) {
  const checks = [
    checkPath("python", config.pythonPath),
    checkPath("sox", config.soxPath),
    checkPath("whisperWorker", config.whisperWorkerPath),
    checkPath("whisperModel", config.whisperModelPath),
    checkPath("argosWorker", config.argosWorkerPath),
    checkPath("xttsWorker", config.xttsWorkerPath),
    checkPath("prosodyExtractor", config.prosodyExtractorPath),
    checkPath("prosodyTransfer", config.prosodyTransferPath),
    checkPath("audioSeparator", config.audioSeparatorPath),
    checkPath("speakScript", config.speakScriptPath),
    checkPath("topologyScript", config.topologyScriptPath),
  ];

  const results = await Promise.all(checks);
  return {
    ok: results.every((check) => check.ok),
    checks: results,
  };
}

async function checkPath(label, targetPath) {
  return require("fs/promises")
    .access(targetPath)
    .then(() => ({ label, path: targetPath, ok: true }))
    .catch(() => ({ label, path: targetPath, ok: false }));
}

module.exports = {
  ensureRuntimeLayout,
  runBootstrapInspection,
  runSelfTest,
};
