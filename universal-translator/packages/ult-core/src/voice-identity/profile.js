const { analyzePcmChunk, toInt16Array } = require("../utils/pcm");

function extractVoiceIdentityFromChunk(chunk, options = {}) {
  const sampleRate = Number.isFinite(options.sampleRate) ? options.sampleRate : 16000;
  const channels = Number.isFinite(options.channels) ? options.channels : 1;
  const pcm = toMonoPcm(chunk?.pcmBuffer || chunk?.pcm || chunk, channels);
  const analysis = chunk?.analysis && typeof chunk.analysis === "object"
    ? chunk.analysis
    : analyzePcmChunk(pcm);

  if (!pcm.length || (!analysis.isSpeechLikely && finiteOr(analysis.rms, 0) < 0.01)) {
    return null;
  }

  const window = pcm.length > sampleRate * 1.2 ? pcm.slice(pcm.length - Math.floor(sampleRate * 1.2)) : pcm;
  const frameSize = Math.max(240, Math.floor(sampleRate * 0.03));
  const hopSize = Math.max(120, Math.floor(sampleRate * 0.015));
  const frameMetrics = collectFrameMetrics(window, sampleRate, frameSize, hopSize);
  const voicedPitches = frameMetrics.filter((frame) => frame.pitch > 0).map((frame) => frame.pitch);
  const pitchFallback = clamp((finiteOr(analysis.zeroCrossingRate, 0.08) * sampleRate) / 8, 85, 240);
  const f0Mean = voicedPitches.length ? average(voicedPitches) : pitchFallback;
  const f0Range = voicedPitches.length > 1
    ? clamp((Math.max(...voicedPitches) - Math.min(...voicedPitches)), 20, 220)
    : clamp(f0Mean * 0.18, 18, 60);

  const formantProfile = estimateFormantProfile(window, sampleRate);
  const speakingRate = estimateSpeakingRate(frameMetrics, window.length / sampleRate);
  const tempo = clamp(0.92 + ((speakingRate - 2.4) * 0.03), 0.9, 1.08);
  const energy = clamp(finiteOr(analysis.rms, average(frameMetrics.map((frame) => frame.energy))), 0, 1);
  const tilt = clamp(
    (((formantProfile.highEnergy - formantProfile.lowEnergy) / Math.max(0.0001, formantProfile.highEnergy + formantProfile.lowEnergy)) * 0.7) +
      ((finiteOr(analysis.zeroCrossingRate, 0.08) - 0.08) * 2.2),
    -1,
    1
  );
  const voicedRatio = frameMetrics.length
    ? frameMetrics.filter((frame) => frame.energy >= 0.02).length / frameMetrics.length
    : 0.5;
  const cadence = clamp((1 - Math.min(1, speakingRate / 6)) * 0.55 + (voicedRatio * 0.35), 0.2, 0.85);

  return {
    f0Mean: round(f0Mean, 2),
    f0Range: round(f0Range, 2),
    formants: formantProfile.formants.map((value) => round(value, 2)),
    tempo: round(tempo, 3),
    energy: round(energy, 4),
    tilt: round(tilt, 3),
    cadence: round(cadence, 3),
  };
}

function blendVoiceIdentityProfiles(previous, next, amount = 0.15) {
  if (!next) {
    return previous || null;
  }
  if (!previous) {
    return cloneProfile(next);
  }

  const blend = clamp(finiteOr(amount, 0.15), 0.01, 1);
  const previousFormants = normalizeFormants(previous.formants);
  const nextFormants = normalizeFormants(next.formants);

  return {
    f0Mean: round(lerp(finiteOr(previous.f0Mean, next.f0Mean), finiteOr(next.f0Mean, previous.f0Mean), blend), 2),
    f0Range: round(lerp(finiteOr(previous.f0Range, next.f0Range), finiteOr(next.f0Range, previous.f0Range), blend), 2),
    formants: previousFormants.map((value, index) => round(lerp(value, nextFormants[index], blend), 2)),
    tempo: round(lerp(finiteOr(previous.tempo, next.tempo), finiteOr(next.tempo, previous.tempo), blend), 3),
    energy: round(lerp(finiteOr(previous.energy, next.energy), finiteOr(next.energy, previous.energy), blend), 4),
    tilt: round(lerp(finiteOr(previous.tilt, next.tilt), finiteOr(next.tilt, previous.tilt), blend), 3),
    cadence: round(lerp(finiteOr(previous.cadence, next.cadence), finiteOr(next.cadence, previous.cadence), blend), 3),
  };
}

function aggregateVoiceIdentityProfiles(entries = []) {
  if (!Array.isArray(entries) || !entries.length) {
    return null;
  }

  let totalWeight = 0;
  const aggregate = {
    f0Mean: 0,
    f0Range: 0,
    tempo: 0,
    energy: 0,
    tilt: 0,
    cadence: 0,
    formants: [0, 0, 0],
  };

  for (const entry of entries) {
    const profile = entry?.profile;
    if (!profile) {
      continue;
    }

    const weight = clamp(
      finiteOr(entry.weight, 0) ||
        Math.max(0.2, finiteOr(entry.durationMs, 0) / 1000) *
        Math.max(0.4, finiteOr(profile.energy, 0.04) * 8),
      0.1,
      6
    );
    const formants = normalizeFormants(profile.formants);

    totalWeight += weight;
    aggregate.f0Mean += finiteOr(profile.f0Mean, 0) * weight;
    aggregate.f0Range += finiteOr(profile.f0Range, 0) * weight;
    aggregate.tempo += finiteOr(profile.tempo, 1) * weight;
    aggregate.energy += finiteOr(profile.energy, 0) * weight;
    aggregate.tilt += finiteOr(profile.tilt, 0) * weight;
    aggregate.cadence += finiteOr(profile.cadence, 0.5) * weight;
    aggregate.formants = aggregate.formants.map((value, index) => value + (formants[index] * weight));
  }

  if (!totalWeight) {
    return null;
  }

  return {
    f0Mean: round(aggregate.f0Mean / totalWeight, 2),
    f0Range: round(aggregate.f0Range / totalWeight, 2),
    formants: aggregate.formants.map((value) => round(value / totalWeight, 2)),
    tempo: round(aggregate.tempo / totalWeight, 3),
    energy: round(aggregate.energy / totalWeight, 4),
    tilt: round(aggregate.tilt / totalWeight, 3),
    cadence: round(aggregate.cadence / totalWeight, 3),
  };
}

module.exports = {
  aggregateVoiceIdentityProfiles,
  blendVoiceIdentityProfiles,
  extractVoiceIdentityFromChunk,
};

function collectFrameMetrics(samples, sampleRate, frameSize, hopSize) {
  const frames = [];

  for (let start = 0; start + frameSize <= samples.length; start += hopSize) {
    const frame = samples.slice(start, start + frameSize);
    const analysis = analyzePcmChunk(frame);
    const pitch = analysis.rms >= 0.02 ? estimatePitchAutocorrelation(frame, sampleRate) : 0;
    frames.push({
      energy: analysis.rms,
      pitch,
    });
  }

  return frames;
}

function estimatePitchAutocorrelation(samples, sampleRate, minHz = 85, maxHz = 320) {
  const minLag = Math.max(1, Math.floor(sampleRate / maxHz));
  const maxLag = Math.min(samples.length - 1, Math.floor(sampleRate / minHz));
  if (minLag >= maxLag) {
    return 0;
  }

  let bestLag = 0;
  let bestCorrelation = 0;
  let energy = 0;
  for (let index = 0; index < samples.length; index += 1) {
    energy += samples[index] * samples[index];
  }
  if (!energy) {
    return 0;
  }

  for (let lag = minLag; lag <= maxLag; lag += 1) {
    let correlation = 0;
    for (let index = 0; index + lag < samples.length; index += 1) {
      correlation += samples[index] * samples[index + lag];
    }
    if (correlation > bestCorrelation) {
      bestCorrelation = correlation;
      bestLag = lag;
    }
  }

  if (!bestLag || bestCorrelation / energy < 0.18) {
    return 0;
  }

  return sampleRate / bestLag;
}

function estimateFormantProfile(samples, sampleRate) {
  const truncated = samples.length > 4096 ? samples.slice(samples.length - 4096) : samples;
  const lowCandidates = [300, 450, 600, 750, 900];
  const midCandidates = [1000, 1300, 1600, 1900, 2200, 2500];
  const highCandidates = [2600, 2900, 3200, 3500];

  const low = strongestBand(truncated, sampleRate, lowCandidates);
  const mid = strongestBand(truncated, sampleRate, midCandidates);
  const high = strongestBand(truncated, sampleRate, highCandidates);

  return {
    formants: [low.frequency, mid.frequency, high.frequency],
    lowEnergy: low.power,
    highEnergy: high.power,
  };
}

function strongestBand(samples, sampleRate, candidates) {
  let bestFrequency = candidates[0];
  let bestPower = 0;

  for (const frequency of candidates) {
    const power = goertzelPower(samples, sampleRate, frequency);
    if (power > bestPower) {
      bestPower = power;
      bestFrequency = frequency;
    }
  }

  return {
    frequency: bestFrequency,
    power: bestPower,
  };
}

function goertzelPower(samples, sampleRate, frequency) {
  const normalizedSamples = toInt16Array(samples);
  if (!normalizedSamples.length) {
    return 0;
  }

  const omega = (2 * Math.PI * frequency) / sampleRate;
  const coeff = 2 * Math.cos(omega);
  let q0 = 0;
  let q1 = 0;
  let q2 = 0;

  for (let index = 0; index < normalizedSamples.length; index += 1) {
    q0 = coeff * q1 - q2 + (normalizedSamples[index] / 32768);
    q2 = q1;
    q1 = q0;
  }

  return (q1 * q1) + (q2 * q2) - (coeff * q1 * q2);
}

function estimateSpeakingRate(frameMetrics, durationSeconds) {
  if (!frameMetrics.length || !durationSeconds) {
    return 2.5;
  }

  let transitions = 0;
  let previousVoiced = frameMetrics[0].energy >= 0.02;
  for (let index = 1; index < frameMetrics.length; index += 1) {
    const voiced = frameMetrics[index].energy >= 0.02;
    if (voiced !== previousVoiced) {
      transitions += 1;
    }
    previousVoiced = voiced;
  }

  return clamp((transitions / 2) / durationSeconds, 1.5, 6.5);
}

function toMonoPcm(input, channels) {
  const pcm = toInt16Array(input);
  if (!pcm.length || channels <= 1) {
    return new Int16Array(pcm);
  }

  const frameCount = Math.floor(pcm.length / channels);
  const mono = new Int16Array(frameCount);
  for (let index = 0; index < frameCount; index += 1) {
    let total = 0;
    for (let channel = 0; channel < channels; channel += 1) {
      total += pcm[(index * channels) + channel];
    }
    mono[index] = Math.round(total / channels);
  }
  return mono;
}

function normalizeFormants(formants) {
  const safe = Array.isArray(formants) ? formants : [];
  return [
    finiteOr(safe[0], 500),
    finiteOr(safe[1], 1500),
    finiteOr(safe[2], 2800),
  ];
}

function cloneProfile(profile) {
  return {
    f0Mean: finiteOr(profile.f0Mean, 0),
    f0Range: finiteOr(profile.f0Range, 0),
    formants: normalizeFormants(profile.formants),
    tempo: finiteOr(profile.tempo, 1),
    energy: finiteOr(profile.energy, 0),
    tilt: finiteOr(profile.tilt, 0),
    cadence: finiteOr(profile.cadence, 0.5),
  };
}

function average(values) {
  if (!Array.isArray(values) || !values.length) {
    return 0;
  }
  return values.reduce((sum, value) => sum + finiteOr(value, 0), 0) / values.length;
}

function round(value, digits) {
  const factor = 10 ** digits;
  return Math.round(finiteOr(value, 0) * factor) / factor;
}

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function lerp(a, b, t) {
  return a + ((b - a) * t);
}

function finiteOr(value, fallback = 0) {
  return Number.isFinite(value) ? value : fallback;
}
