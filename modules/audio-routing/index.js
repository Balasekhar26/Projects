/**
 * Audio Routing Module
 *
 * Handles audio routing, blocking, and device management:
 * - System audio interception and blocking
 * - Microphone routing
 * - Virtual device management
 * - Audio pipeline coordination
 */

const { EventEmitter } = require("events");
const { spawn } = require("child_process");
const path = require("path");

/**
 * Audio Router - Manages system audio routing and blocking
 */
class AudioRouter extends EventEmitter {
  constructor(config) {
    super();
    this.config = config;
    this.isBlocking = false;
    this.virtualDevices = new Map();
    this.activeRoutes = new Map();
  }

  /**
   * Initialize audio routing for system interception
   */
  async initializeSystemRouting() {
    try {
      // Check for virtual audio devices
      const topology = await this.getAudioTopology();

      if (this.hasVirtualAudioSupport(topology)) {
        this.emit("routing-initialized", {
          method: "virtual-device",
          devices: this.getVirtualDevices(topology)
        });
      } else {
        // Fall back to WASAPI loopback
        this.emit("routing-initialized", {
          method: "wasapi-loopback",
          devices: topology.outputDevices
        });
      }
    } catch (error) {
      this.emit("error", error);
    }
  }

  /**
   * Block original system audio output
   */
  async blockSystemAudio() {
    if (this.isBlocking) return;

    try {
      // Use Windows Audio API to mute system audio
      // This requires administrator privileges for system-wide audio control
      const scriptPath = path.join(__dirname, "block-system-audio.ps1");

      this.blockProcess = spawn("powershell", [
        "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", scriptPath
      ], {
        stdio: ["ignore", "pipe", "pipe"]
      });

      this.isBlocking = true;
      this.emit("audio-blocked", { method: "system-mute" });

      this.blockProcess.on("close", (code) => {
        this.isBlocking = false;
        this.emit("audio-unblocked", { code });
      });

    } catch (error) {
      this.emit("error", new Error(`Failed to block system audio: ${error.message}`));
    }
  }

  /**
   * Unblock system audio
   */
  unblockSystemAudio() {
    if (this.blockProcess) {
      this.blockProcess.kill();
      this.blockProcess = null;
    }
  }

  /**
   * Route translated audio to output device
   */
  routeTranslatedAudio(audioBuffer, outputDevice) {
    // Use PowerShell script to play audio on specific device
    const scriptPath = path.join(__dirname, "play-audio.ps1");

    const playProcess = spawn("powershell", [
      "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", scriptPath,
      "-Device", outputDevice,
      "-Data", audioBuffer.toString("base64")
    ]);

    playProcess.on("close", (code) => {
      if (code !== 0) {
        this.emit("routing-error", new Error(`Audio playback failed with code ${code}`));
      }
    });
  }

  /**
   * Set up microphone routing for translation
   */
  setupMicrophoneRouting(inputDevice, virtualMicDevice) {
    // Route physical mic through virtual device for processing
    const routeId = `mic-${Date.now()}`;

    this.activeRoutes.set(routeId, {
      type: "microphone",
      inputDevice,
      virtualDevice: virtualMicDevice,
      active: true
    });

    this.emit("route-established", {
      id: routeId,
      type: "microphone",
      input: inputDevice,
      output: virtualMicDevice
    });

    return routeId;
  }

  /**
   * Set up system audio routing for translation
   */
  setupSystemAudioRouting(virtualInputDevice, outputDevice) {
    const routeId = `system-${Date.now()}`;

    this.activeRoutes.set(routeId, {
      type: "system",
      virtualInput: virtualInputDevice,
      outputDevice,
      active: true
    });

    this.emit("route-established", {
      id: routeId,
      type: "system",
      virtualInput: virtualInputDevice,
      output: outputDevice
    });

    return routeId;
  }

  /**
   * Remove audio route
   */
  removeRoute(routeId) {
    const route = this.activeRoutes.get(routeId);
    if (route) {
      route.active = false;
      this.activeRoutes.delete(routeId);
      this.emit("route-removed", { id: routeId });
    }
  }

  /**
   * Get current audio topology
   */
  async getAudioTopology() {
    const { listDeviceTopology } = require("../../packages/ult-core/src/device-control/topology");
    return await listDeviceTopology(this.config);
  }

  /**
   * Check if virtual audio devices are available
   */
  hasVirtualAudioSupport(topology) {
    const deviceNames = [
      ...topology.inputDevices.map(d => d.name.toLowerCase()),
      ...topology.outputDevices.map(d => d.name.toLowerCase())
    ];

    return deviceNames.some(name =>
      name.includes("voicemeeter") ||
      name.includes("cable") ||
      name.includes("virtual")
    );
  }

  /**
   * Get available virtual devices
   */
  getVirtualDevices(topology) {
    const virtualDevices = [];

    for (const device of [...topology.inputDevices, ...topology.outputDevices]) {
      const name = device.name.toLowerCase();
      if (name.includes("voicemeeter") || name.includes("cable") || name.includes("virtual")) {
        virtualDevices.push({
          id: device.id,
          name: device.name,
          type: topology.inputDevices.includes(device) ? "input" : "output",
          driver: this.inferDriver(name)
        });
      }
    }

    return virtualDevices;
  }

  /**
   * Infer audio driver from device name
   */
  inferDriver(deviceName) {
    const name = deviceName.toLowerCase();
    if (name.includes("voicemeeter")) return "voicemeeter";
    if (name.includes("cable")) return "vb-cable";
    if (name.includes("virtual")) return "generic-virtual";
    return "unknown";
  }

  /**
   * Clean up all routes and blocking
   */
  cleanup() {
    this.unblockSystemAudio();

    for (const [routeId] of this.activeRoutes) {
      this.removeRoute(routeId);
    }

    this.emit("cleanup-complete");
  }
}

/**
 * Route Profile Manager
 * Manages different routing configurations
 */
class RouteProfileManager {
  constructor() {
    this.profiles = new Map();
    this.loadDefaultProfiles();
  }

  loadDefaultProfiles() {
    // Browser debug profile
    this.profiles.set("browser-debug", {
      id: "browser-debug",
      label: "Browser Debug Harness",
      sessionKind: "browser-debug",
      status: "ready",
      requirements: ["No native device interception required"],
      routing: {
        method: "browser-api",
        blocking: false
      }
    });

    // Windows system translation
    this.profiles.set("windows-system-translate", {
      id: "windows-system-translate",
      label: "Windows Speaker Intercept",
      sessionKind: "system",
      status: "needs-setup",
      requirements: [
        "Install Voicemeeter Banana or VB-CABLE",
        "Route system audio through virtual input",
        "Translated audio routed to physical speakers"
      ],
      routing: {
        method: "virtual-device",
        blocking: true,
        virtualInputRequired: true
      }
    });

    // Windows microphone translation
    this.profiles.set("windows-mic-translate", {
      id: "windows-mic-translate",
      label: "Windows Microphone Translate",
      sessionKind: "microphone",
      status: "ready",
      requirements: [
        "Physical microphone as input",
        "Translated audio to virtual microphone"
      ],
      routing: {
        method: "virtual-device",
        blocking: false,
        virtualOutputRequired: true
      }
    });

    // WASAPI loopback profile
    this.profiles.set("wasapi-loopback", {
      id: "wasapi-loopback",
      label: "WASAPI Loopback Capture",
      sessionKind: "system",
      status: "ready",
      requirements: [
        "Direct system audio interception",
        "No virtual devices required",
        "Requires audio blocking"
      ],
      routing: {
        method: "wasapi-loopback",
        blocking: true
      }
    });
  }

  getProfile(profileId) {
    return this.profiles.get(profileId);
  }

  getAvailableProfiles() {
    return Array.from(this.profiles.values());
  }

  updateProfileStatus(profileId, status, reason = null) {
    const profile = this.profiles.get(profileId);
    if (profile) {
      profile.status = status;
      if (reason) profile.statusReason = reason;
    }
  }

  inferAvailableProfiles(topology) {
    const availableProfiles = [];

    // Browser debug always available
    availableProfiles.push(this.profiles.get("browser-debug"));

    // Check for virtual devices
    const hasVirtualDevices = this.hasVirtualAudioSupport(topology);

    if (hasVirtualDevices) {
      availableProfiles.push(this.profiles.get("windows-system-translate"));
      availableProfiles.push(this.profiles.get("windows-mic-translate"));
    }

    // WASAPI loopback always available on Windows
    if (process.platform === "win32") {
      availableProfiles.push(this.profiles.get("wasapi-loopback"));
    }

    return availableProfiles;
  }

  hasVirtualAudioSupport(topology) {
    const deviceNames = [
      ...topology.inputDevices.map(d => d.name.toLowerCase()),
      ...topology.outputDevices.map(d => d.name.toLowerCase())
    ];

    return deviceNames.some(name =>
      name.includes("voicemeeter") ||
      name.includes("cable") ||
      name.includes("virtual")
    );
  }
}

module.exports = {
  AudioRouter,
  RouteProfileManager
};