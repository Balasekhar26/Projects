const test = require("node:test");
const assert = require("node:assert/strict");

const { PlaybackController } = require("../src/tts-engine/playback-controller");

function createSpeaker(log) {
  return {
    createSpeechJob(event) {
      let aborted = false;
      let onStart = null;
      let onEnd = null;
      return {
        get onStart() {
          return onStart;
        },
        set onStart(handler) {
          onStart = handler;
        },
        get onEnd() {
          return onEnd;
        },
        set onEnd(handler) {
          onEnd = handler;
        },
        async play() {
          log.push(`play:${event.segmentId}:${event.mode}:${event.text}`);
          if (event.entryProfile?.attack) {
            log.push(`entry:${event.segmentId}:${event.entryProfile.attack}:${event.entryProfile.volumeBoost}`);
          }
          onStart?.();
          if (!aborted) {
            await new Promise((resolve) => setTimeout(resolve, 1000));
            if (!aborted) {
              onEnd?.();
            }
          }
        },
        abort() {
          aborted = true;
          log.push(`abort:${event.segmentId}`);
          onEnd?.();
        },
        async fadeOut(ms) {
          log.push(`fade:${event.segmentId}:${ms}`);
        },
      };
    },
    createContinuationJob() {
      let aborted = false;
      let onStart = null;
      let onEnd = null;
      return {
        get onStart() {
          return onStart;
        },
        set onStart(handler) {
          onStart = handler;
        },
        get onEnd() {
          return onEnd;
        },
        set onEnd(handler) {
          onEnd = handler;
        },
        async play() {
          log.push("continuation:play");
          onStart?.();
          await new Promise((resolve) => setTimeout(resolve, 40));
          if (!aborted) {
            onEnd?.();
          }
        },
        abort() {
          aborted = true;
          log.push("continuation:abort");
          onEnd?.();
        },
      };
    },
    playPresence() {
      log.push("presence:start");
    },
    stopPresence() {
      log.push("presence:stop");
    },
    preempt(options = {}) {
      log.push(`preempt:${Math.round(options.durationMs ?? 0)}`);
    },
  };
}

test("playback controller coalesces tentative updates and lets commits supersede the same phrase", async () => {
  const log = [];
  const controller = new PlaybackController({
    speaker: createSpeaker(log),
    debounceMs: 10,
    staleMs: 300,
    maxPlaybackMs: 700,
  });

  controller.enqueue({ text: "నేను", mode: "tentative", phraseId: 3, segmentId: "3:1", supersedesSegmentId: null });
  controller.enqueue({ text: "నేను వెళ్తా", mode: "tentative", phraseId: 3, segmentId: "3:2", supersedesSegmentId: "3:1" });
  controller.enqueue({ text: "నేను వెళ్తాను", mode: "tentative", phraseId: 3, segmentId: "3:3", supersedesSegmentId: "3:2" });

  await new Promise((resolve) => setTimeout(resolve, 30));
  await new Promise((resolve) => setTimeout(resolve, 250));
  controller.enqueue({ text: "నేను వెళ్తాను", mode: "commit", phraseId: 3, segmentId: "3:final", supersedesSegmentId: "3:3" });
  await new Promise((resolve) => setTimeout(resolve, 80));

  assert.equal(log[0].startsWith("play:3:3:tentative:"), true);
  assert.equal(log.includes("preempt:22"), true);
  assert.equal(log.includes("fade:3:3:50"), true);
  assert.equal(log.includes("fade:3:3:100"), true);
  assert.equal(log.includes("abort:3:3"), true);
  assert.equal(log.includes("entry:3:final:fast:1.2"), true);
  assert.equal(log.some((entry) => entry.startsWith("play:3:final:commit:")), true);
  controller.stop();
});

test("higher priority commit interrupts lower priority fallback immediately", async () => {
  const log = [];
  const controller = new PlaybackController({
    speaker: createSpeaker(log),
    debounceMs: 10,
    staleMs: 300,
    maxPlaybackMs: 700,
  });

  await controller._process({ text: "fallback", mode: "fallback", phraseId: 1, segmentId: "1:1", supersedesSegmentId: null });
  await new Promise((resolve) => setTimeout(resolve, 250));
  await controller._process({ text: "commit", mode: "commit", phraseId: 1, segmentId: "1:final", supersedesSegmentId: "1:1" });
  await new Promise((resolve) => setTimeout(resolve, 60));

  assert.equal(log[0], "play:1:1:fallback:fallback");
  assert.equal(log.includes("preempt:22"), true);
  assert.equal(log.includes("fade:1:1:50"), true);
  assert.equal(log.includes("fade:1:1:100"), true);
  assert.equal(log.includes("abort:1:1"), true);
  assert.equal(log.includes("entry:1:final:fast:1.2"), true);
  assert.equal(log.includes("play:1:final:commit:commit"), true);
  controller.stop();
});

test("confidence upgrade interrupts a lower-confidence tentative line", async () => {
  const log = [];
  const controller = new PlaybackController({
    speaker: createSpeaker(log),
    debounceMs: 10,
    staleMs: 300,
    maxPlaybackMs: 700,
  });

  await controller._process({
    text: "first pass",
    mode: "tentative",
    confidence: 0.52,
    phraseId: 9,
    segmentId: "9:1",
    supersedesSegmentId: null,
  });
  await new Promise((resolve) => setTimeout(resolve, 250));
  await controller._process({
    text: "clearer pass",
    mode: "tentative",
    confidence: 0.74,
    phraseId: 9,
    segmentId: "9:2",
    supersedesSegmentId: "9:1",
  });
  await new Promise((resolve) => setTimeout(resolve, 60));

  assert.equal(log[0], "play:9:1:tentative:first pass");
  assert.equal(log.includes("fade:9:1:55"), true);
  assert.equal(log.includes("fade:9:1:100"), true);
  assert.equal(log.includes("abort:9:1"), true);
  assert.equal(log.some((entry) => entry.startsWith("preempt:")), true);
  assert.equal(log.includes("play:9:2:tentative:clearer pass"), true);
  controller.stop();
});

test("playback controller adds non-lexical continuation during active dead air", async () => {
  const log = [];
  const controller = new PlaybackController({
    speaker: createSpeaker(log),
    debounceMs: 10,
    staleMs: 300,
    maxPlaybackMs: 700,
    continuationDelayMs: 30,
    continuationWindowMs: 200,
    continuationPollMs: 10,
    continuationGapMs: 20,
  });

  controller.lastAudioEnergyAt = Date.now() - 60;
  controller.presence.lastAudioAt = Date.now() - 60;
  controller.lastUpdateAt = Date.now();
  controller.pipelineActive = true;

  await new Promise((resolve) => setTimeout(resolve, 80));
  controller.stop();

  assert.equal(log.includes("continuation:play"), true);
});

test("speech detection can trigger a low-level presence bed before words arrive", async () => {
  const log = [];
  const speaker = createSpeaker(log);
  const controller = new PlaybackController({
    speaker,
    continuationPollMs: 10,
    preSpeechWindowMs: 180,
  });

  controller.lastAudioEnergyAt = Date.now() - 180;
  controller.presence.lastAudioAt = Date.now() - 180;
  controller.noteSpeechDetected({
    detectedAt: Date.now() - 150,
    triggerAt: Date.now() - 10,
    prosody: { cadence: 0.6, speechRate: 1.05 },
  });

  await new Promise((resolve) => setTimeout(resolve, 40));
  controller.stop();

  assert.equal(log.includes("presence:start"), true);
});

test("real speech stops continuous presence immediately", async () => {
  const log = [];
  const controller = new PlaybackController({
    speaker: createSpeaker(log),
    continuationPollMs: 10,
    continuationWindowMs: 300,
  });

  controller.lastUpdateAt = Date.now();
  controller.pipelineActive = true;
  controller.presence.lastAudioAt = Date.now() - 220;

  await new Promise((resolve) => setTimeout(resolve, 40));
  await controller._process({
    text: "final line",
    mode: "commit",
    phraseId: 11,
    segmentId: "11:final",
    supersedesSegmentId: null,
  });
  await new Promise((resolve) => setTimeout(resolve, 40));
  controller.stop();

  assert.equal(log.includes("presence:start"), true);
  assert.equal(log.includes("presence:stop"), true);
});

test("gap classification distinguishes stretch vs continuation windows", () => {
  const controller = new PlaybackController({
    speaker: createSpeaker([]),
  });

  controller.lastAudioEnergyAt = Date.now() - 220;
  assert.equal(controller._classifyGap().kind, "stretch");

  controller.lastAudioEnergyAt = Date.now() - 520;
  assert.equal(controller._classifyGap().kind, "continuation");

  controller.stop();
});

test("new speech aborts continuation immediately", async () => {
  const log = [];
  const speaker = createSpeaker(log);
  speaker.createContinuationJob = () => {
    let aborted = false;
    let onStart = null;
    let onEnd = null;
    return {
      get onStart() {
        return onStart;
      },
      set onStart(handler) {
        onStart = handler;
      },
      get onEnd() {
        return onEnd;
      },
      set onEnd(handler) {
        onEnd = handler;
      },
      async play() {
        log.push("continuation:play");
        onStart?.();
        await new Promise((resolve) => setTimeout(resolve, 180));
        if (!aborted) {
          onEnd?.();
        }
      },
      abort() {
        aborted = true;
        log.push("continuation:abort");
        onEnd?.();
      },
    };
  };
  const controller = new PlaybackController({
    speaker,
    debounceMs: 10,
    staleMs: 300,
    maxPlaybackMs: 700,
    continuationDelayMs: 30,
    continuationWindowMs: 200,
    continuationPollMs: 10,
    continuationGapMs: 20,
  });

  controller.lastAudioEnergyAt = Date.now() - 60;
  controller.lastUpdateAt = Date.now();

  await new Promise((resolve) => setTimeout(resolve, 90));
  controller.enqueue({ text: "resume", mode: "commit", phraseId: 7, segmentId: "7:final", supersedesSegmentId: null });
  await new Promise((resolve) => setTimeout(resolve, 120));
  controller.stop();

  assert.equal(log.includes("continuation:play"), true);
  assert.equal(log.includes("continuation:abort"), true);
  assert.equal(log.includes("play:7:final:commit:resume"), true);
});

test("dynamic overlap adapts to prior prosody and incoming mode", () => {
  const controller = new PlaybackController({
    speaker: createSpeaker([]),
  });

  const originalRandom = Math.random;
  Math.random = () => 0.5;

  try {
    assert.equal(
      controller._computeOverlapMs({
        incomingMode: "tentative",
        lastProsody: { tempo: 1.05, energy: 1.0 },
      }),
      31
    );

    assert.equal(
      controller._computeOverlapMs({
        incomingMode: "commit",
        lastProsody: { tempo: 0.95, energy: 0.9 },
      }),
      4
    );
  } finally {
    Math.random = originalRandom;
    controller.stop();
  }
});

test("continuity memory softens resets across quick phrase handoffs", () => {
  const controller = new PlaybackController({
    speaker: createSpeaker([]),
  });

  controller.lastProsody = {
    tempo: 1.03,
    energy: 0.94,
    pitchBias: 10,
    cadence: 0.72,
    emotionalTilt: 0.2,
    mode: "tentative",
    updatedAt: Date.now() - 200,
  };
  controller.activePhraseChain = {
    lastPhraseId: 1,
    continuityScore: 0.6,
    updatedAt: Date.now() - 180,
  };
  controller.lastAudioEnergyAt = Date.now() - 180;

  const normalized = controller._normalize({
    text: "next thought?",
    mode: "tentative",
    phraseId: 2,
    segmentId: "2:1",
    supersedesSegmentId: null,
  });

  try {
    assert.equal(normalized.continuityScore > 0.7, true);
    assert.equal(normalized.startupFadeMs < 50, true);
    assert.equal(normalized.cadence > 0.6, true);
    assert.equal(normalized.pitchCents > 0, true);
    assert.equal(normalized.emotionalTilt > 0.1, true);
  } finally {
    controller.stop();
  }
});
