module.exports = {
  ...require("./src/contracts"),
  ...require("./src/config"),
  ...require("./src/catalog/languages"),
  ...require("./src/catalog/model-packs"),
  ...require("./src/device-control/topology"),
  ...require("./src/audio-routing/route-profiles"),
  ...require("./src/installer/bootstrap"),
  ...require("./src/installer/provisioning"),
  ...require("./src/session/session-store"),
  ...require("./src/voice-clone/registry"),
};
