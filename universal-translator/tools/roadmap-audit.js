#!/usr/bin/env node

const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");

const requiredFiles = [
  "src/audio/capture.js",
  "src/pipeline/realtime-translator.js",
  "packages/ult-core/src/audio-routing/route-profiles.js",
  "packages/ult-core/src/tts-engine/playback-controller.js",
  "tools/ult-doctor.js",
  "docs/EXECUTION_ROADMAP.md",
  "docs/ULT_SYSTEM_BLUEPRINT.md",
];

const requiredRuntimeAssets = [
  "Scripts/whisper_stream_worker.py",
  "Scripts/vosk_stream_worker.py",
  "Scripts/marian_translate_worker.py",
  "Scripts/edge_tts_worker.py",
  "sox-14.4.2/sox.exe",
];

const unwantedRepoSurface = [
  "_merged-from-ult-translator1",
  "venv",
  ".venv",
  "Include",
  "share",
  "pyvenv.cfg",
  "dist",
  "build",
];

const generatedIgnoredSurface = [
  "node_modules",
  ".next",
];

let failed = false;

section("ULT Roadmap Audit");
checkRequired("Execution-critical source files", requiredFiles);
checkRequired("Runtime assets used by the current pipeline", requiredRuntimeAssets);
checkAbsent("Generated or stale folders outside the active repo surface", unwantedRepoSurface);
checkIgnoredGenerated("Ignored generated folders", generatedIgnoredSurface);
checkGitIgnore();
checkLatencyConfig();
checkBlueprintSignals();

if (failed) {
  console.log("\nResult: action needed");
  process.exit(1);
}

console.log("\nResult: roadmap audit passed");

function checkRequired(label, relativePaths) {
  section(label);
  for (const relativePath of relativePaths) {
    const fullPath = path.join(root, relativePath);
    if (fs.existsSync(fullPath)) {
      ok(relativePath);
    } else {
      fail(relativePath, "missing");
    }
  }
}

function checkAbsent(label, relativePaths) {
  section(label);
  for (const relativePath of relativePaths) {
    const fullPath = path.join(root, relativePath);
    if (fs.existsSync(fullPath)) {
      fail(relativePath, "should live in runtime/quarantine, not active source");
    } else {
      ok(relativePath);
    }
  }
}

function checkIgnoredGenerated(label, relativePaths) {
  section(label);
  for (const relativePath of relativePaths) {
    const fullPath = path.join(root, relativePath);
    if (fs.existsSync(fullPath)) {
      warn(relativePath, "present locally but allowed because it is generated and ignored");
    } else {
      ok(relativePath);
    }
  }
}

function checkGitIgnore() {
  section("Repo hygiene rules");
  const gitignorePath = path.join(root, ".gitignore");
  const gitignore = fs.existsSync(gitignorePath) ? fs.readFileSync(gitignorePath, "utf8") : "";
  const expectedRules = ["node_modules", ".env", "models/", "Scripts/", "pyvenv.cfg"];

  for (const rule of expectedRules) {
    if (gitignore.includes(rule)) {
      ok(`.gitignore contains ${rule}`);
    } else {
      fail(".gitignore", `missing ${rule}`);
    }
  }
}

function checkLatencyConfig() {
  section("Realtime latency posture");
  const configPath = path.join(root, "packages/ult-core/src/config.js");
  const config = fs.existsSync(configPath) ? fs.readFileSync(configPath, "utf8") : "";
  const signals = [
    "realtimeTargetLatencyMs",
    "realtimeMaxQueueDepth",
    "streamingWindowMs",
    "streamingHopMs",
  ];

  for (const signal of signals) {
    if (config.includes(signal)) {
      ok(signal);
    } else {
      fail("config.js", `missing ${signal}`);
    }
  }
}

function checkBlueprintSignals() {
  section("Seven-layer architecture signals");
  const signals = [
    ["audio interception", ["src/audio/capture.js", "modules/audio-capture/index.js", "modules/mic-routing/setup-virtual-mic.ps1"]],
    ["temporal buffer", ["packages/ult-core/src/audio-capture/ring-buffer.js", "src/pipeline/realtime-translator.js"]],
    ["STT", ["packages/ult-core/src/stt-engine/index.js", "packages/ult-core/src/stt-engine/faster-whisper.js"]],
    ["translation", ["packages/ult-core/src/translation-engine/index.js", "src/translation/service.js"]],
    ["voice identity", ["packages/ult-core/src/voice-identity/profile.js", "src/audio/expressiveness.js"]],
    ["audio reconstruction", ["packages/ult-core/src/tts-engine/playback-controller.js", "src/pipeline/utterance-manager.js"]],
    ["output injection", ["packages/ult-core/src/tts-engine/tiered-speaker.js", "packages/ult-core/src/mic-routing/router.js"]],
  ];

  for (const [layer, candidates] of signals) {
    const found = candidates.some((relativePath) => fs.existsSync(path.join(root, relativePath)));
    if (found) {
      ok(layer);
    } else {
      fail(layer, `missing one of: ${candidates.join(", ")}`);
    }
  }
}

function section(label) {
  console.log(`\n${label}`);
}

function ok(label) {
  console.log(`[ok] ${label}`);
}

function warn(label, detail) {
  console.log(`[warn] ${label}: ${detail}`);
}

function fail(label, detail) {
  failed = true;
  console.log(`[fail] ${label}: ${detail}`);
}
