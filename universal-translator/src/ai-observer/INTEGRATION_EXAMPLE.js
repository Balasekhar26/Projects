/**
 * Integration notes for wiring AIObserver into RealtimeTranslator.
 *
 * This file is intentionally valid JavaScript so repo-wide linting can parse it.
 * The observer is optional and should be injected into RealtimeTranslator through
 * the constructor, then called at these lifecycle points:
 *
 * - after STT: observer.ingestSttChunk(...)
 * - after utterance target update: observer.ingestUtteranceUpdated(...)
 * - after playback arbitration: observer.ingestArbitrationDecision(...)
 * - on audible start/end: observer.ingestPlaybackStart/End(...)
 * - on latency spikes: observer.ingestLatencySpike(...)
 */

const integrationHooks = [
  "ingestSttChunk",
  "ingestUtteranceUpdated",
  "ingestArbitrationDecision",
  "ingestPlaybackStart",
  "ingestPlaybackEnd",
  "ingestLatencySpike",
];

module.exports = {
  integrationHooks,
};
