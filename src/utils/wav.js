const fs = require("fs/promises");

function createWavHeader({
  pcmByteLength,
  sampleRate,
  channels,
  bitsPerSample,
}) {
  const blockAlign = (channels * bitsPerSample) / 8;
  const byteRate = sampleRate * blockAlign;
  const header = Buffer.alloc(44);

  header.write("RIFF", 0);
  header.writeUInt32LE(36 + pcmByteLength, 4);
  header.write("WAVE", 8);
  header.write("fmt ", 12);
  header.writeUInt32LE(16, 16);
  header.writeUInt16LE(1, 20);
  header.writeUInt16LE(channels, 22);
  header.writeUInt32LE(sampleRate, 24);
  header.writeUInt32LE(byteRate, 28);
  header.writeUInt16LE(blockAlign, 32);
  header.writeUInt16LE(bitsPerSample, 34);
  header.write("data", 36);
  header.writeUInt32LE(pcmByteLength, 40);

  return header;
}

async function writePcmAsWavFile(filePath, pcmBuffer, options) {
  const header = createWavHeader({
    pcmByteLength: pcmBuffer.length,
    sampleRate: options.sampleRate,
    channels: options.channels,
    bitsPerSample: options.bitsPerSample,
  });

  await fs.writeFile(filePath, Buffer.concat([header, pcmBuffer]));
}

module.exports = {
  writePcmAsWavFile,
};
