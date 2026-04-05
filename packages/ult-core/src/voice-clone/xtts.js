const fs = require("fs/promises");
const path = require("path");
const { spawn } = require("child_process");

class XttsVoiceCloneEngine {
  constructor(config) {
    this.config = config;
  }

  async synthesizeToWave({ text, language, samplePath, outputPath }) {
    if (!samplePath) {
      throw new Error("XTTS requires a reference sample.");
    }

    await fs.mkdir(path.dirname(outputPath), { recursive: true });

    return new Promise((resolve, reject) => {
      const child = spawn(this.config.pythonPath, [
        this.config.xttsWorkerPath,
        "--text",
        text,
        "--language",
        language || "en",
        "--sample",
        samplePath,
        "--output",
        outputPath,
      ]);

      let stderr = "";
      child.stderr.on("data", (chunk) => {
        stderr += chunk.toString();
      });
      child.on("error", reject);
      child.on("close", (code) => {
        if (code === 0) {
          resolve(outputPath);
          return;
        }

        reject(new Error(stderr.trim() || `XTTS synthesis failed with exit code ${code}.`));
      });
    });
  }
}

module.exports = {
  XttsVoiceCloneEngine,
};
