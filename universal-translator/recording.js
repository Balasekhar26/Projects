const fs = require("fs");
const record = require("node-record-lpcm16");

const outputFile = "system-audio.wav";
const fileStream = fs.createWriteStream(outputFile, { encoding: "binary" });

const recognitionStream = getSpeechRecognitionStream();

const recording = record.record({
  sampleRate: 16000,
  channels: 2,
  threshold: 0,
  recordProgram: "sox", // on Windows use sox
  device: "CABLE Output (VB-Audio Virtual Cable)", // your capture device name
  audioType: "wav",
});

recording.stream().pipe(fileStream);
recording.stream().pipe(recognitionStream);

console.log("Recording system audio to", outputFile);

setTimeout(() => {
  recording.stop();
  console.log("Stopped recording");
}, 10000);