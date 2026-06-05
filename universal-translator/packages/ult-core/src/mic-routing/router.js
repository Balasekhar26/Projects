const { spawn } = require("child_process");
const path = require("path");
const fs = require("fs/promises");
const { EventEmitter } = require("events");

class MicrophoneRouter extends EventEmitter {
  constructor(config) {
    super();
    this.config = config;
    this.virtualMicName = config.virtualMicrophoneName || "VB-Audio Virtual Microphone";
    this.isConfigured = false;
    this.setupScriptPath = path.join(__dirname, "setup-virtual-mic.ps1");
  }

  /**
   * Initialize microphone routing for the system
   */
  async initialize() {
    try {
      this.emit("status", "Checking microphone routing setup...");
      
      const status = await this.getRoutingStatus();
      if (status && status.enabled) {
        this.isConfigured = true;
        this.emit("status", `Microphone routing already configured: ${status.virtualDevice}`);
        return { success: true, configured: true, device: status.virtualDevice };
      }

      // Attempt setup if not configured
      this.emit("status", "Configuring microphone routing...");
      const result = await this.setupMicrophoneRouting();
      
      if (result.success) {
        this.isConfigured = true;
        this.emit("status", "Microphone routing configured successfully");
      } else {
        this.emit("warn", "Microphone routing setup incomplete: " + (result.message || "Unknown error"));
      }
      
      return result;
    } catch (error) {
      this.emit("error", new Error(`Microphone router initialization failed: ${error.message}`));
      return { success: false, message: error.message };
    }
  }

  /**
   * Setup virtual microphone routing
   */
  async setupMicrophoneRouting() {
    return new Promise((resolve) => {
      const child = spawn("powershell", [
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", this.setupScriptPath,
        "-Action", "setup",
        "-VirtualMicName", this.virtualMicName
      ]);

      let stdout = "";
      let stderr = "";

      child.stdout?.on("data", (chunk) => {
        stdout += chunk.toString();
        this.emit("debug", chunk.toString().trim());
      });

      child.stderr?.on("data", (chunk) => {
        stderr += chunk.toString();
        this.emit("debug", chunk.toString().trim());
      });

      child.on("close", (code) => {
        if (code === 0) {
          resolve({
            success: true,
            message: "Microphone routing setup completed",
            output: stdout
          });
        } else {
          resolve({
            success: false,
            message: stderr.trim() || `Setup failed with code ${code}`,
            output: stdout
          });
        }
      });

      child.on("error", (error) => {
        resolve({
          success: false,
          message: `Failed to execute setup script: ${error.message}`
        });
      });
    });
  }

  /**
   * Get current microphone routing status
   */
  async getRoutingStatus() {
    return new Promise((resolve) => {
      const child = spawn("powershell", [
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", this.setupScriptPath,
        "-Action", "status"
      ]);

      let stdout = "";

      child.stdout?.on("data", (chunk) => {
        stdout += chunk.toString();
      });

      child.on("close", () => {
        // Parse status output
        const lines = stdout.split("\n");
        const status = {
          configured: false,
          enabled: false,
          virtualDevice: null,
          physicalDevice: null
        };

        for (const line of lines) {
          if (line.includes("Virtual Device:")) {
            status.virtualDevice = line.split(":")[1]?.trim();
          }
          if (line.includes("Physical Device:")) {
            status.physicalDevice = line.split(":")[1]?.trim();
          }
          if (line.includes("Enabled: Yes")) {
            status.enabled = true;
          }
        }

        status.configured = status.virtualDevice !== null;
        resolve(status);
      });

      child.on("error", () => {
        resolve(null);
      });
    });
  }

  /**
   * Get list of available physical microphones
   */
  async getPhysicalMicrophones() {
    const { listDeviceTopology } = require("../device-control/topology");
    
    try {
      const topology = await listDeviceTopology(this.config);
      return topology.inputDevices || [];
    } catch (error) {
      this.emit("error", new Error(`Failed to list microphones: ${error.message}`));
      return [];
    }
  }

  /**
   * Get list of virtual microphone devices
   */
  async getVirtualMicrophones() {
    try {
      const { listDeviceTopology } = require("../device-control/topology");
      const topology = await listDeviceTopology(this.config);
      
      const inputDevices = topology.inputDevices || [];
      return inputDevices.filter((device) => {
        const name = device.name.toLowerCase();
        return name.includes("virtual") || name.includes("cable") || name.includes("voicemeeter");
      });
    } catch (error) {
      this.emit("error", new Error(`Failed to list virtual microphones: ${error.message}`));
      return [];
    }
  }

  /**
   * Check if VB-Cable or Voicemeeter is installed
   */
  async checkVirtualMicDriver() {
    const devices = await this.getVirtualMicrophones();
    return devices.length > 0;
  }

  /**
   * Cleanup microphone routing
   */
  async cleanup() {
    return new Promise((resolve) => {
      const child = spawn("powershell", [
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", this.setupScriptPath,
        "-Action", "cleanup"
      ]);

      child.on("close", (code) => {
        resolve(code === 0);
      });

      child.on("error", () => {
        resolve(false);
      });
    });
  }
}

module.exports = {
  MicrophoneRouter
};
