const { existsSync } = require("fs");

const config = require("./config");

for (const [label, value] of [
  ["Python", config.pythonPath],
  ["SoX", config.soxPath],
  ["Whisper worker", config.whisperWorkerPath],
  ["Whisper model", config.whisperModelPath],
  ["Speaker script", config.speakScriptPath],
]) {
  if (!existsSync(value)) {
    throw new Error(`${label} path does not exist: ${value}`);
  }
}

module.exports = {
  config,
};
