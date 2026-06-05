class LatencyProfiler {
  constructor(options = {}) {
    this.enabled = options.enabled !== false;
    this.chunks = new Map();
    this.phrases = new Map();
  }

  startChunk(chunkNumber, payload = {}) {
    if (!this.enabled) return null;
    const record = {
      chunkNumber,
      startedAt: nowMs(),
      captureDetectedAt: finiteOr(payload.captureDetectedAt, null),
      stageMarks: new Map(),
      emitted: false,
      phraseId: null,
      mode: null,
    };
    this.chunks.set(chunkNumber, record);
    return record;
  }

  markChunkStage(chunkNumber, stage, at = nowMs()) {
    if (!this.enabled) return;
    const record = this.chunks.get(chunkNumber);
    if (!record) return;
    record.stageMarks.set(stage, at);
  }

  attachPhrase(chunkNumber, payload = {}) {
    if (!this.enabled) return null;
    const record = this.chunks.get(chunkNumber);
    if (!record) return null;
    const phraseKey = phraseKeyFor(payload.phraseId, payload.revision);
    record.phraseId = payload.phraseId ?? null;
    record.mode = payload.mode || null;
    const phrase = {
      phraseKey,
      phraseId: payload.phraseId ?? null,
      revision: payload.revision ?? null,
      mode: payload.mode || null,
      chunkNumber,
      enqueuedAt: nowMs(),
      playbackStartedAt: null,
      playbackEndedAt: null,
      supersedesSegmentId: payload.supersedesSegmentId || null,
    };
    this.phrases.set(phraseKey, phrase);
    return phrase;
  }

  markPlaybackStart(payload = {}) {
    if (!this.enabled) return null;
    const phrase = this.phrases.get(phraseKeyFor(payload.phraseId, payload.revision));
    if (!phrase) return null;
    phrase.playbackStartedAt = nowMs();
    const chunk = this.chunks.get(phrase.chunkNumber);
    if (chunk) {
      this.markChunkStage(phrase.chunkNumber, "playback_start", phrase.playbackStartedAt);
    }
    return this.buildChunkMetric(phrase.chunkNumber);
  }

  markPlaybackEnd(payload = {}) {
    if (!this.enabled) return null;
    const phrase = this.phrases.get(phraseKeyFor(payload.phraseId, payload.revision));
    if (!phrase) return null;
    phrase.playbackEndedAt = nowMs();
    return phrase;
  }

  buildChunkMetric(chunkNumber) {
    if (!this.enabled) return null;
    const chunk = this.chunks.get(chunkNumber);
    if (!chunk) return null;

    const startedAt = chunk.startedAt;
    const stage = (name) => chunk.stageMarks.get(name);
    const playbackStartAt = stage("playback_start");
    const sttReadyAt = stage("stt_ready");
    const translationReadyAt = stage("translation_ready");
    const speechEnqueuedAt = stage("speech_enqueued");
    const captureDetectedAt = finiteOr(chunk.captureDetectedAt, startedAt);

    return {
      chunkNumber,
      mode: chunk.mode,
      phraseId: chunk.phraseId,
      totalLatencyMs: deltaMs(startedAt, playbackStartAt),
      speechStartToFirstAudioMs: deltaMs(captureDetectedAt, playbackStartAt),
      sttReadyMs: deltaMs(startedAt, sttReadyAt),
      translationReadyMs: deltaMs(sttReadyAt, translationReadyAt),
      ttsStartDelayMs: deltaMs(speechEnqueuedAt, playbackStartAt),
      playbackQueueDelayMs: deltaMs(translationReadyAt, speechEnqueuedAt),
      endToEndMs: deltaMs(startedAt, playbackStartAt),
    };
  }

  buildPhraseMetric(payload = {}) {
    if (!this.enabled) return null;
    const phrase = this.phrases.get(phraseKeyFor(payload.phraseId, payload.revision));
    if (!phrase) return null;

    let interruptReactionMs = null;
    if (phrase.supersedesSegmentId) {
      const superseded = findPhraseBySegmentId(this.phrases, phrase.supersedesSegmentId);
      if (superseded?.playbackStartedAt && phrase.playbackStartedAt) {
        interruptReactionMs = phrase.playbackStartedAt - payload.arrivedAt;
      }
    }

    return {
      phraseId: phrase.phraseId,
      revision: phrase.revision,
      mode: phrase.mode,
      chunkNumber: phrase.chunkNumber,
      interruptReactionMs,
      playbackStartedAt: phrase.playbackStartedAt,
    };
  }
}

function phraseKeyFor(phraseId, revision) {
  return `${phraseId ?? "none"}:${revision ?? "none"}`;
}

function findPhraseBySegmentId(phrases, segmentId) {
  for (const phrase of phrases.values()) {
    if (`${phrase.phraseId}:${phrase.revision}` === segmentId || phrase.segmentId === segmentId) {
      return phrase;
    }
  }
  return null;
}

function finiteOr(value, fallback) {
  return Number.isFinite(value) ? value : fallback;
}

function deltaMs(start, end) {
  if (!Number.isFinite(start) || !Number.isFinite(end)) {
    return null;
  }
  return Math.max(0, end - start);
}

function nowMs() {
  return Date.now();
}

module.exports = { LatencyProfiler };
