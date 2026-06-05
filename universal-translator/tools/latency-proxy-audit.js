const { PlaybackController } = require("../packages/ult-core/src/tts-engine/playback-controller");

async function main() {
  const frtRun = await runFirstResponseScenario();
  const pauseRun = await runPauseScenario();
  const correctionRun = await runRapidCorrectionScenario();
  const commitRun = await runCommitDominanceScenario();

  const allRuns = [frtRun, pauseRun, correctionRun, commitRun];
  const allSegments = allRuns.flatMap((run) => run.segments);
  const deadAir = analyzeDeadAir(allRuns);
  const continuationRatio = computeContinuationRatio(allSegments);
  const firstResponseMs = frtRun.firstResponseMs;
  const interruptResponseMs = correctionRun.interruptResponseMs;
  const commitDominanceMs = commitRun.commitDominanceMs;

  const firstResponse = scoreFirstResponse(firstResponseMs);
  const deadAirScore = scoreDeadAir(deadAir);
  const continuationUse = scoreContinuationUse(continuationRatio);
  const interruptResponse = scoreInterruptResponse(interruptResponseMs);
  const commitDominance = scoreCommitDominance(commitDominanceMs);

  console.log("Latency proxy audit");
  console.log(`first response: ${firstResponseMs.toFixed(1)} ms`);
  console.log(`dead-air gaps: ${deadAir.total} total, ${deadAir.risky} risky, ${deadAir.broken} broken`);
  console.log(`continuation ratio: ${(continuationRatio * 100).toFixed(1)}%`);
  console.log(`interrupt response: ${interruptResponseMs.toFixed(1)} ms`);
  console.log(`commit dominance: ${commitDominanceMs.toFixed(1)} ms`);
  console.log("");
  console.log("```text id=\"latency_proxy01\"");
  console.log(`first response | ${firstResponse.label} | ${firstResponse.score}`);
  console.log(`dead air | ${deadAirScore.label} | ${deadAirScore.score}`);
  console.log(`continuation use | ${continuationUse.label} | ${continuationUse.score}`);
  console.log(`interrupt response | ${interruptResponse.label} | ${interruptResponse.score}`);
  console.log(`commit dominance | ${commitDominance.label} | ${commitDominance.score}`);
  console.log("```");
}

async function runFirstResponseScenario() {
  const run = createHarness("first-response");
  const detectedAt = Date.now();
  run.controller.noteSpeechDetected({
    detectedAt,
    triggerAt: detectedAt + 150,
    prosody: { cadence: 0.56, speechRate: 1.04 },
  });

  await waitFor(() => run.segments.some((segment) => segment.type === "presence"), 500);
  const firstResponseSegment = run.segments.find((segment) => segment.type === "presence" || segment.type === "speech");
  const firstResponseMs = firstResponseSegment ? firstResponseSegment.startAt - detectedAt : Number.POSITIVE_INFINITY;

  await run.controller._process({
    text: "hello there",
    mode: "commit",
    confidence: 0.92,
    phraseId: 1,
    segmentId: "frt:final",
    supersedesSegmentId: null,
  });
  await sleep(260);
  await finalizeHarness(run);

  return {
    ...run,
    firstResponseMs,
  };
}

async function runPauseScenario() {
  const run = createHarness("pause");
  await run.controller._process({
    text: "let me think",
    mode: "commit",
    confidence: 0.9,
    phraseId: 11,
    segmentId: "pause:1",
    supersedesSegmentId: null,
  });
  await sleep(320);
  await sleep(540);
  await run.controller._process({
    text: "I have it now",
    mode: "commit",
    confidence: 0.94,
    phraseId: 12,
    segmentId: "pause:2",
    supersedesSegmentId: null,
  });
  await sleep(320);
  await finalizeHarness(run);
  return run;
}

async function runRapidCorrectionScenario() {
  const run = createHarness("rapid-correction");
  await run.controller._process({
    text: "I was going",
    mode: "tentative",
    confidence: 0.58,
    phraseId: 21,
    segmentId: "rapid:1",
    supersedesSegmentId: null,
  });
  await waitFor(() => run.segments.some((segment) => segment.segmentId === "rapid:1"), 400);

  const revisionAt = Date.now();
  await run.controller._process({
    text: "I was going home",
    mode: "tentative",
    confidence: 0.79,
    phraseId: 21,
    segmentId: "rapid:2",
    supersedesSegmentId: "rapid:1",
  });
  await waitFor(() => run.segments.some((segment) => segment.segmentId === "rapid:2"), 400);
  const revisionSegment = run.segments.find((segment) => segment.segmentId === "rapid:2");
  const interruptResponseMs = revisionSegment ? revisionSegment.startAt - revisionAt : Number.POSITIVE_INFINITY;

  await sleep(260);
  await finalizeHarness(run);
  return {
    ...run,
    interruptResponseMs,
  };
}

async function runCommitDominanceScenario() {
  const run = createHarness("commit-dominance");
  await run.controller._process({
    text: "maybe later",
    mode: "tentative",
    confidence: 0.61,
    phraseId: 31,
    segmentId: "commit:1",
    supersedesSegmentId: null,
  });
  await waitFor(() => run.segments.some((segment) => segment.segmentId === "commit:1"), 400);

  const commitAt = Date.now();
  await run.controller._process({
    text: "maybe later tonight",
    mode: "commit",
    confidence: 0.92,
    phraseId: 31,
    segmentId: "commit:final",
    supersedesSegmentId: "commit:1",
  });
  await waitFor(() => run.segments.some((segment) => segment.segmentId === "commit:final"), 400);
  const commitSegment = run.segments.find((segment) => segment.segmentId === "commit:final");
  const commitDominanceMs = commitSegment ? commitSegment.startAt - commitAt : Number.POSITIVE_INFINITY;

  await sleep(280);
  await finalizeHarness(run);
  return {
    ...run,
    commitDominanceMs,
  };
}

function createHarness(name) {
  const segments = [];
  let sequence = 0;
  const speaker = {
    createSpeechJob(event = {}) {
      const durationMs = event.mode === "commit" ? 220 : 180;
      return createTimedJob({
        type: "speech",
        kind: event.mode,
        durationMs,
        segmentId: event.segmentId || `${name}:speech:${++sequence}`,
        segments,
        meta: event,
      });
    },
    createContinuationJob(options = {}) {
      const durationMs = options.kind === "stretch" ? 90 : 130;
      return createTimedJob({
        type: "continuation",
        kind: options.kind || "continuation",
        durationMs,
        segmentId: `${name}:continuation:${++sequence}`,
        segments,
        meta: options,
      });
    },
    createPresenceJob(options = {}) {
      return createTimedJob({
        type: "presence",
        kind: options.gapKind || "presence",
        durationMs: 70,
        segmentId: `${name}:presence:${++sequence}`,
        segments,
        meta: options,
      });
    },
  };

  const controller = new PlaybackController({ speaker });
  return { name, speaker, controller, segments };
}

function createTimedJob({ type, kind, durationMs, segmentId, segments, meta }) {
  let aborted = false;
  let onStart = null;
  let onEnd = null;
  let segment = null;

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
      segment = {
        type,
        kind,
        segmentId,
        mode: meta?.mode || kind,
        startAt: Date.now(),
        endAt: null,
      };
      segments.push(segment);
      onStart?.();
      await sleep(durationMs);
      if (!aborted) {
        segment.endAt = Date.now();
        onEnd?.();
      }
    },
    abort() {
      aborted = true;
      if (segment && !segment.endAt) {
        segment.endAt = Date.now();
      }
      onEnd?.();
    },
    async fadeOut() {},
  };
}

function analyzeDeadAir(runs) {
  const gaps = [];

  for (const run of runs) {
    const completed = run.segments
      .filter((segment) => Number.isFinite(segment.startAt) && Number.isFinite(segment.endAt))
      .sort((a, b) => a.startAt - b.startAt);

    for (let index = 0; index < completed.length - 1; index += 1) {
      const current = completed[index];
      const next = completed[index + 1];
      const gapMs = next.startAt - current.endAt;
      if (gapMs > 0) {
        gaps.push(gapMs);
      }
    }
  }

  const risky = gaps.filter((gap) => gap >= 120 && gap <= 400).length;
  const broken = gaps.filter((gap) => gap > 400).length;

  return {
    total: gaps.length,
    risky,
    broken,
    riskyRatio: gaps.length ? risky / gaps.length : 0,
    maxGapMs: gaps.length ? Math.max(...gaps) : 0,
  };
}

function computeContinuationRatio(segments) {
  const completed = segments.filter((segment) => Number.isFinite(segment.startAt) && Number.isFinite(segment.endAt));
  const totalPlaybackMs = completed.reduce((sum, segment) => sum + (segment.endAt - segment.startAt), 0);
  const continuationMs = completed
    .filter((segment) => segment.type === "continuation")
    .reduce((sum, segment) => sum + (segment.endAt - segment.startAt), 0);

  if (!totalPlaybackMs) {
    return 0;
  }
  return continuationMs / totalPlaybackMs;
}

function scoreFirstResponse(firstResponseMs) {
  if (firstResponseMs <= 180) return { label: "fast", score: 5 };
  if (firstResponseMs <= 240) return { label: "ok", score: 4 };
  if (firstResponseMs <= 300) return { label: "ok", score: 3 };
  if (firstResponseMs <= 400) return { label: "slow", score: 2 };
  return { label: "slow", score: 1 };
}

function scoreDeadAir(deadAir) {
  if (deadAir.broken > 0) {
    return { label: "broken", score: deadAir.broken > 1 ? 1 : 2 };
  }
  if (deadAir.riskyRatio <= 0.05) {
    return { label: "clean", score: 5 };
  }
  if (deadAir.riskyRatio <= 0.15) {
    return { label: "clean", score: 4 };
  }
  if (deadAir.riskyRatio <= 0.3) {
    return { label: "risky", score: 3 };
  }
  return { label: "risky", score: 2 };
}

function scoreContinuationUse(ratio) {
  if (ratio >= 0.05 && ratio <= 0.15) {
    return { label: "natural", score: 5 };
  }
  if (ratio < 0.05) {
    return { label: "natural", score: 4 };
  }
  if (ratio <= 0.25) {
    return { label: "natural", score: 3 };
  }
  if (ratio <= 0.35) {
    return { label: "overused", score: 2 };
  }
  return { label: "overused", score: 1 };
}

function scoreInterruptResponse(interruptResponseMs) {
  if (interruptResponseMs <= 120) return { label: "sharp", score: 5 };
  if (interruptResponseMs <= 160) return { label: "sharp", score: 4 };
  if (interruptResponseMs <= 200) return { label: "late", score: 3 };
  if (interruptResponseMs <= 260) return { label: "late", score: 2 };
  return { label: "late", score: 1 };
}

function scoreCommitDominance(commitDominanceMs) {
  if (commitDominanceMs <= 100) return { label: "decisive", score: 5 };
  if (commitDominanceMs <= 140) return { label: "decisive", score: 4 };
  if (commitDominanceMs <= 200) return { label: "soft", score: 3 };
  if (commitDominanceMs <= 260) return { label: "soft", score: 2 };
  return { label: "soft", score: 1 };
}

async function finalizeHarness(run) {
  await sleep(80);
  run.controller.stop();
  await sleep(40);
}

async function waitFor(predicate, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (predicate()) {
      return;
    }
    await sleep(10);
  }
  throw new Error(`Timed out after ${timeoutMs}ms waiting for audit condition.`);
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

main().catch((error) => {
  console.error(error.message);
  process.exit(1);
});
