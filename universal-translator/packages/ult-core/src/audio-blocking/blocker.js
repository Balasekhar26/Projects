const { spawn } = require("child_process");
const path = require("path");
const { EventEmitter } = require("events");

class AudioBlocker extends EventEmitter {
  constructor(config) {
    super();
    this.config = config;
    this.isBlocking = false;
    this.spawnImpl = config?.spawnImpl || spawn;
    this.powershellPath = config?.powershellPath || "powershell.exe";
    this.scriptPath = path.join(__dirname, "..", "..", "..", "..", "tools", "route-audio.ps1");
  }

  async blockAudio() {
    const currentStatus = await this.getStatus().catch(() => null);
    if (currentStatus?.intercepted) {
      this.isBlocking = true;
      this.emit("debug", "Audio interception already active");
      return true;
    }

    try {
      const result = await this.runScript("intercept");
      const confirmedByScript = /intercept on/i.test(result.stdout);
      if (!confirmedByScript) {
        throw new Error(result.stdout || "Audio interception script exited successfully but did not confirm interception.");
      }
      this.isBlocking = true;
      this.emit("status", result.stdout || "System audio redirected to virtual cable");
      const status = await this.getStatus().catch(() => null);
      if (!status?.intercepted) {
        this.emit("debug", "Audio interception verification lagged behind the script result; proceeding with script-confirmed state");
      }
      return true;
    } catch (error) {
      this.isBlocking = false;
      this.emit("error", new Error(`Audio interception failed: ${error.message}`));
      return false;
    }
  }

  async unblockAudio() {
    const currentStatus = await this.getStatus().catch(() => null);
    if (!currentStatus?.intercepted) {
      this.isBlocking = false;
      this.emit("debug", "Audio interception not active");
      return true;
    }

    try {
      const result = await this.runScript("restore");
      const confirmedByScript =
        !/intercept on/i.test(result.stdout) &&
        /restored|nothing to restore|no saved device/i.test(result.stdout || "");
      if (!confirmedByScript) {
        throw new Error(result.stdout || "Audio restore script exited successfully but did not confirm restore.");
      }
      this.isBlocking = false;
      this.emit("status", result.stdout || "System audio route restored");
      const status = await this.getStatus().catch(() => null);
      if (status?.intercepted) {
        this.emit("debug", "Audio restore verification lagged behind the script result; proceeding with script-confirmed state");
      }
      return true;
    } catch (error) {
      this.emit("error", new Error(`Audio restore failed: ${error.message}`));
      return false;
    }
  }

  async getStatus() {
    try {
      const result = await this.runScript("status");
      const defaultPlayback = result.stdout || "";
      const intercepted = /cable input/i.test(defaultPlayback);
      if (intercepted) {
        this.isBlocking = true;
      }
      return {
        intercepted,
        defaultPlayback,
      };
    } catch {
      return null;
    }
  }

  runScript(action) {
    return new Promise((resolve, reject) => {
      const child = this.spawnImpl(this.powershellPath, [
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        this.scriptPath,
        action,
      ]);

      let stdout = "";
      let stderr = "";

      child.stdout?.on("data", (chunk) => {
        const message = chunk.toString();
        stdout += message;
        if (message.trim()) {
          this.emit("debug", message.trim());
        }
      });

      child.stderr?.on("data", (chunk) => {
        const message = chunk.toString();
        stderr += message;
        if (message.trim()) {
          this.emit("debug", message.trim());
        }
      });

      child.on("close", (code) => {
        const trimmedStdout = stdout.trim();
        const trimmedStderr = stderr.trim();
        if (code !== 0) {
          reject(new Error(trimmedStderr || trimmedStdout || `route-audio.ps1 ${action} exited with code ${code}`));
          return;
        }
        if (trimmedStderr) {
          reject(new Error(trimmedStderr));
          return;
        }
        resolve({
          stdout: trimmedStdout,
          stderr: trimmedStderr,
        });
      });

      child.on("error", (error) => {
        reject(new Error(`Failed to execute route-audio.ps1 ${action}: ${error.message}`));
      });
    });
  }

  async cleanup() {
    if (this.isBlocking) {
      await this.unblockAudio();
    }
  }
}

module.exports = {
  AudioBlocker,
};
