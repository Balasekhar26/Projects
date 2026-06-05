const { spawn } = require("child_process");
const readline = require("readline");
const path = require("path");
const { getPythonEnv, resolveCoreConfig } = require("../config");

class ProsodyEngine {
  constructor(config = {}) {
    this.config = resolveCoreConfig(config);
    this.extractorProc = null;
    this.transferProc = null;
    this.extractorPending = new Map();
    this.transferPending = new Map();
    this.nextId = 1;
    this.extractorWorkerPath = this.config.prosodyExtractorPath || path.join(this.config.scriptsDir, "prosody_extractor_worker.py");
    this.transferWorkerPath = this.config.prosodyTransferPath || path.join(this.config.scriptsDir, "prosody_transfer_worker.py");
  }

  _startWorker(workerPath, pendingMap) {
    const proc = spawn(this.config.pythonPath, [workerPath], {
      stdio: ["pipe", "pipe", "pipe"],
      env: getPythonEnv(this.config),
    });
    readline.createInterface({ input: proc.stdout, crlfDelay: Infinity })
      .on("line", (line) => {
        if (!line.trim()) return;
        let msg;
        try { msg = JSON.parse(line); } catch { return; }
        const entry = pendingMap.get(msg.id);
        if (!entry) return;
        pendingMap.delete(msg.id);
        if (msg.error) entry.reject(new Error(msg.error));
        else entry.resolve(msg);
      });
    proc.on("close", () => {
      for (const e of pendingMap.values()) e.reject(new Error("Prosody worker exited"));
      pendingMap.clear();
    });
    return proc;
  }

  extractProsody(audioPath) {
    if (!this.extractorProc) {
      this.extractorProc = this._startWorker(this.extractorWorkerPath, this.extractorPending);
    }
    const id = String(this.nextId++);
    return new Promise((resolve, reject) => {
      this.extractorPending.set(id, { resolve, reject });
      this.extractorProc.stdin.write(JSON.stringify({ id, audio_path: audioPath }) + "\n", "utf8");
    });
  }

  transferProsody({ inputWav, outputWav, pitchMean, pitchStd, energyMean, speakingRate }) {
    if (!this.transferProc) {
      this.transferProc = this._startWorker(this.transferWorkerPath, this.transferPending);
    }
    const id = String(this.nextId++);
    return new Promise((resolve, reject) => {
      this.transferPending.set(id, { resolve, reject });
      this.transferProc.stdin.write(
        JSON.stringify({
          id,
          input_wav: inputWav,
          output_wav: outputWav,
          pitch_mean: pitchMean || 0,
          pitch_std: pitchStd || 0,
          energy_mean: energyMean || 0,
          speaking_rate: speakingRate || 0,
        }) + "\n",
        "utf8"
      );
    });
  }

  stop() {
    if (this.extractorProc) { this.extractorProc.stdin.end(); this.extractorProc = null; }
    if (this.transferProc) { this.transferProc.stdin.end(); this.transferProc = null; }
  }
}

module.exports = { ProsodyEngine };
