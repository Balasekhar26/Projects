function toInt16Array(value) {
  if (value instanceof Int16Array) {
    return value;
  }

  if (Buffer.isBuffer(value)) {
    return new Int16Array(value.buffer, value.byteOffset, Math.floor(value.byteLength / 2));
  }

  if (value instanceof ArrayBuffer) {
    return new Int16Array(value);
  }

  if (ArrayBuffer.isView(value)) {
    return new Int16Array(value.buffer, value.byteOffset, Math.floor(value.byteLength / 2));
  }

  return new Int16Array(0);
}

function cloneInt16Array(value) {
  const view = toInt16Array(value);
  return new Int16Array(view);
}

function concatInt16Arrays(chunks) {
  const normalized = chunks.map(toInt16Array);
  const totalLength = normalized.reduce((sum, chunk) => sum + chunk.length, 0);
  const merged = new Int16Array(totalLength);
  let offset = 0;

  for (const chunk of normalized) {
    merged.set(chunk, offset);
    offset += chunk.length;
  }

  return merged;
}

function analyzePcmChunk(input) {
  const chunk = toInt16Array(input);
  if (!chunk.length) {
    return {
      rms: 0,
      peak: 0,
      zeroCrossingRate: 0,
      durationMs: 0,
      isSpeechLikely: false,
    };
  }

  let sumSquares = 0;
  let peak = 0;
  let zeroCrossings = 0;

  for (let index = 0; index < chunk.length; index += 1) {
    const normalized = chunk[index] / 32768;
    sumSquares += normalized * normalized;
    peak = Math.max(peak, Math.abs(normalized));

    if (index > 0) {
      const previous = chunk[index - 1];
      const current = chunk[index];
      if ((previous >= 0 && current < 0) || (previous < 0 && current >= 0)) {
        zeroCrossings += 1;
      }
    }
  }

  const rms = Math.sqrt(sumSquares / chunk.length);
  const zeroCrossingRate = zeroCrossings / chunk.length;

  return {
    rms,
    peak,
    zeroCrossingRate,
    durationMs: 0,
    isSpeechLikely: rms >= 0.012 || peak >= 0.12,
  };
}

function computeDurationMs(sampleCount, sampleRate = 16000, channels = 1) {
  if (!sampleCount || !sampleRate || !channels) {
    return 0;
  }

  return Math.round((sampleCount / (sampleRate * channels)) * 1000);
}

function withDuration(analysis, sampleCount, sampleRate, channels) {
  return {
    ...analysis,
    durationMs: computeDurationMs(sampleCount, sampleRate, channels),
  };
}

module.exports = {
  analyzePcmChunk,
  cloneInt16Array,
  computeDurationMs,
  concatInt16Arrays,
  toInt16Array,
  withDuration,
};
