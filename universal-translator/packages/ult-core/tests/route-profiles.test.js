const test = require("node:test");
const assert = require("node:assert/strict");

const { inferRouteProfiles } = require("../src/audio-routing/route-profiles");

test("route profile inference marks Windows routing as ready when virtual buses are present", () => {
  const profiles = inferRouteProfiles({
    inputDevices: [{ name: "Microphone" }, { name: "CABLE Output (VB-Audio Virtual Cable)" }],
    outputDevices: [{ name: "Speakers" }, { name: "Voicemeeter Input" }],
  });

  const desktopProfile = profiles.find((profile) => profile.id === "windows-desktop-runtime");
  assert.ok(desktopProfile);
  assert.equal(desktopProfile.supportsMic, true);
  assert.equal(desktopProfile.supportsSpeaker, true);
});
