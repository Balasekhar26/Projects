const readline = require("readline");
const { spawn } = require("child_process");
const { getPythonEnv, resolveCoreConfig } = require("../config");

class ArgosTranslateClient {
  constructor(config = {}) {
    this.config = resolveCoreConfig(config);
    this.process = null;
    this.pendingRequests = new Map();
    this.requestId = 1;
  }

  start() {
    if (this.process) {
      return;
    }

    this.process = spawn(this.config.pythonPath, [this.config.argosWorkerPath, this.config.argosPackagesDir], {
      stdio: ["pipe", "pipe", "pipe"],
      env: getPythonEnv(this.config),
    });

    const lineReader = readline.createInterface({
      input: this.process.stdout,
      crlfDelay: Infinity,
    });

    lineReader.on("line", (line) => this.handleLine(line));
    this.process.on("close", (code, signal) => {
      const error = new Error(
        `Argos worker exited unexpectedly (code=${code}, signal=${signal || "none"}).`
      );
      for (const entry of this.pendingRequests.values()) {
        entry.reject(error);
      }
      this.pendingRequests.clear();
      this.process = null;
    });
  }

  translate({ text, sourceLanguage, targetLanguage }) {
    this.start();
    const id = String(this.requestId++);

    return new Promise((resolve, reject) => {
      this.pendingRequests.set(id, { resolve, reject });
      this.process.stdin.write(
        `${JSON.stringify({ id, text, source_language: sourceLanguage, target_language: targetLanguage })}\n`,
        "utf8"
      );
    });
  }

  stop() {
    if (!this.process) {
      return;
    }

    this.process.stdin.end();
    this.process = null;
  }

  handleLine(line) {
    if (!line.trim()) {
      return;
    }

    let payload;
    try {
      payload = JSON.parse(line);
    } catch {
      return;
    }

    const request = this.pendingRequests.get(payload.id);
    if (!request) {
      return;
    }

    this.pendingRequests.delete(payload.id);
    if (payload.error) {
      request.reject(new Error(payload.error));
      return;
    }

    request.resolve(payload.translated_text || "");
  }
}

module.exports = {
  ArgosTranslateClient,
};
