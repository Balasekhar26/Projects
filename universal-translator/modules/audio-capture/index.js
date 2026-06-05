/**
 * Audio Capture Module
 *
 * Provides system-level audio interception capabilities:
 * - Virtual device capture (existing VB-Cable/Voicemeeter)
 * - WASAPI loopback capture for true system speaker interception
 * - Microphone capture
 * - Audio blocking and routing
 */

const { EventEmitter } = require("events");
const { spawn } = require("child_process");
const path = require("path");
const { RollingPcmCommitter, RollingWindowSegmenter } = require("../../packages/ult-core/src/audio-capture/ring-buffer");

function createCommitter(config) {
  if (config.streamingSegmenter) {
    return new RollingWindowSegmenter({
      sampleRate: config.sampleRate,
      channels: config.channels,
      windowMs: config.streamingWindowMs || config.chunkDurationMs,
      hopMs: config.streamingHopMs || config.overlapMs,
      capacityMs: config.streamingCapacityMs || 5000,
      skipSilentWindows: Boolean(config.streamingSkipSilentWindows),
      speechThreshold: config.realtimeSpeechRmsThreshold,
      silenceThreshold: config.realtimeSilenceRmsThreshold,
    });
  }

  return new RollingPcmCommitter({
    sampleRate: config.sampleRate,
    channels: config.channels,
    minCommitMs: config.minChunkDurationMs,
    maxCommitMs: config.chunkDurationMs,
    overlapMs: config.overlapMs,
    speechFocus: Boolean(config.speechFocus),
    speechThreshold: config.realtimeSpeechRmsThreshold,
    trailingSilenceMs: config.trailingSilenceMs,
  });
}

/**
 * Virtual Audio Capture (VB-Cable/Voicemeeter based)
 * Existing implementation refactored for modularity
 */
class VirtualAudioCapture extends EventEmitter {
  constructor(config) {
    super();
    this.config = config;
    this.process = null;
    this.isRunning = false;
    this.committer = createCommitter(this.config);
  }

  start() {
    if (this.isRunning) return;

    const args = [
      "-q",
      "-t", "waveaudio", this.config.virtualDeviceName,
      "-r", String(this.config.sampleRate),
      "-c", String(this.config.channels),
      "-b", String(this.config.bytesPerSample * 8),
      "-e", "signed-integer",
      "-t", "raw", "-"
    ];

    this.process = spawn(this.config.soxPath, args, {
      stdio: ["ignore", "pipe", "pipe"]
    });

    this.isRunning = true;
    this.emit("start", {
      device: this.config.virtualDeviceName,
      chunkDurationMs: this.config.chunkDurationMs
    });

    this.process.stdout.on("data", (chunk) => {
      this.emitReadySegments(this.committer.push(chunk));
    });

    this.process.stderr.on("data", (chunk) => {
      const message = chunk.toString().trim();
      if (message) this.emit("debug", message);
    });

    this.process.on("error", (error) => this.emit("error", error));
    this.process.on("close", (code, signal) => {
      this.flushRemainingChunk();
      this.isRunning = false;
      this.process = null;
      this.emit("close", { code, signal });
    });
  }

  stop() {
    if (this.process) this.process.kill("SIGINT");
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
        capturedAt: new Date().toISOString(),
        pcmBuffer,
        analysis: segment.analysis,
        durationMs: segment.durationMs,
        reason: segment.reason,
      });
    }
  }
}

/**
 * WASAPI Loopback Capture for true system speaker interception
 * Captures audio being sent to speakers before playback
 */
class WasapiLoopbackCapture extends EventEmitter {
  constructor(config) {
    super();
    this.config = config;
    this.isRunning = false;
    this.committer = createCommitter(this.config);
  }

  start(deviceId = null) {
    if (this.isRunning) return;

    // Use PowerShell script for WASAPI loopback capture
    const scriptPath = path.join(__dirname, "wasapi-loopback-capture.ps1");
    const args = deviceId ? [scriptPath, deviceId] : [scriptPath];

    this.process = spawn("powershell", [
      "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", ...args
    ], {
      stdio: ["ignore", "pipe", "pipe"]
    });

    this.isRunning = true;
    this.emit("start", { deviceId, type: "loopback" });

    this.process.stdout.on("data", (chunk) => {
      this.emitReadySegments(this.committer.push(chunk));
    });

    this.process.stderr.on("data", (chunk) => {
      const message = chunk.toString().trim();
      if (message) this.emit("debug", message);
    });

    this.process.on("error", (error) => this.emit("error", error));
    this.process.on("close", (code, signal) => {
      this.flushRemainingChunk();
      this.isRunning = false;
      this.process = null;
      this.emit("close", { code, signal });
    });
  }

  stop() {
    if (this.process) this.process.kill("SIGINT");
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
        capturedAt: new Date().toISOString(),
        pcmBuffer,
        analysis: segment.analysis,
        durationMs: segment.durationMs,
        reason: segment.reason,
        source: "loopback" // Mark as system audio
      });
    }
  }
}

/**
 * Microphone Capture
 */
class MicrophoneCapture extends EventEmitter {
  constructor(config) {
    super();
    this.config = config;
    this.isRunning = false;
    this.committer = createCommitter(this.config);
  }

  start() {
    const device = this.config.microphoneDeviceName || this.config.virtualDeviceName;
    if (this.isRunning) return;

    const args = [
      "-q",
      "-t", "waveaudio", device,
      "-r", String(this.config.sampleRate),
      "-c", String(this.config.channels),
      "-b", String(this.config.bytesPerSample * 8),
      "-e", "signed-integer",
      "-t", "raw", "-"
    ];

    this.process = spawn(this.config.soxPath, args, {
      stdio: ["ignore", "pipe", "pipe"]
    });

    this.isRunning = true;
    this.emit("start", { device, type: "microphone" });

    this.process.stdout.on("data", (chunk) => {
      this.emitReadySegments(this.committer.push(chunk));
    });

    this.process.stderr.on("data", (chunk) => {
      const message = chunk.toString().trim();
      if (message) this.emit("debug", message);
    });

    this.process.on("error", (error) => this.emit("error", error));
    this.process.on("close", (code, signal) => {
      this.flushRemainingChunk();
      this.isRunning = false;
      this.process = null;
      this.emit("close", { code, signal });
    });
  }

  stop() {
    if (this.process) this.process.kill("SIGINT");
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
        capturedAt: new Date().toISOString(),
        pcmBuffer,
        analysis: segment.analysis,
        durationMs: segment.durationMs,
        reason: segment.reason,
        source: "microphone"
      });
    }
  }
}


module.exports = {
  VirtualAudioCapture,
  WasapiLoopbackCapture,
  MicrophoneCapture
};