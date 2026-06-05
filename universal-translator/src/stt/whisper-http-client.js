const { EventEmitter } = require("events");
const { spawn } = require("child_process");
const http = require("http");
const path = require("path");
const { getPythonEnv } = require("../../packages/ult-core/src/config");

const DEFAULT_PORT = 8765;
const DEFAULT_STARTUP_TIMEOUT_MS = 45000;
const DEFAULT_POLL_INTERVAL_MS = 500;

class WhisperHttpClient extends EventEmitter {
  constructor(config) {
    super();
    this.config  = config;
    this.port    = Number.isFinite(config?.whisperHttpPort) ? config.whisperHttpPort : DEFAULT_PORT;
    this.proc    = null;
    this.ready   = false;
    this.readyPromise = null;
    this.spawnImpl = config?.spawnImpl || spawn;
    this.pollIntervalMs = Number.isFinite(config?.whisperHealthPollIntervalMs)
      ? config.whisperHealthPollIntervalMs
      : DEFAULT_POLL_INTERVAL_MS;
    this.startupTimeoutMs = Number.isFinite(config?.whisperStartupTimeoutMs)
      ? config.whisperStartupTimeoutMs
      : DEFAULT_STARTUP_TIMEOUT_MS;
    this.startupLogs = [];
  }

  _start() {
    if (this.readyPromise) return this.readyPromise;

    this.readyPromise = new Promise((resolve, reject) => {
      const env = getPythonEnv(this.config);
      let settled = false;
      const settleResolve = () => {
        if (settled) return;
        settled = true;
        this.ready = true;
        this.emit("debug", "Whisper HTTP server ready");
        resolve();
      };
      const settleReject = (error) => {
        if (settled) return;
        settled = true;
        this.ready = false;
        this.readyPromise = null;
        reject(error);
      };

      this.proc = this.spawnImpl(
        this.config.pythonPath,
        [
          path.join(this.config.scriptsDir, "whisper_http_server.py"),
          this.config.whisperModelPath,
          String(this.port),
        ],
        { stdio: ["ignore", "pipe", "pipe"], env }
      );

      this.startupLogs = [];
      const captureLog = (channel, chunk) => {
        const lines = chunk
          .toString()
          .split(/\r?\n/)
          .map((line) => line.trim())
          .filter(Boolean);

        for (const line of lines) {
          const tagged = `[${channel}] ${line}`;
          this.startupLogs.push(tagged);
          if (this.startupLogs.length > 50) {
            this.startupLogs.shift();
          }
          this.emit("debug", tagged);
        }
      };

      this.proc.stdout?.on("data", (chunk) => captureLog("stdout", chunk));
      this.proc.stderr?.on("data", (chunk) => captureLog("stderr", chunk));

      this.proc.on("error", (err) => {
        this.emit("error", err);
        settleReject(err);
      });

      this.proc.on("close", (code) => {
        this.ready = false;
        this.proc = null;
        if (!settled) {
          settleReject(new Error(this._formatStartupFailure(
            `Whisper HTTP server exited before becoming ready (code=${code ?? "none"})`
          )));
          return;
        }
        this.readyPromise = null;
        this.emit("debug", `Whisper HTTP server exited (code=${code ?? "none"})`);
      });

      this._waitForHealth()
        .then(() => settleResolve())
        .catch((error) => {
          if (!settled && this.proc) {
            this.proc.kill();
          }
          settleReject(error);
        });
    });

    return this.readyPromise;
  }

  async _waitForHealth() {
    const deadline = Date.now() + this.startupTimeoutMs;
    while (Date.now() < deadline) {
      try {
        const health = await this._getHealth();
        if (health?.status === "ok") {
          return true;
        }
      } catch {
        // Keep polling until the timeout window expires.
      }
      await new Promise((resolve) => setTimeout(resolve, this.pollIntervalMs));
    }
    throw new Error(this._formatStartupFailure("Whisper HTTP server startup timeout"));
  }

  _getHealth() {
    return new Promise((resolve, reject) => {
      const req = http.request(
        {
          hostname: "127.0.0.1",
          port: this.port,
          path: "/health",
          method: "GET",
          timeout: 1000,
        },
        (res) => {
          let data = "";
          res.on("data", (chunk) => {
            data += chunk;
          });
          res.on("end", () => {
            try {
              resolve(JSON.parse(data));
            } catch (error) {
              reject(new Error(`Invalid JSON from Whisper health endpoint: ${data}`));
            }
          });
        }
      );
      req.on("timeout", () => {
        req.destroy(new Error("Whisper health check timeout"));
      });
      req.on("error", reject);
      req.end();
    });
  }

  _formatStartupFailure(message) {
    const logTail = this.startupLogs.length ? ` | logs: ${this.startupLogs.join(" || ")}` : "";
    return `${message}${logTail}`;
  }

  async transcribeChunk({ audioPath, sourceLanguage, targetLanguage, onlinePolicy }) {
    await this._start();

    const body = JSON.stringify({
      audio_path:      audioPath,
      source_language: sourceLanguage || "en",
      target_language: targetLanguage || "en",
    });

    return new Promise((resolve, reject) => {
      const req = http.request(
        {
          hostname: "127.0.0.1",
          port:     this.port,
          path:     "/transcribe",
          method:   "POST",
          headers:  { "Content-Type": "application/json", "Content-Length": Buffer.byteLength(body) },
        },
        (res) => {
          let data = "";
          res.on("data", (chunk) => { data += chunk; });
          res.on("end", () => {
            try {
              const result = JSON.parse(data);
              if (result.error) { reject(new Error(result.error)); return; }
              resolve({ ...result, backend: "faster-whisper" });
            } catch (e) {
              reject(new Error(`Invalid JSON from Whisper server: ${data}`));
            }
          });
        }
      );
      req.on("error", reject);
      req.write(body);
      req.end();
    });
  }

  stop() {
    if (this.proc) {
      this.proc.kill();
      this.proc = null;
      this.ready = false;
      this.readyPromise = null;
    }
  }
}

module.exports = { WhisperHttpClient };
