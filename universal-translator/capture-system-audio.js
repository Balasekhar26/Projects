const fs = require("fs");
const Mic = require("mic");

// Update this device name if your virtual audio cable has a different label.
const deviceName = "CABLE Output (VB-Audio Virtual Cable)";
const outputFile = "system-audio.wav";

const micInstance = Mic({
  rate: "16000",
  channels: "2",
  bitwidth: "16",
  encoding: "signed-integer",
  device: deviceName,
  format: "wav",
  debug: false,
});

const micInputStream = micInstance.getAudioStream();
const outputFileStream = fs.createWriteStream(outputFile);

micInputStream.on("error", (err) => {
  console.error("Audio capture error:", err);
  if (err && err.code === "ENOENT") {
    console.error("It looks like SoX is not installed or not on your PATH. Install SoX and retry.");
  }
  process.exit(1);
});

outputFileStream.on("error", (err) => {
  console.error("File write error:", err);
});

console.log(`Starting system audio capture from device: ${deviceName}`);
console.log(`Saving to: ${outputFile}`);

micInputStream.pipe(outputFileStream);
micInstance.start();

process.on("SIGINT", () => {
  console.log("\nStopping recording...");
  micInstance.stop();
  outputFileStream.end(() => {
    console.log("Recording saved.");
    process.exit(0);
  });
});

setTimeout(() => {
  console.log("Stopping recording after 10 seconds...");
  micInstance.stop();
  outputFileStream.end(() => {
    console.log("Recording saved.");
    process.exit(0);
  });
}, 10000);
