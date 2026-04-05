const { analyzePcmChunk, computeDurationMs, concatInt16Arrays, toInt16Array, withDuration } = require("../utils/pcm");

class RollingPcmCommitter {
  constructor(options = {}) {
    this.sampleRate = Number.isFinite(options.sampleRate) ? options.sampleRate : 16000;
    this.channels = Number.isFinite(options.channels) ? options.channels : 1;
    this.minCommitMs = Number.isFinite(options.minCommitMs) ? options.minCommitMs : 600;
    this.maxCommitMs = Number.isFinite(options.maxCommitMs) ? options.maxCommitMs : 1200;
    this.overlapMs = Number.isFinite(options.overlapMs) ? options.overlapMs : 200;
    this.silenceThreshold = Number.isFinite(options.silenceThreshold)
      ? options.silenceThreshold
      : 0.012;
    this.pending = new Int16Array(0);
  }

  push(chunk) {
    const pcmChunk = toInt16Array(chunk);
    if (!pcmChunk.length) {
      return [];
    }

    this.pending = concatInt16Arrays([this.pending, pcmChunk]);
    return this.flushReadySegments();
  }

  flush(force = false) {
    if (!this.pending.length) {
      return [];
    }

    if (!force) {
      return this.flushReadySegments();
    }

    const payload = this.buildSegment(this.pending, "forced-flush");
    this.pending = new Int16Array(0);
    return [payload];
  }

  flushReadySegments() {
    const ready = [];
    const minSamples = this.getSampleCount(this.minCommitMs);
    const maxSamples = this.getSampleCount(this.maxCommitMs);
    const overlapSamples = this.getSampleCount(this.overlapMs);

    while (this.pending.length >= minSamples) {
      let splitAt = 0;
      let reason = "window-max";

      if (this.pending.length >= maxSamples) {
        splitAt = maxSamples;
      } else {
        splitAt = this.findSilenceSplit(minSamples, this.pending.length);
        reason = "vad-silence";
      }

      if (!splitAt) {
        break;
      }

      const segment = this.pending.slice(0, splitAt);
      ready.push(this.buildSegment(segment, reason));

      const overlapStart = Math.max(0, splitAt - overlapSamples);
      this.pending = this.pending.slice(overlapStart);
      if (overlapStart === 0) {
        break;
      }
    }

    return ready;
  }

  findSilenceSplit(minSamples, maxSamples) {
    const windowSize = this.getSampleCount(120);
    let bestSplit = 0;

    for (let cursor = minSamples; cursor <= maxSamples; cursor += windowSize) {
      const windowStart = Math.max(0, cursor - windowSize);
      const window = this.pending.slice(windowStart, cursor);
      const analysis = analyzePcmChunk(window);
      if (analysis.rms <= this.silenceThreshold) {
        bestSplit = cursor;
      }
    }

    return bestSplit;
  }

  buildSegment(samples, reason) {
    const analysis = withDuration(
      analyzePcmChunk(samples),
      samples.length,
      this.sampleRate,
      this.channels
    );

    return {
      pcm: samples,
      reason,
      sampleCount: samples.length,
      durationMs: computeDurationMs(samples.length, this.sampleRate, this.channels),
      analysis,
    };
  }

  getSampleCount(durationMs) {
    return Math.max(1, Math.floor((this.sampleRate * this.channels * durationMs) / 1000));
  }
}

module.exports = {
  RollingPcmCommitter,
};
