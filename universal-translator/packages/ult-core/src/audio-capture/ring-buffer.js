const { analyzePcmChunk, computeDurationMs, concatInt16Arrays, toInt16Array, withDuration } = require("../utils/pcm");

class PcmRingBuffer {
  constructor(options = {}) {
    this.sampleRate = Number.isFinite(options.sampleRate) ? options.sampleRate : 16000;
    this.channels = Number.isFinite(options.channels) ? options.channels : 1;
    this.capacityMs = Number.isFinite(options.capacityMs) ? options.capacityMs : 5000;
    this.capacitySamples = this.getSampleCount(this.capacityMs);
    this.buffer = new Int16Array(this.capacitySamples);
    this.writePtr = 0;
    this.totalSamplesWritten = 0;
  }

  write(chunk) {
    const pcmChunk = toInt16Array(chunk);
    if (!pcmChunk.length) {
      return 0;
    }

    for (let index = 0; index < pcmChunk.length; index += 1) {
      this.buffer[this.writePtr] = pcmChunk[index];
      this.writePtr = (this.writePtr + 1) % this.capacitySamples;
    }

    this.totalSamplesWritten += pcmChunk.length;
    return pcmChunk.length;
  }

  availableSamples() {
    return Math.min(this.totalSamplesWritten, this.capacitySamples);
  }

  readLatest(length) {
    const sampleLength = Math.max(0, Math.min(length, this.availableSamples()));
    const output = new Int16Array(sampleLength);
    if (!sampleLength) {
      return output;
    }

    let ptr = (this.writePtr - sampleLength + this.capacitySamples) % this.capacitySamples;
    for (let index = 0; index < sampleLength; index += 1) {
      output[index] = this.buffer[ptr];
      ptr = (ptr + 1) % this.capacitySamples;
    }

    return output;
  }

  getSampleCount(durationMs) {
    return Math.max(1, Math.floor((this.sampleRate * this.channels * durationMs) / 1000));
  }
}

class RollingWindowSegmenter {
  constructor(options = {}) {
    this.sampleRate = Number.isFinite(options.sampleRate) ? options.sampleRate : 16000;
    this.channels = Number.isFinite(options.channels) ? options.channels : 1;
    this.windowMs = Number.isFinite(options.windowMs) ? options.windowMs : 800;
    this.hopMs = Number.isFinite(options.hopMs) ? options.hopMs : 300;
    this.capacityMs = Number.isFinite(options.capacityMs)
      ? options.capacityMs
      : Math.max(this.windowMs * 4, 5000);
    this.silenceThreshold = Number.isFinite(options.silenceThreshold)
      ? options.silenceThreshold
      : 0.008;
    this.speechThreshold = Number.isFinite(options.speechThreshold)
      ? options.speechThreshold
      : 0.014;
    this.skipSilentWindows = Boolean(options.skipSilentWindows);
    this.ring = new PcmRingBuffer({
      sampleRate: this.sampleRate,
      channels: this.channels,
      capacityMs: this.capacityMs,
    });
    this.windowSamples = this.getSampleCount(this.windowMs);
    this.hopSamples = this.getSampleCount(this.hopMs);
    this.lastEmitSample = 0;
    this.sequence = 0;
  }

  push(chunk) {
    this.ring.write(chunk);
    return this.flushReadySegments();
  }

  flush(force = false) {
    if (!force) {
      return this.flushReadySegments();
    }

    if (this.ring.availableSamples() < this.windowSamples) {
      return [];
    }

    const samples = this.ring.readLatest(this.windowSamples);
    const segment = this.buildSegment(samples, "stream-window", this.ring.totalSamplesWritten);
    this.lastEmitSample = this.ring.totalSamplesWritten;
    return this.shouldEmit(segment) ? [segment] : [];
  }

  flushReadySegments() {
    const ready = [];

    while (
      this.ring.availableSamples() >= this.windowSamples &&
      this.ring.totalSamplesWritten - this.lastEmitSample >= this.hopSamples
    ) {
      const endSample = this.lastEmitSample === 0
        ? this.windowSamples
        : this.lastEmitSample + this.hopSamples;
      const boundedEndSample = Math.min(endSample, this.ring.totalSamplesWritten);
      const samples = this.ring.readLatest(this.ring.totalSamplesWritten - boundedEndSample + this.windowSamples);
      const window = samples.slice(samples.length - this.windowSamples);
      const segment = this.buildSegment(window, "stream-window", boundedEndSample);
      this.lastEmitSample = boundedEndSample;
      if (this.shouldEmit(segment)) {
        ready.push(segment);
      }
    }

    return ready;
  }

  shouldEmit(segment) {
    if (!this.skipSilentWindows) {
      return true;
    }

    return (
      segment.analysis.isSpeechLikely ||
      segment.analysis.rms >= this.speechThreshold ||
      segment.analysis.peak >= this.silenceThreshold * 6
    );
  }

  buildSegment(samples, reason, endSample) {
    const durationMs = computeDurationMs(samples.length, this.sampleRate, this.channels);
    const startSample = Math.max(0, endSample - samples.length);
    return {
      segmentId: ++this.sequence,
      pcm: samples,
      reason,
      sampleCount: samples.length,
      durationMs,
      analysis: withDuration(analyzePcmChunk(samples), samples.length, this.sampleRate, this.channels),
      startMs: computeDurationMs(startSample, this.sampleRate, this.channels),
      endMs: computeDurationMs(endSample, this.sampleRate, this.channels),
      isPartial: true,
    };
  }

  getSampleCount(durationMs) {
    return Math.max(1, Math.floor((this.sampleRate * this.channels * durationMs) / 1000));
  }
}

class RollingPcmCommitter {
  constructor(options = {}) {
    this.sampleRate = Number.isFinite(options.sampleRate) ? options.sampleRate : 16000;
    this.channels = Number.isFinite(options.channels) ? options.channels : 1;
    this.minCommitMs = Number.isFinite(options.minCommitMs) ? options.minCommitMs : 600;
    this.maxCommitMs = Number.isFinite(options.maxCommitMs) ? options.maxCommitMs : 1200;
    this.overlapMs = Number.isFinite(options.overlapMs) ? options.overlapMs : 200;
    this.silenceThreshold = Number.isFinite(options.silenceThreshold)
      ? options.silenceThreshold
      : 0.008;
    this.speechFocus = Boolean(options.speechFocus);
    this.speechThreshold = Number.isFinite(options.speechThreshold)
      ? options.speechThreshold
      : 0.018;
    this.speechFrameMs = Number.isFinite(options.speechFrameMs)
      ? options.speechFrameMs
      : 30;
    this.trailingSilenceMs = Number.isFinite(options.trailingSilenceMs)
      ? options.trailingSilenceMs
      : 150;
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
    if (this.speechFocus) {
      return this.flushSpeechFocusedSegments();
    }

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
      // Only break if no overlap AND pending is too small to process again
      if (overlapStart === 0 && this.pending.length < minSamples) {
        break;
      }
    }

    return ready;
  }

  flushSpeechFocusedSegments() {
    const ready = [];
    const minSamples = this.getSampleCount(this.minCommitMs);
    const maxSamples = this.getSampleCount(this.maxCommitMs);
    const overlapSamples = this.getSampleCount(this.overlapMs);
    const frameSamples = this.getSampleCount(this.speechFrameMs);
    const trailingSilenceFrames = Math.max(1, Math.floor(this.trailingSilenceMs / this.speechFrameMs));

    while (this.pending.length >= minSamples) {
      const speechWindow = this.findSpeechWindow({
        minSamples,
        maxSamples,
        frameSamples,
        trailingSilenceFrames,
      });

      if (!speechWindow) {
        if (this.pending.length < maxSamples) {
          break;
        }

        const segment = this.pending.slice(0, maxSamples);
        const payload = this.buildSegment(segment, "window-max");
        if (payload.analysis.isSpeechLikely || payload.analysis.rms >= this.speechThreshold) {
          ready.push(payload);
        }
        this.pending = this.pending.slice(Math.max(0, maxSamples - overlapSamples));
        continue;
      }

      const splitAt = Math.min(this.pending.length, speechWindow.endSample);
      const segment = this.pending.slice(0, splitAt);
      ready.push(this.buildSegment(segment, speechWindow.reason));

      const overlapStart = Math.max(0, splitAt - overlapSamples);
      this.pending = this.pending.slice(overlapStart);
      if (overlapStart === 0 && this.pending.length < minSamples) {
        break;
      }
    }

    return ready;
  }

  findSpeechWindow({ minSamples, maxSamples, frameSamples, trailingSilenceFrames }) {
    let speechStarted = false;
    let speechStartSample = 0;
    let silenceFrames = 0;

    for (let cursor = 0; cursor + frameSamples <= this.pending.length; cursor += frameSamples) {
      const frame = this.pending.slice(cursor, cursor + frameSamples);
      const analysis = analyzePcmChunk(frame);
      const isSpeechFrame =
        analysis.isSpeechLikely ||
        analysis.rms >= this.speechThreshold ||
        (analysis.rms >= this.silenceThreshold * 2 && analysis.zeroCrossingRate >= 0.03);

      if (!speechStarted) {
        if (isSpeechFrame) {
          speechStarted = true;
          speechStartSample = cursor;
          silenceFrames = 0;
        }
        continue;
      }

      if (isSpeechFrame) {
        silenceFrames = 0;
      } else {
        silenceFrames += 1;
      }

      const currentLength = cursor + frameSamples - speechStartSample;
      if (currentLength >= maxSamples) {
        return {
          endSample: speechStartSample + maxSamples,
          reason: "speech-window",
        };
      }

      if (currentLength >= minSamples && silenceFrames >= trailingSilenceFrames) {
        return {
          endSample: cursor + frameSamples,
          reason: "speech-window",
        };
      }
    }

    if (speechStarted && this.pending.length - speechStartSample >= maxSamples) {
      return {
        endSample: speechStartSample + maxSamples,
        reason: "speech-window",
      };
    }

    return null;
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
  PcmRingBuffer,
  RollingWindowSegmenter,
  RollingPcmCommitter,
};
