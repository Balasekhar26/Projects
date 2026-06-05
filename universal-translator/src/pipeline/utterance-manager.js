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

function similarityScore(previousText, nextText) {
  const previous = normalizeTranscript(previousText);
  const next = normalizeTranscript(nextText);
  if (!previous || !next) {
    return 0;
  }

  if (next.startsWith(previous) || previous.startsWith(next)) {
    return 1;
  }

  const overlap = findTranscriptOverlap(previous, next);
  if (!overlap) {
    return 0;
  }

  const overlapWords = overlap.split(" ").filter(Boolean).length;
  const previousWords = previous.split(" ").filter(Boolean).length;
  const nextWords = next.split(" ").filter(Boolean).length;
  return overlapWords / Math.max(previousWords, nextWords);
}

class UtteranceManager {
  constructor(options = {}) {
    this.nextId = 1;
    this.activeUtterance = null;
    this.lastUtterance = null;
    this.options = {
      maxGapMs: Number.isFinite(Number(options.maxGapMs)) ? Number(options.maxGapMs) : 1200,
      similarityThreshold: Number.isFinite(Number(options.similarityThreshold))
        ? Number(options.similarityThreshold)
        : 0.35,
      stabilityWindowMs: Number.isFinite(Number(options.stabilityWindowMs))
        ? Number(options.stabilityWindowMs)
        : 220,
      maxRevisionDeltaTokens: Number.isFinite(Number(options.maxRevisionDeltaTokens))
        ? Number(options.maxRevisionDeltaTokens)
        : 2,
      minimumConfidenceToSpeak: Number.isFinite(Number(options.minimumConfidenceToSpeak))
        ? Number(options.minimumConfidenceToSpeak)
        : 0.45,
    };
  }

  attachOrSpawn(transcriptState, chunk, nowMs) {
    if (this._shouldAttachToCurrent(transcriptState, nowMs)) {
      return this._updateSource(this.activeUtterance, transcriptState, chunk, nowMs);
    }

    if (
      this.activeUtterance &&
      this.activeUtterance.status !== "committed" &&
      nowMs - this.activeUtterance.lastUpdateAt > this.options.maxGapMs
    ) {
      this.activeUtterance.status = "committed";
      this.lastUtterance = this.activeUtterance;
    }

    const utterance = this._spawnUtterance(transcriptState, chunk, nowMs);
    this.activeUtterance = utterance;
    return utterance;
  }

  updateTarget(utterance, translatedFullText, mode, confidence, nowMs, chunk = {}) {
    if (!utterance) {
      return null;
    }

    const normalizedTranslation = normalizeTranscript(translatedFullText);
    const previousTarget = utterance.target.hypothesis;
    const delta = computeDelta(previousTarget, normalizedTranslation);

    if (delta) {
      utterance.target.rollingBuffer = normalizeTranscript(
        `${utterance.target.rollingBuffer} ${delta}`
      );
    }

    utterance.target.previousHypothesis = previousTarget;
    utterance.target.hypothesis = normalizedTranslation;
    utterance.target.confidence = confidence;
    utterance.target.lastUpdateAt = nowMs;

    const hasChanged = normalizedTranslation && normalizedTranslation !== previousTarget;
    if (hasChanged) {
      utterance.revision += 1;
    }

    if (mode === "commit") {
      utterance.target.stableText = normalizedTranslation;
      utterance.status = "committed";
      utterance.playback.state = "committed";
    } else if (utterance.status === "forming") {
      utterance.status = "stabilizing";
      utterance.playback.state = utterance.playback.state === "speaking" ? "revising" : "idle";
    }

    utterance.playback.pendingRevision = utterance.playback.state === "speaking" && hasChanged;

    utterance.timeline.push({
      t: nowMs,
      sourceDelta: "",
      targetDelta: delta,
      confidence,
      reason: mode,
      durationMs: chunk?.durationMs || 0,
    });

    utterance.continuityScore = this._computeContinuityScore(utterance);
    utterance.lastUpdateAt = nowMs;
    return utterance;
  }

  getPlaybackContext(utterance) {
    if (!utterance) {
      return {};
    }

    return {
      utteranceId: utterance.id,
      utteranceVersion: utterance.revision,
      utteranceStatus: utterance.status,
      utterancePlaybackState: utterance.playback.state,
      utteranceLastSpokenVersion: utterance.playback.lastSpokenVersion,
      utteranceSourceHypothesis: utterance.source.hypothesis,
      utteranceTargetHypothesis: utterance.target.hypothesis,
    };
  }

  _spawnUtterance(transcriptState, chunk, nowMs) {
    const id = `utt-${this.nextId++}`;
    const normalizedText = normalizeTranscript(transcriptState.fullText);
    const utterance = {
      id,
      status: transcriptState.isStable ? "stabilizing" : "forming",
      createdAt: nowMs,
      lastUpdateAt: nowMs,
      source: {
        stableText: transcriptState.isStable ? normalizedText : "",
        rollingBuffer: normalizedText,
        hypothesis: normalizedText,
        confidence: transcriptState.confidence,
        lastStableAt: transcriptState.isStable ? nowMs : 0,
      },
      target: {
        previousHypothesis: "",
        stableText: "",
        rollingBuffer: "",
        hypothesis: "",
        confidence: 0,
        lastUpdateAt: nowMs,
      },
      timeline: [
        {
          t: nowMs,
          sourceDelta: normalizeTranscript(transcriptState.deltaText),
          targetDelta: "",
          confidence: transcriptState.confidence,
          reason: chunk?.reason || "chunk",
          durationMs: chunk?.durationMs || 0,
        },
      ],
      continuityScore: transcriptState.confidence,
      chunkIds: chunk?.segmentId ? [chunk.segmentId] : [],
      revision: 1,
      playback: {
        state: "idle",
        lastSpokenVersion: 0,
        lastSpokenAt: 0,
        pendingRevision: false,
      },
    };
    return utterance;
  }

  _shouldAttachToCurrent(transcriptState, nowMs) {
    if (!this.activeUtterance) {
      return false;
    }

    if (this.activeUtterance.status === "committed") {
      return false;
    }

    if (nowMs - this.activeUtterance.lastUpdateAt > this.options.maxGapMs) {
      return false;
    }

    if (transcriptState.extendsPrevious) {
      return true;
    }

    const score = similarityScore(
      this.activeUtterance.source.hypothesis,
      transcriptState.fullText
    );

    if (score >= this.options.similarityThreshold) {
      return true;
    }

    const lastPhrase = this.activeUtterance.source.hypothesis
      .split(" ")
      .slice(-3)
      .join(" ");

    if (lastPhrase && transcriptState.fullText.includes(lastPhrase)) {
      return true;
    }

    return false;
  }

  _updateSource(utterance, transcriptState, chunk, nowMs) {
    const normalizedText = normalizeTranscript(transcriptState.fullText);
    const previousHypothesis = utterance.source.hypothesis;
    const delta = computeDelta(previousHypothesis, normalizedText);

    if (delta) {
      utterance.source.rollingBuffer = normalizeTranscript(
        `${utterance.source.rollingBuffer} ${delta}`
      );
    }

    utterance.source.hypothesis = normalizedText;
    utterance.source.confidence = transcriptState.confidence;

    if (transcriptState.isStable) {
      utterance.source.stableText = normalizedText;
      utterance.source.lastStableAt = nowMs;
      if (utterance.status === "forming") {
        utterance.status = "stabilizing";
      }
    }

    utterance.timeline.push({
      t: nowMs,
      sourceDelta: delta,
      targetDelta: "",
      confidence: transcriptState.confidence,
      reason: chunk?.reason || "chunk",
      durationMs: chunk?.durationMs || 0,
    });

    if (chunk?.segmentId) {
      utterance.chunkIds.push(chunk.segmentId);
    }

    utterance.continuityScore = this._computeContinuityScore(utterance);
    utterance.lastUpdateAt = nowMs;
    return utterance;
  }

  _computeContinuityScore(utterance) {
    const sourceConfidence = Number.isFinite(utterance.source.confidence)
      ? utterance.source.confidence
      : 0;
    const targetConfidence = Number.isFinite(utterance.target.confidence)
      ? utterance.target.confidence
      : 0;
    const weight = utterance.timeline.length > 1 ? 0.33 : 0.0;
    return Math.min(1, sourceConfidence * 0.6 + targetConfidence * 0.35 + weight);
  }

  _revisionDeltaTokens(utterance) {
    if (!utterance || !utterance.target.previousHypothesis || !utterance.target.hypothesis) {
      return 0;
    }

    const delta = computeDelta(utterance.target.previousHypothesis, utterance.target.hypothesis);
    return delta.split(" ").filter(Boolean).length;
  }

  _isMinorRevision(utterance) {
    return this._revisionDeltaTokens(utterance) <= this.options.maxRevisionDeltaTokens;
  }

  canSpeak(utterance, systemState = {}) {
    if (!utterance) {
      return false;
    }

    if (utterance.playback.lastSpokenVersion >= utterance.revision) {
      return false;
    }

    if (utterance.status === "committed") {
      return true;
    }

    const nowMs = Number.isFinite(systemState.nowMs) ? systemState.nowMs : Date.now();
    const sinceUpdateMs = nowMs - utterance.lastUpdateAt;
    const hasCurrentJob = Boolean(systemState.currentJob);
    const isMinor = this._isMinorRevision(utterance);
    const confidence = Number.isFinite(systemState.currentConfidence)
      ? systemState.currentConfidence
      : utterance.target.confidence;

    if (hasCurrentJob && utterance.playback.state === "speaking" && !isMinor) {
      return false;
    }

    if (sinceUpdateMs >= this.options.stabilityWindowMs && confidence >= this.options.minimumConfidenceToSpeak) {
      return true;
    }

    if (!hasCurrentJob && confidence >= this.options.minimumConfidenceToSpeak && isMinor) {
      return true;
    }

    return false;
  }

  decidePlayback(utterance, systemState = {}) {
    if (!utterance) {
      return { action: "wait", mode: "tentative", reason: "no-utterance" };
    }

    if (utterance.playback.lastSpokenVersion >= utterance.revision) {
      return { action: "wait", mode: "tentative", reason: "already-spoken" };
    }

    if (utterance.status === "committed") {
      return { action: "speak", mode: "commit", reason: "commit-ready" };
    }

    const canSpeak = this.canSpeak(utterance, systemState);
    if (!canSpeak) {
      return { action: "wait", mode: "tentative", reason: "waiting-for-stability" };
    }

    const isMorph = Boolean(
      systemState.currentJob &&
      utterance.playback.lastSpokenVersion > 0 &&
      utterance.revision > utterance.playback.lastSpokenVersion &&
      this._isMinorRevision(utterance)
    );

    return {
      action: "speak",
      mode: "tentative",
      isMorph,
      reason: isMorph ? "minor-revision-morph" : "tentative-ready",
    };
  }

  markSpokenVersion(utterance, nowMs = Date.now()) {
    if (!utterance) {
      return;
    }

    if (utterance.revision > utterance.playback.lastSpokenVersion) {
      utterance.playback.lastSpokenVersion = utterance.revision;
    }
    utterance.playback.state = "speaking";
    utterance.playback.lastSpokenAt = nowMs;
    utterance.playback.pendingRevision = false;
  }

  markPlaybackComplete(utterance, nowMs = Date.now()) {
    if (!utterance) {
      return;
    }

    utterance.playback.state = utterance.status === "committed" ? "finalized" : "spoken";
    utterance.playback.lastSpokenAt = nowMs;
    if (utterance.revision > utterance.playback.lastSpokenVersion) {
      utterance.playback.lastSpokenVersion = utterance.revision;
    }
  }
}

module.exports = {
  UtteranceManager,
};
