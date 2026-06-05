const fs = require("fs/promises");
const path = require("path");
const { EventEmitter } = require("events");
const { writePcmAsWavFile } = require("../utils/wav");
const { PlaybackController } = require("../../packages/ult-core/src/tts-engine/playback-controller");
const { LatencyProfiler } = require("./latency-profiler");
const { UtteranceManager } = require("./utterance-manager");
const {
  aggregateVoiceIdentityProfiles,
  blendVoiceIdentityProfiles,
  extractVoiceIdentityFromChunk,
} = require("../../packages/ult-core/src/voice-identity/profile");
const { resolveTemporalIdentityConfig } = require("../ai-observer/temporal-config");

const DEFAULT_MAX_QUEUE_DEPTH = 4;
const DEFAULT_TARGET_LATENCY_MS = 0;
const EARLY_SPEECH_ESCAPE_MS = 250;
const DEFAULT_FORCE_COMMIT_MS = 200;
const DEFAULT_SOFT_TRANSLATION_CONFIDENCE_THRESHOLD = 0.45;
const DEFAULT_COMMIT_TRANSLATION_CONFIDENCE_THRESHOLD = 0.8;
const PRE_SPEECH_TRIGGER_MS = 150;

function normalizeTranscript(value) {
  return typeof value === "string" ? value.replace(/\s+/g, " ").trim() : "";
}

function findTranscriptOverlap(previousText, nextText) {
  const previousWords = normalizeTranscript(previousText).split(" ").filter(Boolean);
  const nextWords = normalizeTranscript(nextText).split(" ").filter(Boolean);
  const maxOverlap = Math.min(previousWords.length, nextWords.length);

  for (let size = maxOverlap; size > 0; size -= 1) {
    const previousTail = previousWords.slice(previousWords.length - size).join(" ");
    const nextHead = nextWords.slice(0, size).join(" ");
    if (previousTail === nextHead) {
      return nextHead;
    }
  }

  return "";
}

function computeDelta(previousText, nextText) {
  const previous = normalizeTranscript(previousText);
  const next = normalizeTranscript(nextText);
  if (!next) {
    return "";
  }

  if (!previous) {
    return next;
  }

  if (next.startsWith(previous)) {
    return normalizeTranscript(next.slice(previous.length));
  }

  const overlap = findTranscriptOverlap(previous, next);
  if (overlap) {
    return normalizeTranscript(next.slice(overlap.length));
  }

  return next;
}

class LiveTranscript {
  constructor(options = {}) {
    this.previousText = "";
    this.lastSpokenDelta = "";
    this.stability = 0;
    this.minDeltaChars = Number.isFinite(options.minDeltaChars) ? options.minDeltaChars : 4;
  }

  update(nextText) {
    const normalizedText = normalizeTranscript(nextText);
    if (!normalizedText) {
      this.previousText = "";
      this.stability = 0;
      return { deltaText: "", isStable: false, overlapText: "", fullText: "", confidence: 0 };
    }

    const previousText = this.previousText;
    const overlapText = findTranscriptOverlap(previousText, normalizedText);
    const deltaText = normalizeTranscript(
      overlapText ? normalizedText.slice(overlapText.length) : normalizedText
    );

    if (!deltaText) {
      this.previousText = normalizedText;
      this.stability += 1;
      return { deltaText: "", isStable: true, overlapText, fullText: normalizedText, confidence: 0.92 };
    }

    if (!previousText) {
      this.stability = 1;
    } else if (overlapText.length > 0 || normalizedText === previousText) {
      this.stability += 1;
    } else {
      this.stability = 0;
    }

    this.previousText = normalizedText;

    const isStable =
      this.stability >= 1 ||
      /[.!?;,:\u0964]$/.test(normalizedText);
    const extendsPrevious = !previousText || overlapText.length > 0 || normalizedText.startsWith(previousText);

    return {
      deltaText,
      overlapText,
      fullText: normalizedText,
      isStable,
      tokenCount: deltaText.split(" ").filter(Boolean).length,
      extendsPrevious,
      confidence: estimateTranscriptConfidence({
        normalizedText,
        previousText,
        overlapText,
        isStable,
        stability: this.stability,
        extendsPrevious,
      }),
    };
  }

  shouldSpeak(text, options = {}) {
    const normalizedText = normalizeTranscript(text);
    if (!normalizedText) {
      return false;
    }

    const nowMs = Number.isFinite(options.nowMs) ? options.nowMs : Date.now();
    const lastSpeechAt = Number.isFinite(options.lastSpeechAt) ? options.lastSpeechAt : 0;
    if (
      normalizedText === this.lastSpokenDelta &&
      (!lastSpeechAt || nowMs - lastSpeechAt < EARLY_SPEECH_ESCAPE_MS)
    ) {
      return false;
    }

    this.lastSpokenDelta = normalizedText;
    return true;
  }
}

class RealtimeTranslator extends EventEmitter {
  constructor({ config, capture, sttClient, translator, speaker }) {
    super();
    this.config = config;
    this.capture = capture;
    this.sttClient = sttClient;
    this.translator = translator;
    this.speaker = speaker;
    this.temporalIdentityConfig = resolveTemporalIdentityConfig(config.temporalIdentityConfig);
    this.chunkSequence = 0;
    this.lastSpokenText = "";
    this.isBound = false;
    this.captureClosedPromise = null;
    this.queueDepth = 0;
    this.processingQueue = Promise.resolve();
    this.detectedLanguage = null;
    this.lastProsody = null;
    this.pendingSpeechText = "";
    this.pendingSpeechStartedAt = 0;
    this.lastSpeechAt = 0;
    this.lastTentativeTranscript = "";
    this.phraseCounter = 0;
    this.currentPhraseId = null;
    this.currentPhraseRevision = 0;
    this.lastEmittedSegmentId = null;
    this.lastCommittedText = "";
    this.lastEmittedText = "";
    this.activeTranslatedText = "";
    this.activeSourceText = "";
    this.lastDeliveryPriority = 0;
    this.voiceIdentityHistory = [];
    this.lastSpeechDetectedAt = 0;
    this.lastPresenceSignalAt = 0;
    this.rhythmMemory = {
      pauseMs: 220,
      clauseCadence: 0.5,
      speechRate: 1.0,
      updatedAt: 0,
    };
    this.utteranceManager = new UtteranceManager({
      maxGapMs: Number.isFinite(Number(config.realtimeUtteranceMaxGapMs))
        ? Number(config.realtimeUtteranceMaxGapMs)
        : 1200,
      similarityThreshold: Number.isFinite(Number(config.realtimeUtteranceSimilarityThreshold))
        ? Number(config.realtimeUtteranceSimilarityThreshold)
        : 0.35,
    });
    this.voiceIdentityProfile = null;
    this.lastSpeechDetectedAt = 0;
    this.lastPresenceSignalAt = 0;
    this.rhythmMemory = {
      pauseMs: 220,
      clauseCadence: 0.5,
      speechRate: 1.0,
      updatedAt: 0,
    };
    this.maxQueueDepth = Number.isFinite(Number(config.realtimeMaxQueueDepth))
      ? Number(config.realtimeMaxQueueDepth)
      : DEFAULT_MAX_QUEUE_DEPTH;
    this.targetLatencyMs = Number.isFinite(Number(config.realtimeTargetLatencyMs))
      ? Number(config.realtimeTargetLatencyMs)
      : DEFAULT_TARGET_LATENCY_MS;
    this.forceCommitMs = Number.isFinite(Number(config.realtimeForceCommitMs))
      ? Number(config.realtimeForceCommitMs)
      : DEFAULT_FORCE_COMMIT_MS;
    this.softTranslationConfidenceThreshold = Number.isFinite(Number(config.realtimeSpeechConfidenceThreshold))
      ? Number(config.realtimeSpeechConfidenceThreshold)
      : DEFAULT_SOFT_TRANSLATION_CONFIDENCE_THRESHOLD;
    this.commitTranslationConfidenceThreshold = Number.isFinite(Number(config.commitTranslationConfidenceThreshold))
      ? Number(config.commitTranslationConfidenceThreshold)
      : DEFAULT_COMMIT_TRANSLATION_CONFIDENCE_THRESHOLD;
    this.skipAllVadSilence = Boolean(config.skipAllVadSilence);
    this.strictSpeechConfidenceGate = Boolean(config.strictSpeechConfidenceGate);
    this.liveTranscript = new LiveTranscript({
      minDeltaChars: this.config.realtimeMinDeltaChars || 4,
    });
    this.debugForceAudio = process.env.ULT_FORCE_AUDIO === "1";
    this.debugCapture = process.env.ULT_DEBUG_CAPTURE === "1";
    this.debugCaptureLimit = Number.isFinite(Number(process.env.ULT_DEBUG_CAPTURE_LIMIT))
      ? Number(process.env.ULT_DEBUG_CAPTURE_LIMIT)
      : 3;
    this.playbackController = new PlaybackController({ speaker: this.speaker });
    this.latencyProfiler = new LatencyProfiler({
      enabled: this.config.enableLatencyProfiler !== false,
    });
    this.lastRms = 0;
    this.rmsInterval = null;
  }

  async start() {
    await fs.mkdir(this.config.tempDir, { recursive: true });
    this.bindEvents();
    this.captureClosedPromise = new Promise((resolve) => {
      this.capture.once("close", resolve);
    });
    this.capture.start();
    this.rmsInterval = setInterval(() => { this.emit("debug", `[mic live rms] ${this.lastRms}`) }, 500);
  }

  async stop() {
    if (this.rmsInterval) { clearInterval(this.rmsInterval); this.rmsInterval = null; }
    this.capture.stop();
    await this.captureClosedPromise;
    await this.processingQueue.catch(() => {});
    this.playbackController.stop();
  }

  bindEvents() {
    if (this.isBound) return;
    this.isBound = true;

    this.capture.on("start", (details) => this.emit("status", `Capturing from ${details.device}`));
    this.capture.on("debug", (message) => this.emit("debug", `capture: ${message}`));
    this.capture.on("error", (error) => this.emit("error", error));
    this.capture.on("close", ({ code }) => this.emit("status", `Capture stopped (code=${code ?? "none"})`));
    this.sttClient.on("debug", (message) => this.emit("debug", `whisper: ${message}`));
    this.sttClient.on("error", (error) => this.emit("error", error));

    this.capture.on("chunk", (chunk) => {
      if (this.queueDepth >= this.maxQueueDepth) {
        return;
      }

      this.queueDepth += 1;
      this.processingQueue = this.processingQueue
        .then(() => this.processChunk(chunk))
        .catch((error) => this.emit("error", error))
        .finally(() => {
          this.queueDepth = Math.max(0, this.queueDepth - 1);
        });
    });
  }

  async processChunk(chunk) {
    const chunkNumber = ++this.chunkSequence;
    const startedAt = Date.now();
    const wavPath = path.join(this.config.tempDir, `chunk-${chunkNumber}.wav`);
    const chunkRms = Number(chunk?.analysis?.rms);
    this.lastRms = chunkRms;
    const silenceThreshold = Number(this.config.realtimeSilenceRmsThreshold);
    this.latencyProfiler.startChunk(chunkNumber, {
      captureDetectedAt: startedAt,
    });
    this.latencyProfiler.markChunkStage(chunkNumber, "chunk_received", startedAt);

    if (
      !this.debugForceAudio &&
      !this.skipAllVadSilence &&
      Number.isFinite(chunkRms) &&
      Number.isFinite(silenceThreshold) &&
      chunkRms <= silenceThreshold &&
      chunk?.reason === "vad-silence"
    ) {
      this.emit("debug", `chunk ${chunkNumber}: silence skipped before STT`);
      this.emit("latency", {
        chunkNumber,
        latencyMs: Date.now() - startedAt,
        durationMs: chunk.durationMs,
        skipped: true,
      });
      return;
    }

    if (this.debugForceAudio && chunk?.reason === "vad-silence") {
      this.emit(
        "debug",
        `chunk ${chunkNumber}: force-audio bypass active (reason=${chunk.reason}, rms=${Number.isFinite(chunkRms) ? chunkRms.toFixed(4) : "n/a"})`
      );
    }

    if (this.debugCapture) {
      this.emit(
        "debug",
        `[audio] chunk ${chunkNumber}: rms=${Number.isFinite(chunkRms) ? chunkRms.toFixed(6) : "n/a"} reason=${chunk?.reason || "unknown"} duration=${chunk?.durationMs || 0}ms`
      );
    }

    await writePcmAsWavFile(wavPath, chunk.pcmBuffer, {
      sampleRate: this.config.sampleRate,
      channels: this.config.channels,
      bitsPerSample: this.config.bytesPerSample * 8,
    });

    if (this.debugCapture && chunkNumber <= this.debugCaptureLimit) {
      const debugInputPath = path.join(this.config.tempDir, `debug-input-${chunkNumber}.wav`);
      await fs.copyFile(wavPath, debugInputPath);
      this.emit("debug", `[audio] debug dump ${debugInputPath}`);
    }

    this.emit("status", `Processing chunk ${chunkNumber}${chunk.reason ? ` (${chunk.reason})` : ""}`);
    this.latencyProfiler.markChunkStage(chunkNumber, "wav_ready");

    try {
      this.updateVoiceIdentity(chunk, Date.now());
      this._triggerPreSpeechPresence(chunk, startedAt);

      const configSourceLanguage = this.config.sourceLanguage || "auto";
      const sourceLanguage =
        configSourceLanguage !== "auto" ? configSourceLanguage : this.detectedLanguage || "auto";
      const policy = this.config.onlinePolicy || "auto";

      const sttResult = await this.sttClient.transcribeChunk({
        audioPath: wavPath,
        sourceLanguage,
        targetLanguage: this.config.targetLanguage,
        onlinePolicy: policy,
      });
      if (this.debugCapture) {
        this.emit(
          "debug",
          `[stt raw] chunk ${chunkNumber}: "${normalizeTranscript(sttResult.transcript || "")}" lang=${sttResult.detected_language || "n/a"} backend=${sttResult.backend || "unknown"}`
        );
      }

      if (!this.detectedLanguage && sttResult.detected_language) {
        this.detectedLanguage = sttResult.detected_language;
        this.emit("status", `Language detected: ${this.detectedLanguage} - locked`);
      }

      const transcript = normalizeTranscript(sttResult.transcript || "");
      this.latencyProfiler.markChunkStage(chunkNumber, "stt_ready");
      if (!transcript) {
        this.emit("latency", { chunkNumber, latencyMs: Date.now() - startedAt, durationMs: chunk.durationMs });
        return;
      }

      const nowMs = Date.now();
      const transcriptState = this.liveTranscript.update(transcript);
      const utterance = this.utteranceManager.attachOrSpawn(transcriptState, chunk, nowMs);
      if (!transcriptState.deltaText) {
        this.emit("debug", `chunk ${chunkNumber}: transcript overlapped fully; no new delta yet`);
        this.emit("latency", { chunkNumber, latencyMs: Date.now() - startedAt, durationMs: chunk.durationMs });
        return;
      }

      this._updateRhythmMemory({
        nowMs,
        transcriptState,
        chunk,
      });
      const risingConfidence =
        transcriptState.confidence >= this.playbackController.currentConfidence + 0.07;
      const meaningfulDelta = transcriptState.deltaText.split(" ").filter(Boolean).length > 0;
      if (risingConfidence && meaningfulDelta && this.playbackController.currentJob) {
        this.playbackController.noteAnticipatedInterrupt();
      }
      const sinceLastSpeechMs = this.lastSpeechAt ? nowMs - this.lastSpeechAt : Number.POSITIVE_INFINITY;
      const shouldAttemptSpeech =
        transcriptState.confidence >= this.softTranslationConfidenceThreshold ||
        transcriptState.isStable ||
        transcriptState.tokenCount >= 2 ||
        sinceLastSpeechMs >= EARLY_SPEECH_ESCAPE_MS;

      if (!transcriptState.isStable && !transcriptState.extendsPrevious && sinceLastSpeechMs < EARLY_SPEECH_ESCAPE_MS) {
        this.emit("debug", `chunk ${chunkNumber}: non-extending unstable hypothesis briefly delayed`);
        this.emit("latency", { chunkNumber, latencyMs: Date.now() - startedAt, durationMs: chunk.durationMs });
        return;
      }

      if (!shouldAttemptSpeech) {
        this.emit("debug", `chunk ${chunkNumber}: hypothesis waiting for early-speech escape`);
        this.emit("latency", { chunkNumber, latencyMs: Date.now() - startedAt, durationMs: chunk.durationMs });
        return;
      }

      const translationResult = await this.translator.translate({
        transcript: transcriptState.fullText,
        whisperTranslation: "",
        detectedLanguage: sttResult.detected_language || this.detectedLanguage,
        sourceLanguage,
        targetLanguage: this.config.targetLanguage,
        onlinePolicy: policy,
      });

      const translatedFullText = normalizeTranscript(translationResult.translatedText || "");
      this.latencyProfiler.markChunkStage(chunkNumber, "translation_ready");
      this.utteranceManager.updateTarget(
        utterance,
        translatedFullText,
        transcriptState.isStable ? "commit" : "tentative",
        transcriptState.confidence,
        nowMs,
        chunk
      );
      const translatedDeltaText = computeDelta(this.activeTranslatedText, translatedFullText);
      if (
        !translatedFullText ||
        !translatedDeltaText ||
        translatedFullText === this.lastSpokenText ||
        !this.liveTranscript.shouldSpeak(translatedDeltaText, { nowMs, lastSpeechAt: this.lastSpeechAt })
      ) {
        this.emit("latency", { chunkNumber, latencyMs: Date.now() - startedAt, durationMs: chunk.durationMs });
        return;
      }

      const speechDecision = this.bufferTranslatedPhrase(translatedFullText, {
        isStable: transcriptState.isStable,
        tokenCount: transcriptState.tokenCount,
        confidence: transcriptState.confidence,
        nowMs,
      });
      if (!speechDecision.readyText) {
        this.emit(
          "debug",
          `chunk ${chunkNumber}: buffered ${transcriptState.isStable ? "stable" : "tentative"} translation fragment`
        );
        this.emit("latency", { chunkNumber, latencyMs: Date.now() - startedAt, durationMs: chunk.durationMs });
        return;
      }

      const arbitration = this.utteranceManager.decidePlayback(utterance, {
        nowMs,
        currentJob: this.playbackController.currentJob,
        currentConfidence: this.playbackController.currentConfidence,
        lastSpeechAt: this.lastSpeechAt,
        translatedText: translatedFullText,
        transcriptState,
      });

      if (arbitration.action !== "speak") {
        this.emit("debug", `chunk ${chunkNumber}: playback arbitration delayed (${arbitration.reason})`);
        this.emit("latency", { chunkNumber, latencyMs: Date.now() - startedAt, durationMs: chunk.durationMs });
        return;
      }

      this.lastSpokenText = speechDecision.readyText;
      this.lastSpeechAt = nowMs;
      this.lastTentativeTranscript = speechDecision.mode === "tentative" ? transcript : "";
      this.lastEmittedText = speechDecision.readyText;
      this.activeTranslatedText = translatedFullText;
      this.activeSourceText = transcriptState.fullText;
      if (speechDecision.mode === "commit") {
        this.lastCommittedText = translatedFullText;
        this.lastEmittedText = translatedFullText;
      }

      const prosody = this.extractSimpleProsody(chunk, this.voiceIdentityProfile);
      if (prosody) {
        if (this.lastProsody) {
          prosody.energy = prosody.energy * 0.8 + this.lastProsody.energy * 0.2;
          prosody.rate = prosody.rate * 0.8 + this.lastProsody.rate * 0.2;
        }
        this.lastProsody = prosody;
      }

      const pipelineMs = Date.now() - startedAt;
      const utteranceContext = this.utteranceManager.getPlaybackContext(utterance);
      this.emit("translation", {
        chunkNumber,
        detectedLanguage: sttResult.detected_language || this.detectedLanguage || "unknown",
        transcript: transcriptState.deltaText,
        transcriptFullText: transcriptState.fullText,
        translatedText: speechDecision.readyText,
        translatedFullText,
        backend: translationResult.backend,
        latencyMs: pipelineMs,
        mode: speechDecision.mode,
        confidence: transcriptState.confidence,
        ...utteranceContext,
      });

      if (this.targetLatencyMs > 0 && pipelineMs < this.targetLatencyMs) {
        await new Promise((resolve) => setTimeout(resolve, this.targetLatencyMs - pipelineMs));
      }

      const deliveryPriority =
        speechDecision.mode === "commit" ? 3 :
        transcriptState.confidence > 0.75 ? 2 :
        transcriptState.confidence > 0.45 ? 1 : 0;
      const playbackEvent = this.buildPlaybackEvent({
        chunkNumber,
        mode: speechDecision.mode,
        text: speechDecision.readyText,
        language: this.config.targetLanguage,
        onlinePolicy: policy,
        outputDeviceName: this.config.ttsOutputDeviceName,
        prosody: this.lastProsody,
        voiceProfile: this.config.voiceProfile,
        voiceIdentityProfile: this.voiceIdentityProfile,
        confidence: transcriptState.confidence,
        fullText: translatedFullText,
        priority: deliveryPriority,
        preemptNow: deliveryPriority > this.lastDeliveryPriority || arbitration.isMorph,
        ...utteranceContext,
        utterance,
      });
      this.lastDeliveryPriority = deliveryPriority;
      this.latencyProfiler.markChunkStage(chunkNumber, "speech_enqueued");
      this.playbackController.enqueue(playbackEvent);

      this.emit("latency", { chunkNumber, latencyMs: Date.now() - startedAt, durationMs: chunk.durationMs });
    } catch (error) {
      this.emit("debug", `chunk ${chunkNumber} error: ${error.message}`);
    } finally {
      await fs.rm(wavPath, { force: true }).catch(() => {});
    }
  }

  buildPlaybackEvent({ chunkNumber, mode, text, utterance, ...rest }) {
    const utteranceId = typeof rest.utteranceId === "string" ? rest.utteranceId : undefined;
    const utteranceVersion = Number.isFinite(Number(rest.utteranceVersion))
      ? Number(rest.utteranceVersion)
      : undefined;

    let phraseId = utteranceId || this.currentPhraseId || null;
    let revision = utteranceVersion || this.currentPhraseRevision || 0;

    if (!phraseId) {
      this.phraseCounter += 1;
      phraseId = this.phraseCounter;
      revision = utteranceVersion || 1;
    }

    if (utteranceId) {
      revision = utteranceVersion || revision || 1;
    } else if (mode !== "commit" && this.currentPhraseId === phraseId) {
      revision = (this.currentPhraseRevision || 0) + 1;
    }

    this.currentPhraseId = phraseId;
    this.currentPhraseRevision = revision;

    const revisionLabel = mode === "commit" ? "final" : String(revision);
    const segmentId = `${phraseId}:${revisionLabel}`;
    const supersedesSegmentId = this.lastEmittedUtteranceId === phraseId ? this.lastEmittedSegmentId : null;
    this.lastEmittedSegmentId = segmentId;
    this.lastEmittedUtteranceId = phraseId;

    if (mode === "commit") {
      this.currentPhraseId = null;
      this.currentPhraseRevision = 0;
      this.activeTranslatedText = "";
      this.activeSourceText = "";
    }

    const phraseMetric = this.latencyProfiler.attachPhrase(chunkNumber, {
      phraseId,
      revision,
      mode,
      supersedesSegmentId,
    });

    return {
      chunkNumber,
      mode,
      text,
      fullText: rest.fullText || text,
      phraseId,
      revision: mode === "commit" ? revisionLabel : revision,
      segmentId,
      supersedesSegmentId,
      onAudibleStart: () => {
        if (utterance) {
          this.utteranceManager.markSpokenVersion(utterance, Date.now());
        }
        const metric = this.latencyProfiler.markPlaybackStart({ phraseId, revision });
        if (metric) {
          this.emit("metric", {
            type: "latency",
            scope: "chunk",
            ...metric,
          });
        }
        const phraseLatency = this.latencyProfiler.buildPhraseMetric({
          phraseId,
          revision,
          arrivedAt: phraseMetric?.enqueuedAt,
        });
        if (phraseLatency?.interruptReactionMs !== null) {
          this.emit("metric", {
            type: "latency",
            scope: "phrase",
            ...phraseLatency,
          });
        }
      },
      onAudibleEnd: () => {
        if (utterance) {
          this.utteranceManager.markPlaybackComplete(utterance, Date.now());
        }
        this.latencyProfiler.markPlaybackEnd({ phraseId, revision });
      },
      ...rest,
    };
  }

  extractSimpleProsody(chunk, identityProfile = null) {
    const analysis = chunk.analysis;
    if (!analysis) {
      return null;
    }

    const prosody = {
      energy: Number.isFinite(analysis.rms) ? analysis.rms : 0.05,
      rate: Number.isFinite(analysis.zeroCrossingRate) ? analysis.zeroCrossingRate : 0.08,
      energyMean: Number.isFinite(analysis.rms) ? analysis.rms : 0.05,
      cadence: this.rhythmMemory.clauseCadence,
      speechRate: this.rhythmMemory.speechRate,
      expectedPauseMs: this.rhythmMemory.pauseMs,
    };

    if (identityProfile && typeof identityProfile === "object") {
      prosody.pitchMean = Number.isFinite(identityProfile.f0Mean) ? identityProfile.f0Mean : undefined;
      prosody.pitchStd = Number.isFinite(identityProfile.f0Range) ? identityProfile.f0Range / 2 : undefined;
      prosody.speakingRate = Number.isFinite(identityProfile.tempo)
        ? Math.max(0.7, Math.min(1.3, identityProfile.tempo))
        : undefined;
    }

    return prosody;
  }

  updateVoiceIdentity(chunk, nowMs = Date.now()) {
    const extracted = extractVoiceIdentityFromChunk(chunk, {
      sampleRate: this.config.sampleRate,
      channels: this.config.channels,
    });
    if (!extracted) {
      return this.voiceIdentityProfile;
    }

    const windowMs = Number.isFinite(this.config.voiceIdentityWindowMs)
      ? this.config.voiceIdentityWindowMs
      : 5000;
    const blendFactor = Number.isFinite(this.config.voiceIdentityBlendFactor)
      ? this.config.voiceIdentityBlendFactor
      : 0.15;

    this.voiceIdentityHistory.push({
      capturedAt: nowMs,
      durationMs: chunk?.durationMs || chunk?.analysis?.durationMs || 0,
      profile: extracted,
    });
    this.voiceIdentityHistory = this.voiceIdentityHistory.filter((entry) => nowMs - entry.capturedAt <= windowMs);

    const aggregate = aggregateVoiceIdentityProfiles(this.voiceIdentityHistory);
    if (!aggregate) {
      return this.voiceIdentityProfile;
    }

    this.voiceIdentityProfile = blendVoiceIdentityProfiles(this.voiceIdentityProfile, aggregate, blendFactor);
    return this.voiceIdentityProfile;
  }

  bufferTranslatedPhrase(translatedText, options = {}) {
    const incoming = normalizeTranscript(translatedText);
    if (!incoming) {
      return { readyText: "", mode: "hold" };
    }

    const nowMs = Number.isFinite(options.nowMs) ? options.nowMs : Date.now();
    const isStable = Boolean(options.isStable);
    const confidence = Number.isFinite(options.confidence) ? options.confidence : 0;
    const tokenCount = Number.isFinite(options.tokenCount)
      ? options.tokenCount
      : incoming.split(" ").filter(Boolean).length;

    if (!this.pendingSpeechStartedAt) {
      this.pendingSpeechStartedAt = nowMs;
    }

    this.pendingSpeechText = normalizeTranscript(
      this.pendingSpeechText ? `${this.pendingSpeechText} ${incoming}` : incoming
    );

    const wordCount = this.pendingSpeechText.split(" ").filter(Boolean).length;
    const hasPauseBoundary = /[.!?;:\u0964]$/.test(this.pendingSpeechText);
    const pendingAgeMs = nowMs - this.pendingSpeechStartedAt;
    const sinceLastSpeechMs = this.lastSpeechAt ? nowMs - this.lastSpeechAt : Number.POSITIVE_INFINITY;
    const canTentativelySpeak =
      confidence >= this.softTranslationConfidenceThreshold ||
      tokenCount >= 2 ||
      (tokenCount >= 1 && sinceLastSpeechMs >= EARLY_SPEECH_ESCAPE_MS) ||
      hasPauseBoundary;
    const shouldForceCommit = pendingAgeMs >= this.forceCommitMs;
    const shouldCommit =
      confidence >= this.commitTranslationConfidenceThreshold ||
      hasPauseBoundary ||
      (isStable && wordCount >= 2) ||
      (isStable && tokenCount >= 1 && sinceLastSpeechMs >= EARLY_SPEECH_ESCAPE_MS) ||
      shouldForceCommit;

    if (!shouldCommit && !canTentativelySpeak) {
      return { readyText: "", mode: "hold" };
    }

    const ready = this.pendingSpeechText;
    this.pendingSpeechText = "";
    this.pendingSpeechStartedAt = 0;
    return {
      readyText: ready,
      mode: isStable || shouldForceCommit || hasPauseBoundary || confidence >= this.commitTranslationConfidenceThreshold
        ? "commit"
        : "tentative",
    };
  }

  _triggerPreSpeechPresence(chunk, startedAt) {
    const rms = Number(chunk?.analysis?.rms);
    const threshold = Number(this.config.realtimeSpeechRmsThreshold);
    const speechActive =
      chunk?.reason !== "vad-silence" &&
      (!Number.isFinite(threshold) || !Number.isFinite(rms) || rms >= threshold);

    if (!speechActive) {
      return;
    }

    const now = Date.now();
    if (now - this.lastPresenceSignalAt < PRE_SPEECH_TRIGGER_MS) {
      return;
    }

    const prosody = this.extractSimpleProsody(chunk, this.voiceIdentityProfile);
    this.lastSpeechDetectedAt = now;
    this.lastPresenceSignalAt = now;
    this.playbackController.noteSpeechDetected({
      chunkNumber: this.chunkSequence,
      detectedAt: startedAt,
      triggerAt: startedAt + PRE_SPEECH_TRIGGER_MS,
      prosody,
    });
  }

  _updateRhythmMemory({ nowMs, transcriptState, chunk }) {
    const sinceLastSpeechMs = this.lastSpeechAt ? Math.max(0, nowMs - this.lastSpeechAt) : this.rhythmMemory.pauseMs;
    const tokenCount = Number.isFinite(transcriptState?.tokenCount) ? transcriptState.tokenCount : 0;
    const chunkDurationMs = Number(chunk?.durationMs) || 0;
    const tokenRate = chunkDurationMs > 0 && tokenCount > 0
      ? (tokenCount / Math.max(chunkDurationMs, 1)) * 1000
      : this.rhythmMemory.speechRate;
    const pauseTarget = transcriptState?.isStable
      ? sinceLastSpeechMs
      : Math.min(sinceLastSpeechMs, this.rhythmMemory.pauseMs);
    const clauseCadenceTarget = clamp(
      0.35 +
        (Math.min(tokenCount, 6) * 0.06) +
        (transcriptState?.isStable ? 0.08 : 0),
      0.3,
      0.85
    );

    this.rhythmMemory = {
      pauseMs: Math.round(lerp(this.rhythmMemory.pauseMs, pauseTarget, 0.25)),
      clauseCadence: lerp(this.rhythmMemory.clauseCadence, clauseCadenceTarget, 0.2),
      speechRate: clamp(lerp(this.rhythmMemory.speechRate, tokenRate || 1.0, 0.2), 0.7, 1.35),
      updatedAt: nowMs,
    };
  }
}

module.exports = { LiveTranscript, RealtimeTranslator, computeDelta, findTranscriptOverlap, normalizeTranscript };

function estimateTranscriptConfidence({
  normalizedText,
  previousText,
  overlapText,
  isStable,
  stability,
  extendsPrevious,
}) {
  if (!normalizedText) {
    return 0;
  }

  let confidence = isStable ? 0.78 : 0.48;

  if (!previousText) {
    confidence += 0.1;
  } else if (extendsPrevious) {
    confidence += 0.08;
  } else {
    confidence -= 0.14;
  }

  if (overlapText) {
    confidence += 0.05;
  }

  if (stability >= 2) {
    confidence += 0.06;
  }

  if (/[.!?;,:\u0964]$/.test(normalizedText)) {
    confidence += 0.05;
  }

  return Math.max(0.2, Math.min(0.99, confidence));
}

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function lerp(a, b, t) {
  return a + ((b - a) * t);
}
