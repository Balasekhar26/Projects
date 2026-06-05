class PlaybackController {
  constructor({
    speaker,
    debounceMs = 120,
    staleMs = 300,
    maxPlaybackMs = 700,
    confidenceInterruptDelta = 0.15,
    continuationDelayMs = 180,
    continuationWindowMs = 800,
    continuationPollMs = 80,
    continuationGapMs = 250,
    preSpeechWindowMs = 180,
  } = {}) {
    this.speaker = speaker;
    this.debounceMs = debounceMs;
    this.staleMs = staleMs;
    this.maxPlaybackMs = maxPlaybackMs;
    this.confidenceInterruptDelta = confidenceInterruptDelta;
    this.continuationDelayMs = continuationDelayMs;
    this.continuationWindowMs = continuationWindowMs;
    this.continuationGapMs = continuationGapMs;
    this.preSpeechWindowMs = preSpeechWindowMs;

    this.currentJob = null;
    this.currentPriority = 0;
    this.currentSegmentId = null;
    this.currentConfidence = 0;
    this.startedAt = 0;
    this.lastUpdateAt = 0;
    this.lastMeaningCommitAt = 0;
    this.lastInterruptAt = 0;
    this.lastAudioEnergyAt = 0;
    this.lastContinuationAt = 0;
    this.lastSpokenByPhrase = new Map();
    this.continuationRepeatCount = 0;
    this.lastProsody = {
      tempo: 1.0,
      energy: 1.0,
      pitchBias: 0,
      cadence: 0.5,
      emotionalTilt: 0,
      mode: "tentative",
      updatedAt: 0,
    };
    this.activePhraseChain = {
      lastPhraseId: null,
      continuityScore: 0,
      updatedAt: 0,
    };

    this.tentativeTimer = null;
    this.pendingTentative = null;
    this.currentContinuationJob = null;
    this.currentPresenceJob = null;
    this.continuationActive = false;
    this.presenceActive = false;
    this.presence = {
      active: false,
      lastAudioAt: Date.now(),
      lastPresenceAt: 0,
    };
    this.interrupt = {
      pending: false,
      lastSignalAt: 0,
    };
    this.pendingSpeechDetection = null;
    this.continuationSuppressedUntil = 0;
    this.anticipatedInterruptUntil = 0;
    this.lastEnergyAt = Date.now();
    this.pipelineActive = false;
    this.continuationInterval = setInterval(() => {
      void this._maybePlayContinuation();
    }, continuationPollMs);
    this.continuationInterval.unref?.();
    this.startPresenceLoop();
  }

  enqueue(event) {
    this.pipelineActive = true;
    this._signalInterrupt(event);
    if (event?.mode === "commit") {
      this.cancelAllTentatives();
    } else {
      this._stopPresence();
    }
    this._stopContinuation();
    this.pendingSpeechDetection = null;

    if (event?.mode === "tentative") {
      this._handleTentative(event);
      return;
    }

    void this._process(event);
  }

  _handleTentative(event) {
    this.pendingTentative = event;
    if (this.tentativeTimer) {
      return;
    }

    this.tentativeTimer = setTimeout(() => {
      const pending = this.pendingTentative;
      this.pendingTentative = null;
      this.tentativeTimer = null;
      if (pending) {
        void this._process(pending);
      }
    }, this.debounceMs);
  }

  async _process(event) {
    this._signalInterrupt(event);
    const now = Date.now();
    if (now - this.lastInterruptAt < 200) {
      setTimeout(() => {
        void this._process(event);
      }, 100);
      return;
    }

    const incoming = this._applyDeltaSpeech(this._normalize(event));
    if (!incoming || !this._shouldInterrupt(incoming)) {
      return;
    }

    if (incoming.mode === "commit") {
      await this._playCommit(incoming);
      return;
    }

    await this._playNonCommit(incoming);
  }

  async _playNonCommit(incoming) {
    this._anticipateInterrupt(incoming);

    const overlapMs = incoming.preemptNow
      ? 6
      : this._isHardInterrupt(incoming)
        ? 10
        : this._computeOverlapMs({
          incomingMode: incoming.mode,
          lastProsody: this.lastProsody,
          continuityScore: incoming.continuityScore,
        });

    await this._interruptCurrent(overlapMs, incoming.preemptNow ? 50 : 100);
    this.interrupt.pending = false;
    this._beginPlayback(incoming);
  }

  async _playCommit(incoming) {
    this._stopPresence();
    this._stopContinuation();
    this._anticipateInterrupt({
      ...incoming,
      preemptNow: true,
    });
    await this._interruptCurrent(6, 35);
    this.interrupt.pending = false;
    this._beginPlayback({
      ...incoming,
      entryProfile: {
        attack: "fast",
        volumeBoost: Math.max(1.2, finiteOr(incoming.volumeBoost, 1.0)),
        presenceCut: true,
        startOffsetMs: 5,
        pitchLiftCents: 5,
        tempoScale: 0.98,
      },
    });
  }

  _beginPlayback(incoming) {
    const job = this.speaker.createSpeechJob(incoming);
    this.currentJob = job;
    this.continuationRepeatCount = 0;
    this.currentPriority = incoming.priority;
    this.currentSegmentId = incoming.segmentId;
    this.currentConfidence = incoming.confidence;
    this.startedAt = Date.now();
    this.lastUpdateAt = Date.now();
    this.lastInterruptAt = Date.now();
    this.lastAudioEnergyAt = this.lastInterruptAt;
    this.lastEnergyAt = this.lastInterruptAt;
    if (incoming.mode === "commit") {
      this.continuationSuppressedUntil = this.lastInterruptAt + 120;
      this.lastMeaningCommitAt = this.lastInterruptAt;
    }

    job.onStart = () => {
      this._onAudioStart();
      this.startedAt = Date.now();
      this.lastUpdateAt = Date.now();
      this._recordProsody(incoming);
      incoming.onAudibleStart?.();
    };

    job.onEnd = () => {
      if (this.currentJob === job) {
        this._markAudioBoundary();
        incoming.onAudibleEnd?.();
        this._resetState();
      }
    };

    void job.play().catch(() => {
      if (this.currentJob === job) {
        this._resetState();
      }
    });
  }

  _shouldInterrupt(incoming) {
    if (!this.currentJob) {
      return true;
    }

    const now = Date.now();

    if (incoming.priority > this.currentPriority) {
      return true;
    }

    if (incoming.mode === "commit") {
      return true;
    }

    if (incoming.confidence > this.currentConfidence + this.confidenceInterruptDelta) {
      return true;
    }

    if (incoming.confidence < 0.5 && incoming.priority <= this.currentPriority) {
      return false;
    }

    if (
      incoming.priority === this.currentPriority &&
      incoming.supersedesSegmentId &&
      incoming.supersedesSegmentId === this.currentSegmentId
    ) {
      return true;
    }

    if (now - this.lastUpdateAt > this.staleMs) {
      return true;
    }

    if (now - this.startedAt > this.maxPlaybackMs) {
      return true;
    }

    return false;
  }

  async _interruptCurrent(overlapMs = 0) {
    return this._interruptCurrentWithFade(overlapMs, 100);
  }

  async _interruptCurrentWithFade(overlapMs = 0, fadeOutMs = 100) {
    const job = this.currentJob;
    if (!job) {
      return;
    }

    try {
      const fadePromise = job.fadeOut ? job.fadeOut(fadeOutMs) : delay(fadeOutMs);
      fadePromise.catch(() => {});
      job.abort();
      this._resetState();
      if (overlapMs > 0) {
        await delay(overlapMs);
      }
      return;
    } catch {}
    this._resetState();
  }

  _resetState() {
    this.currentJob = null;
    this.currentPriority = 0;
    this.currentSegmentId = null;
    this.currentConfidence = 0;
    this.startedAt = 0;
    this.lastUpdateAt = 0;
  }

  _recordProsody(job) {
    this.lastProsody = {
      tempo: finiteOr(job?.tempo, 1.0),
      energy: finiteOr(job?.volumeBoost, 1.0),
      pitchBias: finiteOr(job?.pitchCents, 0),
      cadence: clamp(finiteOr(job?.cadence, 0.5), 0, 1),
      emotionalTilt: clamp(finiteOr(job?.emotionalTilt, 0), -1, 1),
      expectedPauseMs: finiteOr(job?.expectedPauseMs, this.lastProsody.expectedPauseMs || 220),
      mode: job?.mode || "tentative",
      updatedAt: Date.now(),
    };
    this.activePhraseChain = {
      lastPhraseId: job?.phraseId ?? this.activePhraseChain.lastPhraseId,
      continuityScore: clamp(finiteOr(job?.continuityScore, 0), 0, 1),
      updatedAt: Date.now(),
    };
  }

  _computeOverlapMs({ incomingMode, lastProsody, continuityScore = 0 }) {
    if (incomingMode === "commit") {
      return 4;
    }

    let base = 28;

    if (incomingMode === "tentative") {
      base += 5;
    }

    const tempoFactor = (1.0 - finiteOr(lastProsody?.tempo, 1.0)) * 40;
    const energyFactor = (1.0 - finiteOr(lastProsody?.energy, 1.0)) * 20;
    const continuityFactor = clamp(continuityScore, 0, 1) * 6;
    const jitter = (Math.random() * 4) - 2;

    base += tempoFactor + energyFactor + continuityFactor + jitter;

    return clamp(Math.round(base), 15, 45);
  }

  _isHardInterrupt(incoming) {
    if (!this.currentJob) {
      return false;
    }

    if (incoming.priority > this.currentPriority) {
      return true;
    }

    if (incoming.mode === "commit" && this.currentPriority < 3) {
      return true;
    }

    return false;
  }

  async _maybePlayContinuation() {
    if (
      this.continuationActive ||
      typeof this.speaker?.createContinuationJob !== "function"
    ) {
      return;
    }

    const now = Date.now();
    if (now < this.continuationSuppressedUntil) {
      return;
    }
    if (this._maybePlayPresence(now)) {
      return;
    }

    if (this.currentJob) {
      return;
    }

    const gapClass = this._classifyGap(now);
    if (!gapClass) {
      return;
    }

    const pipelineActive = now - this.lastUpdateAt < this.continuationWindowMs;
    const shouldContinue =
      pipelineActive &&
      now - this.lastContinuationAt >= this.continuationGapMs &&
      (
        gapClass.kind === "continuation"
          ? gapClass.gapMs > 180
          : now - this.lastAudioEnergyAt > this.continuationDelayMs
      );

    if (!shouldContinue) {
      return;
    }

    const job = this.speaker.createContinuationJob({
      kind: gapClass.kind,
      volumeBoost: gapClass.kind === "stretch"
        ? Math.max(0.58, 0.68 - (this.continuationRepeatCount * 0.04))
        : Math.max(0.7, 0.82 - (this.continuationRepeatCount * 0.05)),
      pitchCents: ((Math.random() * 4) - 2) + (this.continuationRepeatCount * 0.35),
      tempo: clamp(
        (gapClass.kind === "stretch" ? 0.99 : 0.98) +
          ((Math.random() * 0.04) - 0.02) -
          (this.continuationRepeatCount * 0.01),
        gapClass.kind === "stretch" ? 0.95 : 0.93,
        1.01
      ),
      cadence: finiteOr(this.lastProsody?.cadence, 0.5),
    });
    if (!job) {
      return;
    }

    this.continuationActive = true;
    this.currentContinuationJob = job;
    this.lastContinuationAt = now;
    this.continuationRepeatCount += 1;

    job.onStart = () => {
      this.lastAudioEnergyAt = Date.now();
      this.lastEnergyAt = this.lastAudioEnergyAt;
    };

    const finish = () => {
      if (this.currentContinuationJob === job) {
        this.currentContinuationJob = null;
        this.continuationActive = false;
      }
    };

    job.onEnd = () => {
      this.lastAudioEnergyAt = Date.now();
      this.lastEnergyAt = this.lastAudioEnergyAt;
      finish();
    };

    void job.play().catch(() => {
      finish();
    });
  }

  noteSpeechDetected({ chunkNumber, detectedAt, triggerAt, prosody } = {}) {
    this.pendingSpeechDetection = {
      chunkNumber,
      detectedAt: Number.isFinite(detectedAt) ? detectedAt : Date.now(),
      triggerAt: Number.isFinite(triggerAt) ? triggerAt : Date.now() + this.continuationDelayMs,
      prosody: prosody || null,
    };
  }

  noteAnticipatedInterrupt() {
    this.anticipatedInterruptUntil = Date.now() + 180;
    if (!this.currentJob) {
      return;
    }

    if (typeof this.currentJob.prepareSoftRelease === "function") {
      this.currentJob.prepareSoftRelease();
      return;
    }

    if (typeof this.currentJob.fadeOut === "function") {
      this.currentJob.fadeOut(50).catch(() => {});
    }
  }

  startPresenceLoop() {
    if (this._presenceLoop) {
      return;
    }

    this._presenceLoop = setInterval(() => {
      const now = Date.now();
      const silenceMs = now - this.presence.lastAudioAt;
      const pipelineAlive = this._isPresencePipelineActive(now);

      if (
        pipelineAlive &&
        !this.currentJob &&
        !this.continuationActive &&
        !this.presence.active &&
        this._canStartPresence(now) &&
        silenceMs > 120
      ) {
        this._startPresence();
        return;
      }

      if (!pipelineAlive || this.currentJob || this.continuationActive) {
        this._stopPresence();
      }
      if (!pipelineAlive) {
        this.pipelineActive = false;
      }
    }, 30);
    this._presenceLoop.unref?.();
  }

  _startPresence() {
    if (this.presence.active || typeof this.speaker?.playPresence !== "function") {
      return;
    }

    this.presence.active = true;
    this.presence.lastPresenceAt = Date.now();
    this.speaker.playPresence({
      energy: this._derivePresenceEnergy(),
      tempo: finiteOr(this.lastProsody?.tempo, 1.0),
      tilt: finiteOr(this.lastProsody?.emotionalTilt, 0),
      outputDeviceName: this.speaker?.config?.ttsOutputDeviceName,
    });
    this.presenceActive = true;
  }

  _maybePlayPresence(now) {
    if (
      this.currentJob ||
      this.continuationActive ||
      this.presence.active ||
      typeof this.speaker?.playPresence !== "function" ||
      !this.pendingSpeechDetection
    ) {
      return false;
    }

    const { triggerAt, detectedAt, prosody } = this.pendingSpeechDetection;
    if (now < triggerAt) {
      return false;
    }

    if (now - detectedAt > this.preSpeechWindowMs + 120) {
      this.pendingSpeechDetection = null;
      return false;
    }

    this.pendingSpeechDetection = null;
    this._startPresence();
    return true;
  }

  _classifyGap(now = Date.now()) {
    const lastBoundary = Math.max(this.lastAudioEnergyAt || 0, this.lastMeaningCommitAt || 0);
    if (!lastBoundary) {
      return null;
    }
    const gapMs = Math.max(0, now - lastBoundary);
    if (gapMs < 90) {
      return null;
    }
    if (gapMs <= 250) {
      return { kind: "stretch", gapMs };
    }
    return { kind: "continuation", gapMs };
  }

  _anticipateInterrupt(incoming) {
    if (!this.currentJob || typeof this.currentJob.fadeOut !== "function") {
      return;
    }

    const isRisingRevision =
      incoming.supersedesSegmentId &&
      incoming.supersedesSegmentId === this.currentSegmentId &&
      incoming.confidence >= this.currentConfidence + Math.max(this.confidenceInterruptDelta * 0.5, 0.08);
    const isCommitTakeover = incoming.mode === "commit" && this.currentPriority < incoming.priority;

    if (!isRisingRevision && !isCommitTakeover) {
      return;
    }

    const fadeMs = incoming.preemptNow ? 50 : isCommitTakeover ? 35 : 55;
    this.currentJob.fadeOut(fadeMs).catch(() => {});
  }

  _stopContinuation() {
    const job = this.currentContinuationJob;
    if (!job) {
      this.continuationActive = false;
      this.continuationRepeatCount = 0;
      return;
    }

    this.currentContinuationJob = null;
    this.continuationActive = false;
    this.continuationRepeatCount = 0;
    try {
      job.abort?.();
    } catch {}
  }

  _stopPresence() {
    if (!this.presence.active && !this.presenceActive) {
      return;
    }
    this.presence.active = false;
    this.presenceActive = false;
    try {
      this.speaker?.stopPresence?.();
    } catch {}
  }

  cancelAllTentatives() {
    this.pendingTentative = null;
    this._stopPresence();
    this._stopContinuation();
  }

  stop() {
    if (this.tentativeTimer) {
      clearTimeout(this.tentativeTimer);
      this.tentativeTimer = null;
    }
    if (this.continuationInterval) {
      clearInterval(this.continuationInterval);
      this.continuationInterval = null;
    }
    if (this._presenceLoop) {
      clearInterval(this._presenceLoop);
      this._presenceLoop = null;
    }
    this._stopPresence();
    this._stopContinuation();
    this.pendingSpeechDetection = null;
    void this._interruptCurrent(0);
  }

  _markAudioBoundary(at = Date.now()) {
    this.presence.lastAudioAt = at;
    this.lastAudioEnergyAt = at;
    this.lastEnergyAt = at;
  }

  _onAudioStart() {
    const now = Date.now();
    this._markAudioBoundary(now);
    this.lastContinuationAt = now;
    if (this.presence.active) {
      this._stopPresence();
    }
  }

  _derivePresenceEnergy() {
    const energy = finiteOr(this.lastProsody?.energy, 0.4);
    return clamp(energy * 0.7, 0.2, 0.6);
  }

  _isPresencePipelineActive(now = Date.now()) {
    const pendingSpeechAlive = this.pendingSpeechDetection && (now - this.pendingSpeechDetection.detectedAt) <= (this.preSpeechWindowMs + 120);
    return (
      (this.pipelineActive && now - this.lastUpdateAt < this.continuationWindowMs) ||
      Boolean(pendingSpeechAlive) ||
      Boolean(this.pendingTentative)
    );
  }

  _canStartPresence(now = Date.now()) {
    if (this.pendingSpeechDetection) {
      return now >= this.pendingSpeechDetection.triggerAt;
    }
    return true;
  }

  _signalInterrupt(event) {
    if (!this.currentJob || !event) {
      return;
    }

    const samePhraseRevision =
      event.supersedesSegmentId &&
      event.supersedesSegmentId === this.currentSegmentId;
    const strongerMode =
      (event.mode === "commit" && this.currentPriority < 3) ||
      (event.mode === "tentative" && this.currentPriority >= 2);
    const preemptNow = Boolean(event.preemptNow);

    if (!samePhraseRevision && !strongerMode && !preemptNow) {
      return;
    }

    const now = Date.now();
    if (now - this.interrupt.lastSignalAt < 40) {
      return;
    }

    this.interrupt.lastSignalAt = now;
    this.interrupt.pending = true;
    this.speaker?.preempt?.({
      aggressiveness: preemptNow ? 1 : event.mode === "commit" ? 0.95 : 0.72,
      durationMs: preemptNow ? 18 : event.mode === "commit" ? 22 : 25,
    });
  }

  _normalize(event) {
    const priorityMap = {
      commit: 3,
      tentative: 2,
      fallback: 1,
    };
    const continuityScore = this._deriveContinuityScore(event);
    const previousProsody = this.lastProsody;
    const emotionalTilt = lerp(previousProsody.emotionalTilt, detectTilt(event?.text || ""), 0.3);
    const baseStartupFadeMs = event?.mode === "commit" ? 30 : 50;
    const startupFadeMs = clamp(
      baseStartupFadeMs - Math.round(continuityScore * (event?.mode === "commit" ? 18 : 12)),
      20,
      90
    );
    const cadence = clamp(
      lerp(previousProsody.cadence, 0.45 + (continuityScore * 0.35), 0.35),
      0,
      1
    );
    const basePitchBias = event?.mode === "commit" ? -6 : event?.mode === "tentative" ? 4 : 0;
    const pitchCents = clamp(
      lerp(previousProsody.pitchBias, basePitchBias + (emotionalTilt * 26), 0.35),
      -45,
      45
    );

    return {
      ...event,
      priority: priorityMap[event?.mode] || 1,
      preemptNow: Boolean(event?.preemptNow),
      confidence: clampConfidence(event?.confidence),
      volumeBoost:
        event?.mode === "commit"
          ? 1.1
          : event?.mode === "tentative"
            ? 0.96
            : 1.0,
      startupFadeMs,
      tempo:
        event?.mode === "commit"
          ? 0.97
          : event?.mode === "tentative"
            ? 1.04
            : 1.0,
      pitchCents,
      cadence,
      emotionalTilt,
      continuityScore,
      previousProsody,
      releaseProfile: buildReleaseProfile(event?.text || ""),
      entryProfile:
        event?.mode === "commit"
          ? {
              attack: "fast",
              volumeBoost: 1.2,
              presenceCut: true,
              startOffsetMs: 5,
              pitchLiftCents: 5,
              tempoScale: 0.98,
            }
          : null,
    };
  }

  _deriveContinuityScore(event) {
    if (!event?.phraseId || !this.activePhraseChain.updatedAt) {
      return 0;
    }

    if (event.phraseId === this.activePhraseChain.lastPhraseId) {
      return Math.max(this.activePhraseChain.continuityScore, 0.85);
    }

    const lastBoundaryAt = Math.max(this.lastAudioEnergyAt || 0, this.activePhraseChain.updatedAt || 0);
    const gapMs = lastBoundaryAt ? Math.max(0, Date.now() - lastBoundaryAt) : Number.POSITIVE_INFINITY;

    if (gapMs < 400) {
      return clamp(this.activePhraseChain.continuityScore + 0.2, 0, 1);
    }

    if (gapMs < 900) {
      return clamp(Math.max(this.activePhraseChain.continuityScore * 0.5, 0.25), 0, 1);
    }

    return 0;
  }

  async _fadeOut(ms) {
    await delay(ms);
  }

  _applyDeltaSpeech(event) {
    if (!event?.phraseId || !event?.text) {
      return event;
    }

    const previousText = this.lastSpokenByPhrase.get(event.phraseId) || "";
    const normalizedIncoming = normalizeText(event.text);
    if (!normalizedIncoming) {
      return null;
    }

    const overlap = findTextOverlap(previousText, normalizedIncoming);
    const delta = normalizeText(overlap ? normalizedIncoming.slice(overlap.length) : normalizedIncoming);
    const finalText = delta || normalizedIncoming;

    this.lastSpokenByPhrase.set(event.phraseId, normalizedIncoming);

    return {
      ...event,
      text: finalText,
    };
  }
}

module.exports = { PlaybackController };

function normalizeText(value) {
  return typeof value === "string" ? value.replace(/\s+/g, " ").trim() : "";
}

function clampConfidence(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return 0.5;
  }
  return Math.max(0, Math.min(0.99, numeric));
}

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function finiteOr(value, fallback) {
  return Number.isFinite(value) ? value : fallback;
}

function lerp(a, b, t) {
  return a + ((b - a) * t);
}

function detectTilt(text) {
  const normalized = normalizeText(text);
  if (!normalized) {
    return 0;
  }
  if (normalized.includes("!")) {
    return 0.4;
  }
  if (normalized.includes("?")) {
    return 0.2;
  }
  if (normalized.length < 5) {
    return -0.2;
  }
  return 0;
}

function findTextOverlap(previousText, nextText) {
  const previousWords = normalizeText(previousText).split(" ").filter(Boolean);
  const nextWords = normalizeText(nextText).split(" ").filter(Boolean);
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

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function buildReleaseProfile(text) {
  const trimmed = normalizeText(text);
  if (!trimmed) {
    return {
      tailMs: 90,
      fadeMs: 70,
      pitchCents: -30,
      tempo: 0.97,
      lowpassHz: 5600,
      volume: 0.94,
    };
  }

  const lastChar = trimmed.slice(-1);
  const endsWithSpace = /\s$/.test(text);
  const endsWithPunct = /[.!?;:,"'()\[\]{}<>]|[。？！、，]/.test(lastChar);
  const endsWithLetterOrNumber = /\p{L}|\p{N}/u.test(lastChar);
  const midWord = !endsWithSpace && !endsWithPunct && endsWithLetterOrNumber;

  if (midWord) {
    return {
      tailMs: 80,
      fadeMs: 60,
      pitchCents: -20,
      tempo: 0.98,
      lowpassHz: 6000,
      volume: 0.95,
    };
  }

  return {
    tailMs: 140,
    fadeMs: 100,
    pitchCents: -40,
    tempo: 0.95,
    lowpassHz: 5200,
    volume: 0.93,
  };
}
