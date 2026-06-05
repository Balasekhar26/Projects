const { existsSync } = require("fs");
const { getCoreConfig } = require("../packages/ult-core/src/config");

function getRuntimeConfig() {
  return getCoreConfig();
}

function validateRuntimeConfig(config = getRuntimeConfig()) {
  const checks = [
    ["Python", config.pythonPath],
    ["SoX", config.soxPath],
    ["Whisper worker", config.whisperWorkerPath],
    ["Whisper model", config.whisperModelPath],
    ["Speaker script", config.speakScriptPath],
  ];

  return checks.map(([label, value]) => ({
    label,
    path: value,
    ok: existsSync(value),
  }));
}

module.exports = {
  config: getRuntimeConfig(),
  getRuntimeConfig,
  validateRuntimeConfig,
};
