function inferRouteProfiles(topology = {}) {
  const inputDevices = Array.isArray(topology.inputDevices) ? topology.inputDevices : [];
  const outputDevices = Array.isArray(topology.outputDevices) ? topology.outputDevices : [];
  const inputNames = new Set(inputDevices.map((device) => device.name.toLowerCase()));
  const outputNames = new Set(outputDevices.map((device) => device.name.toLowerCase()));

  const profiles = [
    {
      id: "browser-debug",
      label: "Browser Debug Harness",
      sessionKind: "browser-debug",
      status: "ready",
      requirements: ["No native device interception required"],
    },
  ];

  if (hasVirtualBus(inputNames, outputNames, "voicemeeter") || hasVirtualBus(inputNames, outputNames, "cable")) {
    profiles.push({
      id: "windows-system-translate",
      label: "Windows Speaker Intercept",
      sessionKind: "system",
      status: "ready",
      requirements: [
        "Windows playback routed into Voicemeeter or VB-CABLE virtual input",
        "Translated audio routed to physical speaker output",
      ],
    });

    profiles.push({
      id: "windows-mic-translate",
      label: "Windows Microphone Translate",
      sessionKind: "microphone",
      status: "ready",
      requirements: [
        "Physical microphone selected as input",
        "Translated audio routed to virtual microphone return",
      ],
    });
  } else {
    profiles.push({
      id: "windows-routing-setup-required",
      label: "Windows Routing Setup Required",
      sessionKind: "microphone",
      status: "needs-setup",
      requirements: [
        "Install Voicemeeter Banana or VB-CABLE",
        "Expose at least one virtual input and one virtual output device",
      ],
    });
  }

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
