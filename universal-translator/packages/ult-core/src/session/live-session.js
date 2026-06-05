const fs = require("fs/promises");
const path = require("path");
const { EventEmitter } = require("events");
const { randomUUID } = require("crypto");

const { HybridSttEngine } = require("../stt-engine");
const { HybridTranslationEngine } = require("../translation-engine");
const { TieredSpeechEngine } = require("../tts-engine/tiered-speaker");
const { AudioSeparator } = require("../audio-separation/separator");
const { ProsodyEngine } = require("../prosody/engine");
const { listDeviceTopology } = require("../device-control/topology");
const { resolveCoreConfig } = require("../config");
const { validateRouteProfile } = require("../audio-routing/validator");
const { EventTimeNormalizer } = require("../../../../src/ai-observer/event-time-normalizer");
const {
  stabilizeTemporalIdentities,
} = require("../../../../src/ai-observer/temporal-identity");
const {
  resolveTemporalIdentityConfig,
} = require("../../../../src/ai-observer/temporal-config");
const {
  SCHEMA_VERSION,
  NORMALIZATION_VERSION,
  MAX_DEBUG_EVENTS,
  computeDependencyHash,
  computeIntegrityHash,
  computeDecisionHash,
  computeTimingHash,
  computeLogicHash,
  deepFreeze,
  stableStringify,
} = require("../../../../src/ai-observer/debug-record");
const {
  createSessionEvent,
  normalizeStartSessionRequest,
  SESSION_EVENT_TYPES,
} = require("../contracts");
const { getVoiceProfile, isConsentedLocalVoiceProfile } = require("../voice-clone/registry");
const { createClockSource } = require("./clock-source");

const VOICE_SAMPLE_CHUNKS = 3;
const SESSION_STATES = Object.freeze({
  CREATED: "created",
  WARMING: "warming",
  HEALTHY: "healthy",
  DEGRADED: "degraded",
  FAIL_CLOSED: "fail_closed",
  STOPPED: "stopped",
});

class UniversalLiveSession extends EventEmitter {
  constructor(request, options = {}) {
    super();
    this.config = resolveCoreConfig(options.config || {});
    this.request = normalizeStartSessionRequest(request);
    this.id = randomUUID();
    this.createdAt = new Date().toISOString();
    this.tempDir = path.join(this.config.tempDir, "sessions", this.id);
    this.sttEngine = options.sttEngine || new HybridSttEngine(this.config);
    this.translationEngine = options.translationEngine || new HybridTranslationEngine(this.config);
    this.speechEngine = options.speechEngine || new TieredSpeechEngine(this.config);
    this.separator = options.separator || new AudioSeparator(this.config);
    this.prosodyEngine = options.prosodyEngine || new ProsodyEngine(this.config);
    this.processingQueue = Promise.resolve();
    this.recentEvents = [];
    this.debugEventsFull = [];
    this.debugEventsCompact = [];
    this.debugEventsFullRaw = [];
    this.debugEventsCompactRaw = [];
    this.debugReplayComparisons = new Map();
    this.debugMode = options.debugMode || "compact";
    this.temporalIdentityOptions = resolveTemporalIdentityConfig(options.temporalIdentityOptions);
    this.lastTranslatedText = "";
    this.chunkSequence = 0;
    this.stopped = false;
    this.voiceSampleChunks = [];
    this.voiceSampleReady = false;
    this.voiceSamplePath = null;
    this.state = SESSION_STATES.CREATED;

    // STRICT: Clock mode must be explicitly specified
    // No silent defaults - prevents accidental mixing of live/replay
    const clockMode = options.clockMode || "live";
    this.clock = options.clock || createClockSource(clockMode, options.clockConfig || {});

    this.debugTimeNormalizer = new EventTimeNormalizer({
      sessionOrigin: this.clock.getNow(),
      defaultMode: "observer",
    });
    this.lastDebugSessionTime = -1;
    this.debugEventSequence = 0; // Tracks arrival order for stable sorting
    this.health = {
      sessionState: this.state,
      failClosed: false,
      failClosedReason: "",
      micPath: { status: "idle", message: "Waiting to start" },
      speakerPath: { status: "idle", message: "Waiting to start" },
      routing: { ok: this.request.sessionKind === "browser_debug", diagnostics: [] },
      models: { stt: "pending", translation: "pending", tts: "pending" },
      lastLatencyMs: null,
    };
  }

  async start() {
    await fs.mkdir(this.tempDir, { recursive: true });
    this._setState(SESSION_STATES.WARMING, "Preparing fail-closed session");
    await this._validateStartup();

    this.publish(SESSION_EVENT_TYPES.ROUTING_STATE, {
      routeProfileId: this.request.routeProfileId,
      inputDeviceId: this.request.inputDeviceId,
      outputDeviceId: this.request.outputDeviceId,
      sessionKind: this.request.sessionKind,
      routing: this.health.routing,
    });

    this._setState(SESSION_STATES.HEALTHY, `Session ready: ${this.request.sourceLanguage} -> ${this.request.targetLanguage}`);
  }

  getSnapshot() {
    return {
      id: this.id,
      createdAt: this.createdAt,
      request: this.request,
      events: this.recentEvents,
      health: this.health,
      state: this.state,
    };
  }

  getDebugEvents(mode = this.debugMode) {
    const records = mode === "full" ? this.debugEventsFull : this.debugEventsCompact;
    return [...records];
  }

  getDebugEvent(eventId, mode = this.debugMode) {
    return this.getDebugEvents(mode).find((event) => event.id === eventId) || null;
  }

  getDebugNormalizationTrace(eventId, mode = this.debugMode) {
    return this.getDebugEvent(eventId, mode)?.timing?.normalizationTrace || null;
  }

  getReplayComparison(eventId) {
    return (
      this.debugReplayComparisons.get(eventId) || {
        supported: false,
        eventId,
        message: "Replay comparison is not wired for live sessions yet.",
      }
    );
  }

  async enqueueChunk({ audioBuffer, fileExtension, analysis }) {
    if (this.stopped) {
      throw new Error("Session is already stopped.");
    }

    if (this.state === SESSION_STATES.FAIL_CLOSED) {
      return { chunkNumber: this.chunkSequence, dropped: true, failClosed: true };
    }

    const chunkNumber = ++this.chunkSequence;
    const chunkPath = path.join(this.tempDir, `chunk-${chunkNumber}.${fileExtension || "wav"}`);
    await fs.writeFile(chunkPath, audioBuffer);

    this.processingQueue = this.processingQueue
      .then(() => this.processChunk({ chunkNumber, chunkPath, analysis }))
      .catch((error) => {
        this._failClosed(error instanceof Error ? error.message : String(error), chunkNumber);
      });

    return { chunkNumber };
  }

  async stop() {
    if (this.stopped) return;
    this.stopped = true;
    await this.processingQueue.catch(() => {});
    this.sttEngine.stop();
    this.translationEngine.stop();
    this.separator.stop();
    this.prosodyEngine.stop();
    this.speechEngine.stop?.();
    await fs.rm(this.tempDir, { recursive: true, force: true }).catch(() => {});
    this._setState(SESSION_STATES.STOPPED, "Session stopped");
  }

  async processChunk({ chunkNumber, chunkPath, analysis }) {
    const startedAt = this.clock.getNow();
    if (this.state === SESSION_STATES.FAIL_CLOSED) {
      return;
    }

    try {
      this.publish(SESSION_EVENT_TYPES.STATUS, {
        message: `Processing chunk ${chunkNumber}`,
        chunkNumber,
      });

      const speechPath = chunkPath.replace(/\.\w+$/, "-speech.wav");
      const bgPath = chunkPath.replace(/\.\w+$/, "-bg.wav");
      let audioForStt = chunkPath;
      let hasSpeech = true;

      if (chunkPath.endsWith(".wav")) {
        try {
          const sepResult = await this.separator.separate({
            audioPath: chunkPath,
            speechPath,
            bgPath,
          });
          hasSpeech = sepResult.has_speech;
          if (hasSpeech) {
            audioForStt = speechPath;
          }
        } catch {
          this._setPathStatus("speakerPath", "degraded", "Speech separation unavailable; continuing with raw audio");
        }
      }

      if (!hasSpeech) {
        this._setPathStatus("speakerPath", "healthy", "Background audio preserved without speech leakage");
        this._recordLatency(chunkNumber, startedAt);
        return;
      }

      let prosodyFeatures = null;
      if (this.request.preserveEmotion && audioForStt.endsWith(".wav")) {
        try {
          prosodyFeatures = await this.prosodyEngine.extractProsody(audioForStt);
          this.speechEngine.setProsody(prosodyFeatures);
        } catch {
          this._setPathStatus("speakerPath", "degraded", "Prosody extraction unavailable; continuing");
        }
      }

      if (!this.voiceSampleReady && chunkNumber <= VOICE_SAMPLE_CHUNKS) {
        this.voiceSampleChunks.push(audioForStt);
        if (this.voiceSampleChunks.length >= VOICE_SAMPLE_CHUNKS) {
          await this._buildVoiceSample();
        }
      }

      const transcription = await this.sttEngine.transcribeChunk({
        audioPath: audioForStt,
        sourceLanguage: this.request.autoDetectSource ? "auto" : this.request.sourceLanguage,
        targetLanguage: this.request.targetLanguage,
        onlinePolicy: this.request.onlinePolicy,
      });
      this.health.models.stt = transcription.backend || "offline";
      const transcript = (transcription.transcript || "").trim();

      if (!transcript) {
        this._setPathStatus("micPath", "healthy", "Silence detected");
        this._recordLatency(chunkNumber, startedAt);
        return;
      }

      this.publish(SESSION_EVENT_TYPES.PARTIAL_TRANSCRIPT, {
        chunkNumber,
        transcript,
        detectedLanguage: transcription.detected_language || this.request.sourceLanguage,
        backend: transcription.backend || "stt",
      });

      const translation = await this.translationEngine.translate({
        transcript,
        whisperTranslation: transcription.translated_text,
        detectedLanguage: transcription.detected_language,
        sourceLanguage: this.request.sourceLanguage,
        targetLanguage: this.request.targetLanguage,
        onlinePolicy: this.request.onlinePolicy,
      });
      this.health.models.translation = translation.backend || "offline";

      const translatedText = (translation.translatedText || "").trim();
      this.publish(SESSION_EVENT_TYPES.FINAL_TRANSLATION, {
        chunkNumber,
        transcript,
        translatedText,
        detectedLanguage: transcription.detected_language || this.request.sourceLanguage,
        backend: translation.backend,
      });

      if (!translatedText) {
        this._failClosed("Translation produced no output; preserving silence instead of leaking original audio", chunkNumber);
        return;
      }

      if (translatedText !== this.lastTranslatedText) {
        this.lastTranslatedText = translatedText;
        const voiceProfile = await getVoiceProfile(this.config, this.request.voiceProfileId);
        const effectiveVoiceProfile = isConsentedLocalVoiceProfile(voiceProfile) ? voiceProfile : null;

        this.publish(SESSION_EVENT_TYPES.TTS_STARTED, {
          chunkNumber,
          translatedText,
          voiceProfileId: effectiveVoiceProfile?.id || "generic:offline-default",
        });

        await this.speechEngine.speak(translatedText, {
          onlinePolicy: this.request.onlinePolicy,
          language: this.request.targetLanguage,
          outputDeviceName: this.request.outputDeviceId,
          voiceProfile: effectiveVoiceProfile,
          prosody: prosodyFeatures,
          analysis,
          transcript,
          preserveEmotion: this.request.preserveEmotion,
        });
        this.health.models.tts = effectiveVoiceProfile ? "xtts" : "generic-offline";

        this.publish(SESSION_EVENT_TYPES.TTS_FINISHED, {
          chunkNumber,
          translatedText,
          voiceProfileId: effectiveVoiceProfile?.id || "generic:offline-default",
        });
      }

      this._setPathStatus("micPath", "healthy", "Translated speech delivered");
      this._setPathStatus("speakerPath", "healthy", "Translated audio output active");
      this._recordLatency(chunkNumber, startedAt);
    } finally {
      const base = chunkPath.replace(/\.\w+$/, "");
      await Promise.all([
        fs.rm(chunkPath, { force: true }),
        fs.rm(`${base}-speech.wav`, { force: true }),
        fs.rm(`${base}-bg.wav`, { force: true }),
      ]).catch(() => {});
    }
  }

  async _validateStartup() {
    if (this.request.sessionKind === "browser_debug") {
      this.health.routing = {
        ok: true,
        diagnostics: ["Browser debug sessions do not require native fail-closed routing."],
      };
      this.publish(SESSION_EVENT_TYPES.HEALTH, { health: this.health });
      return;
    }

    const topology = await listDeviceTopology(this.config).catch((error) => ({
      inputDevices: [],
      outputDevices: [],
      routeProfiles: [],
      diagnostics: [error.message],
    }));

    const routing = validateRouteProfile({ request: this.request, topology });
    this.health.routing = routing;
    if (!routing.ok) {
      this._failClosed(routing.diagnostics.join(" "), null);
      throw new Error(routing.diagnostics.join(" "));
    }

    this.publish(SESSION_EVENT_TYPES.HEALTH, { health: this.health });
  }

  async _buildVoiceSample() {
    const sampleSrc = this.voiceSampleChunks[0];
    if (!sampleSrc) return;
    try {
      const sampleDest = path.join(this.tempDir, "voice-sample.wav");
      await fs.copyFile(sampleSrc, sampleDest);
      this.voiceSamplePath = sampleDest;
      this.voiceSampleReady = true;
      this.speechEngine.setVoiceSample(sampleDest);
      this.publish(SESSION_EVENT_TYPES.STATUS, {
        message: "Voice sample captured; consented clone can be activated when a local profile is present",
      });
    } catch {
      this._setPathStatus("micPath", "degraded", "Voice sample capture unavailable");
    }
  }

  _recordLatency(chunkNumber, startedAt) {
    const latencyMs = this.clock.getNow() - startedAt;
    this.health.lastLatencyMs = latencyMs;
    this.publish(SESSION_EVENT_TYPES.LATENCY_SAMPLE, {
      chunkNumber,
      latencyMs,
    });
  }

  _setPathStatus(pathKey, status, message) {
    this.health[pathKey] = { status, message };
    if (status === "degraded" && this.state === SESSION_STATES.HEALTHY) {
      this._setState(SESSION_STATES.DEGRADED, message);
    }
    if (status === "healthy" && this.state !== SESSION_STATES.FAIL_CLOSED) {
      const bothHealthy = ["micPath", "speakerPath"].every((key) => this.health[key].status === "healthy");
      if (bothHealthy) {
        this._setState(SESSION_STATES.HEALTHY, "Both translation paths are healthy");
      }
    }
    this.publish(SESSION_EVENT_TYPES.HEALTH, { health: this.health });
  }

  _setState(nextState, message) {
    this.state = nextState;
    this.health.sessionState = nextState;
    this.publish(SESSION_EVENT_TYPES.STATUS, { message });
    this.publish(SESSION_EVENT_TYPES.HEALTH, { health: this.health });
  }

  _failClosed(reason, chunkNumber) {
    this.health.failClosed = true;
    this.health.failClosedReason = reason;
    this.health.micPath = { status: "fail_closed", message: reason };
    this.health.speakerPath = { status: "fail_closed", message: reason };
    this._setState(SESSION_STATES.FAIL_CLOSED, "Fail-closed engaged: translated silence only");
    this.publish(SESSION_EVENT_TYPES.ERROR, {
      chunkNumber: chunkNumber ?? undefined,
      message: reason,
      failClosed: true,
    });
  }

  publish(type, payload = {}) {
    const event = createSessionEvent(type, { sessionId: this.id, state: this.state, ...payload });
    this.recentEvents.push(event);
    if (this.recentEvents.length > 100) this.recentEvents.shift();
    this._recordDebugEvent(event);
    this.emit("event", event);
  }

  _recordDebugEvent(event) {
    const sequence = this.debugEventsFull.length;
    const arrivalIndex = this.debugEventSequence++;
    const systemTime = Date.parse(event.timestamp) || this.clock.getNow();
    const sessionTime = this._getSessionTimeMs();
    const normalizedEvent = this.debugTimeNormalizer.normalizeEvent(
      {
        ...event,
        id: `${this.id}-debug-${sequence}`,
        sequence,
        arrivalIndex, // Track raw insertion order
        lineageId: this._resolveDebugLineageId(event),
      },
      {
        sessionId: this.id,
        sequence,
        systemTime,
        observerTime: systemTime,
        utteranceTime: Number.isFinite(event.chunkNumber) ? event.chunkNumber * 100 : undefined,
        quotaTime: this._extractQuotaTime(event),
        confidence: Number.isFinite(event.confidence) ? event.confidence : undefined,
        normalizationMode: this._resolveDebugNormalizationMode(event),
      }
    );
    const sourceEventIds = this._resolveSourceEventIds(event);
    const contributions = this._buildContributions(normalizedEvent);
    const dominantDomain = this._getDominantDomain(contributions);
    const timing = {
      raw: normalizedEvent.timing?.rawTimes || {},
      rebased: normalizedEvent.timing?.rebasedTimes || {},
      normalizationTrace: normalizedEvent.timing?.normalizationTrace || {},
      skew: normalizedEvent.timing?.skew || {},
      coherenceScore: normalizedEvent.timing?.coherenceScore || 0,
      flags: {
        normalizedTimeBackward: false,
        chunkNumber: event.chunkNumber ?? null,
      },
    };
    const weights = { ...(normalizedEvent.timing?.normalizationWeights || {}) };
    const confidences = { ...(normalizedEvent.timing?.confidences || {}) };
    const ignoredDomains =
      normalizedEvent.timing?.normalizationTrace?.ignoredDomains?.map((domain) => domain.domain) || [];
    const ignoredDomainsDecision = (
      normalizedEvent.timing?.normalizationTrace?.ignoredDomains || []
    ).map((domain) => ({
      domain: domain.domain,
      reason: domain.reason || "unspecified",
    }));
    const causalityKey = {
      sourceEventIds,
      transformation: `normalize.${NORMALIZATION_VERSION}`,
      dependencyHash: computeDependencyHash({
        sourceEventIds,
        transformation: `normalize.${NORMALIZATION_VERSION}`,
        eventType: normalizedEvent.type,
        timing,
        weights,
        confidences,
      }),
    };

    const recordWithoutHash = {
      id: normalizedEvent.id,
      type: normalizedEvent.type,
      schemaVersion: SCHEMA_VERSION,
      normalizationVersion: NORMALIZATION_VERSION,
      rawTime: systemTime,
      sessionTime,
      normalizedTime: normalizedEvent.timing?.normalizedTime || 0,
      arrivalIndex, // Raw insertion order for stable sorting
      causalityKey,
      timing,
      weights,
      confidences,
      ignoredDomains,
      ignoredDomainsDecision,
      dominantDomain,
      contributions,
      flags: [],
      createdAt: this.clock.getNow(),
    };

    this._storeDebugRecord(recordWithoutHash, "full");

    const compactRecord = this._cloneDebugRecord(recordWithoutHash);
    this._storeDebugRecord(compactRecord, "compact");
  }

  _resolveDebugLineageId(event) {
    if (event.utteranceId) {
      return event.utteranceId;
    }
    if (Number.isFinite(event.chunkNumber)) {
      return `chunk-${event.chunkNumber}`;
    }
    return `${event.type}-session`;
  }

  _resolveDebugNormalizationMode(event) {
    switch (event.type) {
      case SESSION_EVENT_TYPES.PARTIAL_TRANSCRIPT:
      case SESSION_EVENT_TYPES.PARTIAL_TRANSLATION:
      case SESSION_EVENT_TYPES.FINAL_TRANSLATION:
        return "utterance";
      case SESSION_EVENT_TYPES.LATENCY_SAMPLE:
        return "capture";
      default:
        return "observer";
    }
  }

  _extractQuotaTime(event) {
    if (Number.isFinite(event.expectedDelayMs)) {
      return {
        delayMs: event.expectedDelayMs,
      };
    }
    return undefined;
  }

  _getSessionTimeMs() {
    const elapsedMs = this.clock.getHighResTimeMs();
    const monotonicSessionTime = this.clock.enforceMonotonic(elapsedMs);
    this.lastDebugSessionTime = monotonicSessionTime;
    return monotonicSessionTime;
  }

  _resolveSourceEventIds(event) {
    if (Number.isFinite(event.chunkNumber)) {
      const matching = this.debugEventsFull
        .filter((record) => record.timing?.flags?.chunkNumber === event.chunkNumber)
        .slice(-4)
        .map((record) => record.id);
      return matching;
    }

    if (event.type === SESSION_EVENT_TYPES.STATUS || event.type === SESSION_EVENT_TYPES.HEALTH) {
      return this.debugEventsFull.slice(-2).map((record) => record.id);
    }

    return [];
  }

  _buildContributions(normalizedEvent) {
    const contributions = {};
    const domains =
      normalizedEvent.timing?.normalizationTrace?.contributingDomains || [];

    for (const domain of domains) {
      contributions[domain.domain] = Number(
        (domain.rebasedTime * domain.effectiveWeight).toFixed(6)
      );
    }

    return contributions;
  }

  _getDominantDomain(contributions) {
    const entries = Object.entries(contributions);
    if (entries.length === 0) {
      return "none";
    }

    return entries.reduce((winner, current) =>
      Math.abs(current[1]) > Math.abs(winner[1]) ? current : winner
    )[0];
  }

  _finalizeDebugRecord(recordWithoutHash) {
    const draft = {
      ...recordWithoutHash,
      flags: [...recordWithoutHash.flags],
      ignoredDomains: [...recordWithoutHash.ignoredDomains],
      ignoredDomainsDecision: [...recordWithoutHash.ignoredDomainsDecision],
      contributions: { ...recordWithoutHash.contributions },
      weights: { ...recordWithoutHash.weights },
      confidences: { ...recordWithoutHash.confidences },
      timing: {
        ...recordWithoutHash.timing,
        raw: { ...recordWithoutHash.timing.raw },
        rebased: { ...recordWithoutHash.timing.rebased },
        normalizationTrace: { ...recordWithoutHash.timing.normalizationTrace },
        skew: { ...recordWithoutHash.timing.skew },
        flags: { ...recordWithoutHash.timing.flags },
      },
      causalityKey: {
        ...recordWithoutHash.causalityKey,
        sourceEventIds: [...recordWithoutHash.causalityKey.sourceEventIds],
      },
    };

    return deepFreeze({
      ...draft,
      integrityHash: computeIntegrityHash(draft),
      decisionHash: computeDecisionHash(draft),
      timingHash: computeTimingHash(draft),
      logicHash: computeLogicHash(draft),
    });
  }

  _storeDebugRecord(record, mode) {
    const rawTargetRecords = mode === "full" ? this.debugEventsFullRaw : this.debugEventsCompactRaw;

    if (mode === "compact" && this._shouldDropDebugRecord(record)) {
      return;
    }

    if (mode === "compact") {
      this._applyDuplicateCausalityCompaction(record, rawTargetRecords);
      this._applyPartialCompaction(record, rawTargetRecords);
    }

    rawTargetRecords.push(this._cloneDebugRecord(record));

    while (rawTargetRecords.length > MAX_DEBUG_EVENTS) {
      rawTargetRecords.shift();
    }

    this._rebuildDebugRecords(mode);
  }

  _rebuildDebugRecords(mode) {
    const rawRecords = mode === "full" ? this.debugEventsFullRaw : this.debugEventsCompactRaw;
    const stabilizedRecords = stabilizeTemporalIdentities(
      rawRecords.map((record) => this._cloneDebugRecord(record)),
      this.temporalIdentityOptions
    );
    const finalizedRecords = [];

    for (const stabilizedRecord of stabilizedRecords) {
      const draft = this._cloneDebugRecord(stabilizedRecord);
      this._enforceTimeOrder(finalizedRecords[finalizedRecords.length - 1] || null, draft);
      this._checkBrokenChain(draft, finalizedRecords);
      finalizedRecords.push(this._finalizeDebugRecord(draft));
    }

    if (mode === "full") {
      this.debugEventsFull = finalizedRecords;
    } else {
      this.debugEventsCompact = finalizedRecords;
    }
  }

  _cloneDebugRecord(record) {
    return JSON.parse(JSON.stringify(record));
  }

  _enforceTimeOrder(previousRecord, currentRecord) {
    if (!previousRecord) {
      return;
    }

    if (currentRecord.normalizedTime < previousRecord.normalizedTime) {
      currentRecord.flags.push("TIME_REGRESSION");
    }
  }

  _checkBrokenChain(record, targetRecords) {
    const sourceEventIds = record.causalityKey?.sourceEventIds || [];
    if (sourceEventIds.length === 0) {
      return;
    }

    const seenIds = new Set(targetRecords.map((event) => event.id));
    const missingDependencies = sourceEventIds.filter((id) => !seenIds.has(id));
    if (missingDependencies.length > 0) {
      record.flags.push("BROKEN_CHAIN");
    }
  }

  _shouldDropDebugRecord(record) {
    const contributions = Object.values(record.contributions || {}).map((value) => Math.abs(value));
    const maxContribution = contributions.length > 0 ? Math.max(...contributions) : 0;
    if (maxContribution < 0.05) {
      return true;
    }
 
    return false;
  }

  _applyDuplicateCausalityCompaction(record, targetRecords) {
    const key = this._getCausalitySignature(record);
    const nextRecords = targetRecords.filter(
      (candidate) => this._getCausalitySignature(candidate) !== key
    );
    targetRecords.length = 0;
    targetRecords.push(...nextRecords);
  }

  _applyPartialCompaction(record, targetRecords) {
    if (
      record.type !== SESSION_EVENT_TYPES.PARTIAL_TRANSCRIPT &&
      record.type !== SESSION_EVENT_TYPES.PARTIAL_TRANSLATION
    ) {
      return;
    }

    const partials = targetRecords.filter((candidate) => candidate.type === record.type);
    if (partials.length < 1) {
      return;
    }

    const idsToKeep = new Set(partials.slice(-1).map((candidate) => candidate.id));
    const nextRecords = targetRecords.filter(
      (candidate) => candidate.type !== record.type || idsToKeep.has(candidate.id)
    );
    targetRecords.length = 0;
    targetRecords.push(...nextRecords);
  }

  _getCausalitySignature(record) {
    return stableStringify({
      transformation: record.causalityKey?.transformation,
      sourceEventIds: record.causalityKey?.sourceEventIds || [],
    });
  }

  /**
   * Get a complete session dump including all debug events
   * @param {Object} options - Dump options
   * @param {string} options.mode - "full" or "compact" (default: current debugMode)
   * @param {number} options.limit - Max events to return (default: all)
   * @returns {Object} Complete dump payload
   */
  getDebugSessionDump(options = {}) {
    const mode = options.mode || this.debugMode;
    const limit = options.limit || Infinity;
    const records = this.getDebugEvents(mode).slice(-limit);

    // Compute session-level hashes
    const integrityHashes = records.map(r => r.integrityHash);
    const decisionHashes = records.map(r => r.decisionHash);
    const timingHashes = records.map(r => r.timingHash);
    const logicHashes = records.map(r => r.logicHash);

    const integritySessionHash = integrityHashes.length > 0
      ? require("crypto").createHash("sha256").update(integrityHashes.join("|")).digest("hex").slice(0, 16)
      : null;

    const uniqueDecisionHashes = [...new Set(decisionHashes)].sort();
    const decisionSessionHash = uniqueDecisionHashes.length > 0
      ? require("crypto").createHash("sha256").update(uniqueDecisionHashes.join("|")).digest("hex").slice(0, 16)
      : null;

    const timingSessionHash = timingHashes.length > 0
      ? require("crypto").createHash("sha256").update(timingHashes.join("|")).digest("hex").slice(0, 16)
      : null;

    const uniqueLogicHashes = [...new Set(logicHashes)].sort();
    const logicSessionHash = uniqueLogicHashes.length > 0
      ? require("crypto").createHash("sha256").update(uniqueLogicHashes.join("|")).digest("hex").slice(0, 16)
      : null;

    return {
      sessionId: this.id,
      createdAt: this.createdAt,
      mode,
      request: this.request,
      state: this.state,
      health: this.health,
      recordCount: records.length,
      totalRecordsAvailable: this.getDebugEvents(mode).length,
      integritySessionHash,
      decisionSessionHash,
      timingSessionHash,
      logicSessionHash,
      events: records.map((record) => ({
        id: record.id,
        type: record.type,
        sequence: records.indexOf(record),
        arrivalIndex: record.arrivalIndex,
        rawTime: record.rawTime,
        sessionTime: record.sessionTime,
        normalizedTime: record.normalizedTime,
        dominantDomain: record.dominantDomain,
        contributions: record.contributions,
        temporalIdentity: record.temporalIdentity || null,
        flags: record.flags,
        timing: {
          coherenceScore: record.timing?.coherenceScore,
          skew: record.timing?.skew,
        },
        causalityKey: record.causalityKey,
        integrityHash: record.integrityHash,
        decisionHash: record.decisionHash,
        timingHash: record.timingHash,
        logicHash: record.logicHash,
      })),
    };
  }

  /**
   * Persist session dump to filesystem
   * @param {string} dumpDir - Directory to write dump to
   * @param {Object} options - Dump options (passed to getDebugSessionDump)
   * @returns {Promise<Object>} Details about persisted file
   */
  async persistDebugSessionDump(dumpDir, options = {}) {
    const dump = this.getDebugSessionDump(options);
    const mode = options.mode || this.debugMode;
    const filename = `${this.id}_${mode}_${Date.now()}.json`;
    const filepath = path.join(dumpDir, filename);

    await fs.mkdir(dumpDir, { recursive: true });
    await fs.writeFile(filepath, JSON.stringify(dump, null, 2));

    return {
      filepath,
      filename,
      size: (await fs.stat(filepath)).size,
      events: dump.recordCount,
    };
  }

  /**
   * Get comparison between live and deterministic replay modes
   * (currently unsupported; would require replay infrastructure)
   * @param {string} eventId - Event to compare
   * @returns {Object} Comparison result or placeholder
   */
  getReplayComparisonDetailed(eventId) {
    return {
      supported: false,
      eventId,
      message:
        "Replay comparison requires recorded timestamps and deterministic replay infrastructure. Use persistDebugSessionDump() to capture live data for manual analysis.",
      suggestion:
        "Implement DeterministicClockSource replay by (1) recording live timestamps, (2) creating identical session with same input, (3) comparing sessionHash values",
    };
  }
}

module.exports = { UniversalLiveSession, SESSION_STATES };
