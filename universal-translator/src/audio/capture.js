const { EventEmitter } = require("events");
const { spawn } = require("child_process");
const { RollingPcmCommitter, RollingWindowSegmenter } = require("../../packages/ult-core/src/audio-capture/ring-buffer");

class VirtualAudioCapture extends EventEmitter {
  constructor(config) {
    super();
    this.config = config;
    this.process = null;
    this.isRunning = false;
    this.committer = this.createCommitter();
  }

  createCommitter() {
    if (this.config.streamingSegmenter) {
      return new RollingWindowSegmenter({
        sampleRate: this.config.sampleRate,
        channels: this.config.channels,
        windowMs: this.config.streamingWindowMs || this.config.chunkDurationMs,
        hopMs: this.config.streamingHopMs || this.config.overlapMs,
        capacityMs: this.config.streamingCapacityMs || 5000,
        skipSilentWindows: Boolean(this.config.streamingSkipSilentWindows),
        speechThreshold: this.config.realtimeSpeechRmsThreshold,
        silenceThreshold: this.config.realtimeSilenceRmsThreshold,
      });
    }

    return new RollingPcmCommitter({
      sampleRate: this.config.sampleRate,
      channels: this.config.channels,
      minCommitMs: this.config.minChunkDurationMs,
      maxCommitMs: this.config.chunkDurationMs,
      overlapMs: this.config.overlapMs,
      speechFocus: Boolean(this.config.speechFocus),
      speechThreshold: this.config.realtimeSpeechRmsThreshold,
      trailingSilenceMs: this.config.trailingSilenceMs,
    });
  }

  start() {
    if (this.isRunning) {
      return;
    }

    const args = [
      "-q",
      "-t",
      "waveaudio",
      this.config.virtualDeviceName,
      "-r",
      String(this.config.sampleRate),
      "-c",
      String(this.config.channels),
      "-b",
      String(this.config.bytesPerSample * 8),
      "-e",
      "signed-integer",
      "-t",
      "raw",
      "-",
    ];

    this.process = spawn(this.config.soxPath, args, {
      stdio: ["ignore", "pipe", "pipe"],
    });

    this.isRunning = true;
    this.emit("start", {
      device: this.config.virtualDeviceName,
      chunkDurationMs: this.config.streamingSegmenter
        ? this.config.streamingWindowMs || this.config.chunkDurationMs
        : this.config.chunkDurationMs,
    });

    this.process.stdout.on("data", (chunk) => {
      this.emitReadySegments(this.committer.push(chunk));
    });

    this.process.stderr.on("data", (chunk) => {
      const message = chunk.toString().trim();
      if (message) {
        this.emit("debug", message);
      }
    });

    this.process.on("error", (error) => {
      this.emit("error", error);
    });

    this.process.on("close", (code, signal) => {
      this.flushRemainingChunk();
      this.isRunning = false;
      this.process = null;
      this.emit("close", { code, signal });
    });
  }

  stop() {
    if (!this.process) {
      return;
    }

    this.process.kill("SIGINT");
  }

  flushRemainingChunk() {
    this.emitReadySegments(this.committer.flush(true));
  }

  emitReadySegments(segments) {
    for (const segment of segments) {
      const pcmBuffer = Buffer.from(
        segment.pcm.buffer,
        segment.pcm.byteOffset,
        segment.pcm.byteLength
      );

      this.emit("chunk", {
        segmentId: segment.segmentId,
        capturedAt: new Date().toISOString(),
        pcmBuffer,
        analysis: segment.analysis,
        durationMs: segment.durationMs,
        reason: segment.reason,
        startMs: segment.startMs,
        endMs: segment.endMs,
        isPartial: segment.isPartial,
      });
    }
  }
}

module.exports = {
  VirtualAudioCapture,
};
