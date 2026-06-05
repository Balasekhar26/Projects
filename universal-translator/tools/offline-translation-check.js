#!/usr/bin/env node

const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");
const { getCoreConfig } = require("../packages/ult-core/src/config");

const root = path.resolve(__dirname, "..");
const config = getCoreConfig({ runtimeRootDir: root });

const checks = [
  ["Python runtime", config.pythonPath],
  ["Argos worker", config.argosWorkerPath],
  ["Argos packages directory", config.argosPackagesDir],
  ["Marian worker", config.marianWorkerPath],
  ["Marian models directory", path.join(config.modelsDir, "marian")],
  ["Google worker", config.googleTranslateWorkerPath],
];

let failed = false;
console.log("Offline Translation Check\n");

for (const [label, target] of checks) {
  if (label === "Python runtime" ? isRunnable(target) : fs.existsSync(target)) {
    console.log(`[ok] ${label}: ${displayTarget(target)}`);
  } else {
    failed = true;
    console.log(`[missing] ${label}: ${displayTarget(target)}`);
  }
}

console.log("\nPolicy:");
console.log(`- ONLINE_POLICY default: ${config.onlinePolicy}`);
console.log(`- ULT_TRANSLATION_PROVIDER: ${config.translationProvider}`);
console.log("- Offline path order: Argos when target is supported, then MarianMT.");
console.log("- Online auto path order: NVIDIA NIM, DeepL, Google worker, then offline fallback.");

process.exit(failed ? 1 : 0);

function isRunnable(command) {
  try {
    return spawnSync(command, ["--version"], { encoding: "utf8", shell: false }).status === 0;
  } catch {
    return false;
  }
}

function displayTarget(target) {
  if (!target.includes("\\") && !target.includes("/")) {
    return target;
  }
  return path.relative(root, target) || target;
}
