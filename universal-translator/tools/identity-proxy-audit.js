const fs = require("fs");
const path = require("path");
const {
  extractVoiceIdentityFromChunk,
} = require("../packages/ult-core/src/voice-identity/profile");
const { analyzePcmChunk } = require("../packages/ult-core/src/utils/pcm");

async function main() {
  const inputPaths = process.argv.slice(2);
  if (!inputPaths.length) {
    console.error("Usage: node tools/identity-proxy-audit.js <wav-file> [more-wav-files]");
    process.exit(1);
  }

  const expanded = inputPaths.flatMap(expandInput).filter(Boolean);
  if (!expanded.length) {
    console.error("No matching WAV files found.");
    process.exit(1);
  }

  const analyses = expanded.map((filePath) => analyzeFile(filePath));
  const combined = combineAnalyses(analyses);

  console.log("Proxy audit");
  console.log(`files: ${expanded.length}`);
  console.log(`duration: ${combined.durationSeconds.toFixed(2)}s`);
  console.log(`pitch drift: ${combined.pitchDriftPercent.toFixed(1)}%`);
  console.log(`formant variation: F1 ${combined.formantVariation.f1.toFixed(1)}%, F2 ${combined.formantVariation.f2.toFixed(1)}%`);
  console.log(`energy max jump: ${combined.maxEnergyJumpDb.toFixed(2)} dB`);
  console.log(`tempo drift: ${combined.tempoDriftPercent.toFixed(1)}%`);
  console.log(`spectral tilt drift: ${combined.spectralTiltDriftPercent.toFixed(1)}%`);
  console.log("");
  console.log("```text id=\"identity_proxy_pass\"");
  console.log(`identity match | ${combined.identityLabel} | ${combined.identityScore}`);
  console.log(`drift stability | ${combined.driftLabel} | ${combined.driftScore}`);
  console.log(`color naturalness | ${combined.colorLabel} | ${combined.colorScore}`);
  console.log("```");
}

function analyzeFile(filePath) {
  const wav = readWaveFile(filePath);
  const mono = toMonoInt16(wav.samples, wav.channels);
  const windowMs = 1000;
  const hopMs = 500;
  const windowSamples = Math.max(1, Math.floor((wav.sampleRate * windowMs) / 1000));
  const hopSamples = Math.max(1, Math.floor((wav.sampleRate * hopMs) / 1000));
  const windows = [];

  for (let start = 0; start + windowSamples <= mono.length; start += hopSamples) {
    const segment = mono.slice(start, start + windowSamples);
    const pcmBuffer = Buffer.from(segment.buffer, segment.byteOffset, segment.byteLength);
    const analysis = analyzePcmChunk(segment);
    const identity = extractVoiceIdentityFromChunk(
      {
        pcmBuffer,
        analysis,
        durationMs: (segment.length / wav.sampleRate) * 1000,
      },
      { sampleRate: wav.sampleRate, channels: 1 }
    );

    const tilt = computeSpectralTilt(segment, wav.sampleRate);
    windows.push({
      startSeconds: start / wav.sampleRate,
      durationSeconds: segment.length / wav.sampleRate,
      rms: analysis.rms,
      energyDb: rmsToDb(analysis.rms),
      identity,
      tilt,
    });
  }

  return {
    filePath,
    durationSeconds: mono.length / wav.sampleRate,
    windows: windows.filter((entry) => entry.identity),
  };
}

function combineAnalyses(analyses) {
  const windows = analyses.flatMap((entry) => entry.windows);
  if (!windows.length) {
    throw new Error("No analyzable voiced windows were found in the provided WAV files.");
  }

  const f0Values = windows.map((entry) => entry.identity.f0Mean).filter(Number.isFinite);
  const tempoValues = windows.map((entry) => entry.identity.tempo).filter(Number.isFinite);
  const f1Values = windows.map((entry) => entry.identity.formants[0]).filter(Number.isFinite);
  const f2Values = windows.map((entry) => entry.identity.formants[1]).filter(Number.isFinite);
  const tiltValues = windows.map((entry) => entry.tilt).filter(Number.isFinite);
  const energyDbValues = windows.map((entry) => entry.energyDb).filter(Number.isFinite);

  const pitchDriftPercent = relativeDriftPercent(f0Values);
  const tempoDriftPercent = relativeDriftPercent(tempoValues);
  const formantVariation = {
    f1: coefficientOfVariationPercent(f1Values),
    f2: coefficientOfVariationPercent(f2Values),
  };
  const spectralTiltDriftPercent = coefficientOfVariationPercent(tiltValues.map((value) => Math.abs(value)));
  const maxEnergyJumpDb = maxAdjacentDelta(energyDbValues);

  const identityScore = scoreIdentity({
    pitchDriftPercent,
    formantVariation,
  });
  const driftScore = scoreDrift({
    pitchDriftPercent,
    tempoDriftPercent,
  });
  const colorScore = scoreColor({
    maxEnergyJumpDb,
    spectralTiltDriftPercent,
    formantVariation,
  });

  return {
    durationSeconds: analyses.reduce((sum, entry) => sum + entry.durationSeconds, 0),
    pitchDriftPercent,
    tempoDriftPercent,
    formantVariation,
    spectralTiltDriftPercent,
    maxEnergyJumpDb,
    identityScore,
    driftScore,
    colorScore,
    identityLabel: scoreToIdentityLabel(identityScore),
    driftLabel: scoreToDriftLabel(driftScore),
    colorLabel: scoreToColorLabel(colorScore),
  };
}

function scoreIdentity({ pitchDriftPercent, formantVariation }) {
  const worstFormant = Math.max(formantVariation.f1, formantVariation.f2);
  if (pitchDriftPercent <= 8 && worstFormant <= 10) return 5;
  if (pitchDriftPercent <= 10 && worstFormant <= 13) return 4;
  if (pitchDriftPercent <= 12 && worstFormant <= 15) return 3;
  if (pitchDriftPercent <= 16 && worstFormant <= 20) return 2;
  return 1;
}

function scoreDrift({ pitchDriftPercent, tempoDriftPercent }) {
  const worst = Math.max(pitchDriftPercent, tempoDriftPercent);
  if (worst <= 8) return 5;
  if (worst <= 10) return 4;
  if (worst <= 12) return 3;
  if (worst <= 16) return 2;
  return 1;
}

function scoreColor({ maxEnergyJumpDb, spectralTiltDriftPercent, formantVariation }) {
  const worstFormant = Math.max(formantVariation.f1, formantVariation.f2);
  if (maxEnergyJumpDb <= 4 && spectralTiltDriftPercent <= 10 && worstFormant <= 12) return 5;
  if (maxEnergyJumpDb <= 6 && spectralTiltDriftPercent <= 14 && worstFormant <= 15) return 4;
  if (maxEnergyJumpDb <= 8 && spectralTiltDriftPercent <= 18 && worstFormant <= 18) return 3;
  if (maxEnergyJumpDb <= 10 && spectralTiltDriftPercent <= 24) return 2;
  return 1;
}

function scoreToIdentityLabel(score) {
  if (score >= 5) return "proxy-stable";
  if (score >= 3) return "proxy-stable with minor deviation";
  return "proxy-unstable";
}

function scoreToDriftLabel(score) {
  if (score >= 5) return "stable";
  if (score >= 3) return "slight drift";
  return "drifting";
}

function scoreToColorLabel(score) {
  if (score >= 5) return "natural";
  if (score >= 3) return "slightly processed";
  return "processed";
}

function readWaveFile(filePath) {
  const buffer = fs.readFileSync(filePath);
  if (buffer.toString("ascii", 0, 4) !== "RIFF" || buffer.toString("ascii", 8, 12) !== "WAVE") {
    throw new Error(`${filePath} is not a PCM WAV file.`);
  }

  let offset = 12;
  let channels = 1;
  let sampleRate = 16000;
  let bitsPerSample = 16;
  let dataOffset = -1;
  let dataSize = 0;

  while (offset + 8 <= buffer.length) {
    const chunkId = buffer.toString("ascii", offset, offset + 4);
    const chunkSize = buffer.readUInt32LE(offset + 4);
    const chunkDataOffset = offset + 8;

    if (chunkId === "fmt ") {
      const audioFormat = buffer.readUInt16LE(chunkDataOffset);
      channels = buffer.readUInt16LE(chunkDataOffset + 2);
      sampleRate = buffer.readUInt32LE(chunkDataOffset + 4);
      bitsPerSample = buffer.readUInt16LE(chunkDataOffset + 14);
      if (audioFormat !== 1) {
        throw new Error(`${filePath} must be PCM WAV (format 1).`);
      }
    } else if (chunkId === "data") {
      dataOffset = chunkDataOffset;
      dataSize = chunkSize;
      break;
    }

    offset = chunkDataOffset + chunkSize + (chunkSize % 2);
  }

  if (dataOffset < 0) {
    throw new Error(`${filePath} does not contain a data chunk.`);
  }
  if (bitsPerSample !== 16) {
    throw new Error(`${filePath} must be 16-bit PCM for this audit.`);
  }

  const sampleCount = Math.floor(dataSize / 2);
  const samples = new Int16Array(sampleCount);
  for (let index = 0; index < sampleCount; index += 1) {
    samples[index] = buffer.readInt16LE(dataOffset + (index * 2));
  }

  return {
    channels,
    sampleRate,
    samples,
  };
}

function toMonoInt16(samples, channels) {
  if (channels <= 1) {
    return new Int16Array(samples);
  }

  const frameCount = Math.floor(samples.length / channels);
  const mono = new Int16Array(frameCount);
  for (let frame = 0; frame < frameCount; frame += 1) {
    let total = 0;
    for (let channel = 0; channel < channels; channel += 1) {
      total += samples[(frame * channels) + channel];
    }
    mono[frame] = Math.round(total / channels);
  }
  return mono;
}

function computeSpectralTilt(samples, sampleRate) {
  const low = goertzelBandPower(samples, sampleRate, [250, 500, 1000]);
  const high = goertzelBandPower(samples, sampleRate, [2000, 3000, 4000]);
  return (low + 1e-9) / (high + 1e-9);
}

function goertzelBandPower(samples, sampleRate, frequencies) {
  return frequencies.reduce((sum, frequency) => sum + goertzelPower(samples, sampleRate, frequency), 0);
}

function goertzelPower(samples, sampleRate, frequency) {
  const omega = (2 * Math.PI * frequency) / sampleRate;
  const coeff = 2 * Math.cos(omega);
  let q0 = 0;
  let q1 = 0;
  let q2 = 0;

  for (let index = 0; index < samples.length; index += 1) {
    q0 = coeff * q1 - q2 + (samples[index] / 32768);
    q2 = q1;
    q1 = q0;
  }

  return (q1 * q1) + (q2 * q2) - (coeff * q1 * q2);
}

function rmsToDb(rms) {
  return 20 * Math.log10(Math.max(rms, 1e-9));
}

function maxAdjacentDelta(values) {
  let maxDelta = 0;
  for (let index = 1; index < values.length; index += 1) {
    maxDelta = Math.max(maxDelta, Math.abs(values[index] - values[index - 1]));
  }
  return maxDelta;
}

function relativeDriftPercent(values) {
  if (!values.length) {
    return 100;
  }
  const center = median(values);
  const maxDeviation = Math.max(...values.map((value) => Math.abs(value - center)));
  return (maxDeviation / Math.max(Math.abs(center), 1e-6)) * 100;
}

function coefficientOfVariationPercent(values) {
  if (!values.length) {
    return 100;
  }
  const avg = average(values);
  const variance = average(values.map((value) => (value - avg) ** 2));
  const stddev = Math.sqrt(variance);
  return (stddev / Math.max(Math.abs(avg), 1e-6)) * 100;
}

function average(values) {
  return values.reduce((sum, value) => sum + value, 0) / Math.max(values.length, 1);
}

function median(values) {
  const sorted = [...values].sort((a, b) => a - b);
  const middle = Math.floor(sorted.length / 2);
  if (sorted.length % 2 === 0) {
    return (sorted[middle - 1] + sorted[middle]) / 2;
  }
  return sorted[middle];
}

function expandInput(inputPath) {
  const resolved = path.resolve(process.cwd(), inputPath);
  if (fs.existsSync(resolved) && fs.statSync(resolved).isFile()) {
    return [resolved];
  }

  const directory = path.dirname(resolved);
  const pattern = wildcardToRegExp(path.basename(resolved));
  if (!fs.existsSync(directory)) {
    return [];
  }

  return fs.readdirSync(directory)
    .filter((entry) => pattern.test(entry))
    .map((entry) => path.join(directory, entry));
}

function wildcardToRegExp(pattern) {
  const escaped = pattern.replace(/[.+^${}()|[\]\\]/g, "\\$&").replace(/\*/g, ".*").replace(/\?/g, ".");
  return new RegExp(`^${escaped}$`, "i");
}

main().catch((error) => {
  console.error("[fatal]", error.message);
  process.exit(1);
});
