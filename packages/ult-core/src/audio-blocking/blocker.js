const { spawn } = require("child_process");
const path = require("path");
const { EventEmitter } = require("events");

class AudioBlocker extends EventEmitter {
  constructor(config) {
    super();
    this.config = config;
    this.isBlocking = false;
    this.scriptPath = path.join(__dirname, "..", "audio-blocking", "wasapi-audio-block.ps1");
  }

  /**
   * Block system audio output
   */
  async blockAudio() {
    if (this.isBlocking) {
      this.emit("debug", "Audio blocking already active");
      return true;
    }

    return new Promise((resolve) => {
      const child = spawn("powershell", [
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", this.scriptPath,
        "block",
        "-v"
      ]);

      let stderr = "";

      child.stderr?.on("data", (chunk) => {
        stderr += chunk.toString();
        this.emit("debug", chunk.toString().trim());
      });

      child.stdout?.on("data", (chunk) => {
        this.emit("debug", chunk.toString().trim());
      });

      child.on("close", (code) => {
        if (code === 0) {
          this.isBlocking = true;
          this.emit("status", "System audio blocked successfully");
          resolve(true);
        } else {
          this.emit("error", new Error(`Audio blocking failed: ${stderr.trim()}`));
          resolve(false);
        }
      });

      child.on("error", (error) => {
        this.emit("error", new Error(`Failed to execute audio blocker: ${error.message}`));
        resolve(false);
      });
    });
  }

  /**
   * Unblock system audio output
   */
  async unblockAudio() {
    if (!this.isBlocking) {
      this.emit("debug", "Audio blocking not active");
      return true;
    }

    return new Promise((resolve) => {
      const child = spawn("powershell", [
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", this.scriptPath,
        "unblock",
        "-v"
      ]);

      let stderr = "";

      child.stderr?.on("data", (chunk) => {
        stderr += chunk.toString();
        this.emit("debug", chunk.toString().trim());
      });

      child.on("close", (code) => {
        if (code === 0) {
          this.isBlocking = false;
          this.emit("status", "System audio unblocked");
          resolve(true);
        } else {
          this.emit("error", new Error(`Audio unblocking failed: ${stderr.trim()}`));
          resolve(false);
        }
      });

      child.on("error", (error) => {
        this.emit("error", new Error(`Failed to execute audio unlocker: ${error.message}`));
        resolve(false);
      });
    });
  }

  /**
   * Get current audio blocking status
   */
  async getStatus() {
    return new Promise((resolve) => {
      const child = spawn("powershell", [
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", this.scriptPath,
        "status"
      ]);

      let stdout = "";

      child.stdout?.on("data", (chunk) => {
        stdout += chunk.toString();
      });

      child.on("close", (code) => {
        if (code === 0) {
          const lines = stdout.split("\n");
          const status = {
            muted: false,
            volumeLevel: 1.0
          };

          for (const line of lines) {
            if (line.includes("Muted:")) {
              status.muted = line.toLowerCase().includes("true");
            }
            if (line.includes("Volume:")) {
              const match = line.match(/(\d+)/);
              if (match) {
                status.volumeLevel = parseInt(match[1]) / 100;
              }
            }
          }

          resolve(status);
        } else {
          resolve(null);
        }
      });

      child.on("error", () => {
        resolve(null);
      });
    });
  }

  /**
   * Cleanup blocking on shutdown
   */
  async cleanup() {
    if (this.isBlocking) {
      await this.unblockAudio();
    }
  }
}

module.exports = {
  AudioBlocker
};
