function validateRouteProfile({ request, topology }) {
  const routeProfiles = Array.isArray(topology?.routeProfiles) ? topology.routeProfiles : [];
  const profile = routeProfiles.find((entry) => entry.id === request.routeProfileId) || null;
  const inputDevices = Array.isArray(topology?.inputDevices) ? topology.inputDevices : [];
  const outputDevices = Array.isArray(topology?.outputDevices) ? topology.outputDevices : [];

  const diagnostics = [];
  const result = {
    ok: true,
    profile,
    diagnostics,
    supportsMic: true,
    supportsSpeaker: true,
    validatedAt: new Date().toISOString(),
  };

  if (profile && profile.status !== "ready") {
    diagnostics.push(`Route profile ${profile.id} is ${profile.status}.`);
    result.ok = false;
  }

  if (request.sessionKind === "desktop_runtime") {
    if (!hasVirtualMic(inputDevices)) {
      diagnostics.push("A virtual microphone device is required for fail-closed desktop routing.");
      result.ok = false;
      result.supportsMic = false;
    }

    if (!hasVirtualSpeakerBus(inputDevices, outputDevices)) {
      diagnostics.push("A virtual speaker bus is required for fail-closed desktop speaker interception.");
      result.ok = false;
      result.supportsSpeaker = false;
    }
  }

  if (request.platform === "android" && request.sessionKind === "android_runtime") {
    result.supportsSpeaker = false;
    diagnostics.push("Android speaker interception is capability-gated and may be unavailable on this device.");
  }

  return result;
}

function hasVirtualMic(inputDevices) {
  return inputDevices.some((device) => /virtual|cable output|voicemeeter output|line 1/i.test(device.name));
}

function hasVirtualSpeakerBus(inputDevices, outputDevices) {
  return [...inputDevices, ...outputDevices].some((device) => /cable|voicemeeter|line 1/i.test(device.name));
}

module.exports = {
  validateRouteProfile,
};
