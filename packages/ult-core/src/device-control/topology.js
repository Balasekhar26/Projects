const { spawn } = require("child_process");

const { getCoreConfig } = require("../config");
const { inferRouteProfiles } = require("../audio-routing/route-profiles");

function listDeviceTopology(config = getCoreConfig()) {
  return new Promise((resolve, reject) => {
    const child = spawn("powershell", [
      "-NoProfile",
      "-ExecutionPolicy",
      "Bypass",
      "-File",
      config.topologyScriptPath,
    ]);

    let stdout = "";
    let stderr = "";

    child.stdout.on("data", (chunk) => {
      stdout += chunk.toString();
    });

    child.stderr.on("data", (chunk) => {
      stderr += chunk.toString();
    });

    child.on("error", reject);
    child.on("close", (code) => {
      if (code !== 0) {
        reject(new Error(stderr.trim() || `Device topology probe failed with exit code ${code}.`));
        return;
      }

      try {
        const payload = JSON.parse(stdout.trim() || "{}");
        const topology = {
          platform: process.platform,
          inputDevices: Array.isArray(payload.inputDevices) ? payload.inputDevices : [],
          outputDevices: Array.isArray(payload.outputDevices) ? payload.outputDevices : [],
          systemVoices: Array.isArray(payload.systemVoices) ? payload.systemVoices : [],
        };
        topology.routeProfiles = inferRouteProfiles(topology);
        topology.defaultRouteProfileId =
          topology.routeProfiles.find((profile) => profile.status === "ready")?.id || "browser-debug";
        resolve(topology);
      } catch {
        reject(new Error("Device topology probe did not return valid JSON."));
      }
    });
  });
}

function listAudioRoutingOptions(config = getCoreConfig()) {
  return listDeviceTopology(config).then((topology) => ({
    outputDevices: topology.outputDevices,
    inputDevices: topology.inputDevices,
    voices: topology.systemVoices,
    routeProfiles: topology.routeProfiles,
    defaultOutputDeviceName: config.ttsOutputDeviceName || topology.outputDevices[0]?.name || "",
    defaultInputDeviceName: topology.inputDevices[0]?.name || "",
    defaultVoiceName: config.ttsVoiceName || topology.systemVoices[0]?.name || "alloy",
    defaultRouteProfileId: topology.defaultRouteProfileId,
  }));
}

module.exports = {
  listAudioRoutingOptions,
  listDeviceTopology,
};
