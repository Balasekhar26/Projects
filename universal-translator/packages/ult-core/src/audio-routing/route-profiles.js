function inferRouteProfiles(topology = {}) {
  const inputDevices = Array.isArray(topology.inputDevices) ? topology.inputDevices : [];
  const outputDevices = Array.isArray(topology.outputDevices) ? topology.outputDevices : [];
  const inputNames = new Set(inputDevices.map((device) => device.name.toLowerCase()));
  const outputNames = new Set(outputDevices.map((device) => device.name.toLowerCase()));
  const virtualRoutingReady =
    hasVirtualBus(inputNames, outputNames, "voicemeeter") ||
    hasVirtualBus(inputNames, outputNames, "cable") ||
    hasVirtualBus(inputNames, outputNames, "line 1");

  const profiles = [
    {
      id: "browser-debug",
      label: "Browser Debug Harness",
      sessionKind: "browser_debug",
      platform: "cross-platform",
      status: "ready",
      requiredDevices: [],
      supportsMic: true,
      supportsSpeaker: false,
      requirements: ["No native device interception required"],
      validatedAt: new Date().toISOString(),
    },
  ];

  if (virtualRoutingReady) {
    profiles.push({
      id: "windows-desktop-runtime",
      label: "Windows Fail-Closed Desktop Runtime",
      sessionKind: "desktop_runtime",
      platform: "windows",
      status: "ready",
      requiredDevices: [
        "Physical microphone",
        "Physical speaker",
        "Virtual microphone return",
        "Virtual speaker bus",
      ],
      supportsMic: true,
      supportsSpeaker: true,
      requirements: [
        "Capture physical mic into ULT and inject translated speech into a virtual microphone",
        "Capture speaker path through virtual bus and keep original physical endpoint silent while ULT is active",
      ],
      validatedAt: new Date().toISOString(),
    });
  } else {
    profiles.push({
      id: "windows-routing-setup-required",
      label: "Windows Routing Setup Required",
      sessionKind: "desktop_runtime",
      platform: "windows",
      status: "needs-setup",
      requiredDevices: ["Virtual microphone return", "Virtual speaker bus"],
      supportsMic: false,
      supportsSpeaker: false,
      requirements: [
        "Install VB-CABLE or Voicemeeter",
        "Expose at least one virtual input and one virtual output device",
      ],
      validatedAt: new Date().toISOString(),
    });
  }

  profiles.push({
    id: "android-runtime",
    label: "Android Runtime",
    sessionKind: "android_runtime",
    platform: "android",
    status: "limited",
    requiredDevices: ["Microphone permission", "Foreground service", "MediaProjection for speaker capture"],
    supportsMic: true,
    supportsSpeaker: false,
    requirements: [
      "Microphone translation is required",
      "Speaker translation is capability-gated by Android MediaProjection support",
    ],
    validatedAt: new Date().toISOString(),
  });

  return profiles;
}

function hasVirtualBus(inputNames, outputNames, token) {
  for (const name of [...inputNames, ...outputNames]) {
    if (name.includes(token)) {
      return true;
    }
  }

  return false;
}

module.exports = {
  inferRouteProfiles,
};
