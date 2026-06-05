const fs = require("fs/promises");
const { spawn } = require("child_process");

const { getCoreConfig, getPythonEnv } = require("../config");
const {
  buildLanguagePairPackId,
  hasArgosLanguagePair,
} = require("../catalog/model-packs");
const { ensureRuntimeLayout, pruneTempArtifacts } = require("./runtime-layout");

async function prepareRuntimeForSession(options = {}) {
  const config = options.config || getCoreConfig();
  const sourceLanguage = normalizeLanguage(options.sourceLanguage || "en");
  const targetLanguage = normalizeLanguage(options.targetLanguage || "te");
  const onlinePolicy = normalizeOnlinePolicy(options.onlinePolicy || "auto");

  await ensureRuntimeLayout(config);
  const tempCleanup = await pruneTempArtifacts(config);

  const actions = [
    {
      step: "runtime-layout",
      status: "ready",
      detail: "Runtime directories verified.",
    },
    {
      step: "temp-cleanup",
      status: tempCleanup.removedCount ? "cleaned" : "ready",
      detail: tempCleanup.removedCount
        ? `Removed ${tempCleanup.removedCount} transient audio file(s).`
        : "No transient audio cleanup was needed.",
    },
  ];

  if (onlinePolicy === "online-only") {
    actions.push({
      step: "offline-pack",
      status: "skipped",
      detail: "Offline pack provisioning skipped because the session is online-only.",
    });
  } else {
    try {
      const offlinePack = await ensureOfflineLanguagePack(config, {
        sourceLanguage,
        targetLanguage,
      });
      actions.push({
        step: "offline-pack",
        status: offlinePack.status,
        detail: offlinePack.detail,
        packId: offlinePack.packId,
      });
    } catch (error) {
      if (onlinePolicy === "offline-only") {
        throw error;
      }

      actions.push({
        step: "offline-pack",
        status: "deferred",
        detail: error instanceof Error ? error.message : "Offline pack provisioning failed.",
      });
    }
  }

  return {
    preparedAt: new Date().toISOString(),
    sourceLanguage,
    targetLanguage,
    onlinePolicy,
    actions,
  };
}

async function ensureOfflineLanguagePack(config = getCoreConfig(), options = {}) {
  const sourceLanguage = normalizeLanguage(options.sourceLanguage || "en");
  const targetLanguage = normalizeLanguage(options.targetLanguage || "te");
  const packId = buildLanguagePairPackId(sourceLanguage, targetLanguage);

  if (!sourceLanguage || !targetLanguage || sourceLanguage === targetLanguage) {
    return {
      packId,
      status: "skipped",
      detail: "Offline translation pack is not needed for identical language pairs.",
    };
  }

  await fs.mkdir(config.argosPackagesDir, { recursive: true });
  if (hasArgosLanguagePair(config.argosPackagesDir, sourceLanguage, targetLanguage)) {
    return {
      packId,
      status: "installed",
      detail: `Offline translation pack ${sourceLanguage} -> ${targetLanguage} is already installed.`,
    };
  }

  const workerPayload = await runJsonWorker(config.pythonPath, [
    config.argosEnsurePairPath,
    "--packages-dir",
    config.argosPackagesDir,
    "--source",
    sourceLanguage,
    "--target",
    targetLanguage,
  ], config);

  if (workerPayload.status === "error") {
    throw new Error(workerPayload.message || "Argos provisioning failed.");
  }

  return {
    packId,
    status: workerPayload.status === "already-installed" ? "installed" : "downloaded",
    detail:
      workerPayload.status === "already-installed"
        ? `Offline translation pack ${sourceLanguage} -> ${targetLanguage} is already installed.`
        : `Offline translation pack ${sourceLanguage} -> ${targetLanguage} was downloaded and installed.`,
  };
}

function runJsonWorker(command, args, config) {
  const pythonEnv = config ? getPythonEnv(config) : process.env;
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, {
      stdio: ["ignore", "pipe", "pipe"],
      env: pythonEnv,
    });

    let stdout = "";
    let stderr = "";

    child.stdout.on("data", (chunk) => {
      stdout += chunk.toString();
    });

    child.stderr.on("data", (chunk) => {
      stderr += chunk.toString();
    });

    child.on("error", reject);
    child.on("close", (code) => {
      if (code !== 0) {
        reject(new Error(stderr.trim() || `Provisioning worker failed with exit code ${code}.`));
        return;
      }

      try {
        const lines = stdout
          .split(/\r?\n/)
          .map((line) => line.trim())
          .filter(Boolean);
        const payload = JSON.parse(lines.at(-1) || "{}");
        resolve(payload);
      } catch {
        reject(new Error("Provisioning worker did not return valid JSON."));
      }
    });
  });
}

function normalizeLanguage(value) {
  return typeof value === "string" && value.trim() ? value.trim().toLowerCase() : "";
}

function normalizeOnlinePolicy(value) {
  const normalized = typeof value === "string" ? value.trim().toLowerCase() : "";
  return normalized || "auto";
}

module.exports = {
  ensureOfflineLanguagePack,
  prepareRuntimeForSession,
};
