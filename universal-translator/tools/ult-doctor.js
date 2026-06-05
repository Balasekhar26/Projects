#!/usr/bin/env node

const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");
const { getCoreConfig } = require("../packages/ult-core/src/config");
const { listDeviceTopology } = require("../packages/ult-core/src/device-control/topology");
const { validateRouteProfile } = require("../packages/ult-core/src/audio-routing/validator");

const root = path.resolve(__dirname, "..");
const dotenvPath = path.join(root, ".env");
if (fs.existsSync(dotenvPath)) require("dotenv").config({ path: dotenvPath });

const desktopShortcut = path.join(process.env.USERPROFILE || "", "Desktop", "ULT Translator.lnk");
const startMenuDir = path.join(process.env.APPDATA || "", "Microsoft", "Windows", "Start Menu", "Programs", "ULT Translator");
const startMenuShortcut = path.join(startMenuDir, "ULT Translator.lnk");
const launchTarget = path.join(root, "run.exe");

let ok = true;
const coreConfig = getCoreConfig({ runtimeRootDir: root });

log("ULT Doctor");
ensureDir(path.join(root, ".ult-runtime"));
ensureDir(path.join(root, ".ult-runtime", "temp"));
ensureDir(path.join(root, "models"));
ensureDir(path.join(root, "models", "argos"));
ensureDir(path.join(root, "models", "voice-profiles"));
ensureDir(path.join(root, "models", "marian"));

ensureFileFromTemplate(path.join(root, ".env"), path.join(root, ".env.example"));
ensureShortcut(desktopShortcut, launchTarget, root, "ULT Universal Language Translator");
ensureDir(startMenuDir);
ensureShortcut(startMenuShortcut, launchTarget, root, "ULT Universal Language Translator");

checkPath("Node.js", findCommand("node"));
checkRunnable("Python runtime", coreConfig.pythonPath, ["--version"]);
checkPath("Electron", path.join(root, "node_modules", ".bin", "electron.cmd"));
checkPath("SoX", path.join(root, "sox-14.4.2", "sox.exe"));
checkPath("Whisper worker", path.join(root, "Scripts", "whisper_stream_worker.py"));
checkPath("Argos worker", path.join(root, "Scripts", "argos_translate_worker.py"));
checkOptionalEnv("NVIDIA NIM translation", "NVIDIA_NIM_API_KEY");
checkOptionalEnv("DeepL translation", "DEEPL_API_KEY");
checkOptionalEnv("OpenAI speech", "OPENAI_API_KEY");

main().catch((error) => {
  fail("Audio topology", error.message);
  process.exit(1);
});

function ensureDir(target) {
  fs.mkdirSync(target, { recursive: true });
  pass(path.relative(root, target) || target, "ready");
}

function ensureFileFromTemplate(target, template) {
  if (!fs.existsSync(target) && fs.existsSync(template)) {
    fs.copyFileSync(template, target);
    pass(path.basename(target), "created from template");
    return;
  }
  if (fs.existsSync(target)) {
    pass(path.basename(target), "present");
    return;
  }
  fail(path.basename(target), "missing");
}

function ensureShortcut(shortcutPath, targetPath, workingDir, description) {
  if (fs.existsSync(shortcutPath)) {
    pass(path.basename(shortcutPath), "present");
    return;
  }

  const script = `
$ws = New-Object -ComObject WScript.Shell
$s = $ws.CreateShortcut('${escapePs(shortcutPath)}')
$s.TargetPath = '${escapePs(targetPath)}'
$s.WorkingDirectory = '${escapePs(workingDir)}'
$s.Description = '${escapePs(description)}'
$s.Save()
`;
  const result = runPowerShell(script);
  if (result.status === 0 && fs.existsSync(shortcutPath)) {
    pass(path.basename(shortcutPath), "created");
  } else {
    fail(path.basename(shortcutPath), "could not create");
  }
}

function checkPath(label, target) {
  if (target && fs.existsSync(target)) {
    pass(label, "present");
  } else {
    fail(label, "missing");
  }
}

function checkOptionalEnv(label, envName) {
  if (process.env[envName]) {
    pass(label, `${envName} configured`);
  } else {
    console.log(`[optional] ${label}: ${envName} not configured`);
  }
}

function findCommand(command) {
  const result = spawnSync("where", [command], { encoding: "utf8", shell: true });
  if (result.status === 0) {
    return result.stdout.split(/\r?\n/).find(Boolean) || "";
  }
  return "";
}

function runPowerShell(script) {
  return spawnSync("powershell", ["-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script], {
    encoding: "utf8",
    shell: true,
  });
}

function escapePs(value) {
  return String(value).replace(/'/g, "''");
}

function log(message) {
  console.log(`[doctor] ${message}`);
}

function pass(label, detail) {
  console.log(`[ok] ${label}: ${detail}`);
}

function fail(label, detail) {
  ok = false;
  console.log(`[fail] ${label}: ${detail}`);
}

async function main() {
  const config = coreConfig;
  const topology = await listDeviceTopology(config);
  const routing = validateRouteProfile({
    request: {
      platform: "windows",
      sessionKind: "desktop_runtime",
      routeProfileId: "windows-desktop-runtime",
    },
    topology,
  });

  if (routing.ok) {
    pass("Virtual audio devices", "present");
  } else {
    fail("Virtual audio devices", routing.diagnostics.join(" "));
  }

  process.exit(ok ? 0 : 1);
}

function checkRunnable(label, command, args = []) {
  const result = spawnSync(command, args, { encoding: "utf8", shell: false });
  if (result.status === 0) {
    pass(label, `${command} ${String(result.stdout || result.stderr).trim()}`);
  } else {
    fail(label, `${command} is not runnable`);
  }
}
