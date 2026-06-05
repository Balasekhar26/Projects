const { hashPayload, normalizeContributions } = require("./debug-record");
const {
  TEMPORAL_IDENTITY_CONFIG,
  resolveTemporalIdentityConfig,
} = require("./temporal-config");

const DEFAULT_TEMPORAL_IDENTITY_OPTIONS = TEMPORAL_IDENTITY_CONFIG;

function stabilizeTemporalIdentities(records, options = {}) {
  return evaluateTemporalIdentities(records, options).records;
}

function evaluateTemporalIdentities(records, options = {}) {
  const config = resolveTemporalIdentityConfig(options);

  if (!Array.isArray(records) || records.length === 0) {
    return { records: [], transitions: [], config };
  }

  const output = records.map((record) => clone(record));
  const channels = groupByChannel(output);
  const transitions = [];

  for (const indexes of channels.values()) {
    const channelRecords = indexes.map((index) => output[index]);
    const evaluation = evaluateChannel(channelRecords, config);
    indexes.forEach((index, position) => {
      output[index] = evaluation.records[position];
    });
    transitions.push(...evaluation.transitions);
  }

  return {
    records: output,
    transitions: transitions.sort((left, right) => left.firstEvidenceTime - right.firstEvidenceTime),
    config,
  };
}

function evaluateChannel(records, options) {
  const observedCandidates = records.map((record) => createCandidate(record));
  const hysteresisCandidates = applyHysteresis(observedCandidates, options);
  const spikeRejected = rejectIsolatedSpikes(hysteresisCandidates, records, options);
  const effectiveCandidates = mergeShortRuns(spikeRejected, records, options);
  const effectiveRuns = computeRuns(effectiveCandidates, records);
  const transitions = buildTransitions(
    observedCandidates,
    hysteresisCandidates,
    effectiveCandidates,
    effectiveRuns,
    records,
    options
  );

  const recordsWithMeta = records.map((record, index) => {
    const observedCandidate = observedCandidates[index];
    const effectiveCandidate = effectiveCandidates[index];
    const run = computeRunAtIndex(effectiveCandidates, records, index);
    const recentHashes = effectiveCandidates
      .slice(Math.max(0, index - options.majorityWindow + 1), index + 1)
      .map((candidate) => candidate.hash);
    const confirmationCount = recentHashes.filter((hash) => hash === effectiveCandidate.hash).length;
    const confirmed =
      confirmationCount >= options.majorityCount && run.durationMs >= options.minDurationMs;
    const transition = findTransitionForIndex(transitions, index);

    return {
      ...record,
      dominantDomain: effectiveCandidate.dominantDomain,
      contributions: { ...effectiveCandidate.contributions },
      temporalIdentity: buildTemporalIdentityMeta({
        record,
        index,
        observedCandidate,
        effectiveCandidate,
        hysteresisCandidate: hysteresisCandidates[index],
        confirmationCount,
        confirmed,
        run,
        transition,
        options,
      }),
    };
  });

  return { records: recordsWithMeta, transitions };
}

function applyHysteresis(candidates, options) {
  const nextCandidates = [];

  for (const candidate of candidates) {
    const previous = nextCandidates[nextCandidates.length - 1];
    if (!previous || previous.hash === candidate.hash) {
      nextCandidates.push(candidate);
      continue;
    }

    const candidateShare = Math.abs(candidate.normalizedContributions[candidate.dominantDomain] || 0);
    const previousShare = Math.abs(candidate.normalizedContributions[previous.dominantDomain] || 0);

    if (candidateShare - previousShare < options.hysteresisMargin) {
      nextCandidates.push({
        ...clone(previous),
        rawHash: candidate.hash,
        rawDominantDomain: candidate.dominantDomain,
        rawNormalizedContributions: { ...candidate.normalizedContributions },
        rawContributions: { ...candidate.contributions },
        hysteresisApplied: true,
      });
      continue;
    }

    nextCandidates.push(candidate);
  }

  return nextCandidates;
}

function rejectIsolatedSpikes(candidates, records, options) {
  const nextCandidates = candidates.map((candidate) => clone(candidate));

  for (let index = 1; index < candidates.length - 1; index++) {
    const previous = nextCandidates[index - 1];
    const current = nextCandidates[index];
    const next = nextCandidates[index + 1];
    const pointDuration = getPointDuration(records, index);

    if (
      previous.hash === next.hash &&
      current.hash !== previous.hash &&
      pointDuration < options.minDurationMs
    ) {
      nextCandidates[index] = {
        ...clone(previous),
        spikeRejected: true,
        rawHash: current.rawHash || current.hash,
        rawDominantDomain: current.rawDominantDomain || current.dominantDomain,
        rawNormalizedContributions: {
          ...(current.rawNormalizedContributions || current.normalizedContributions),
        },
        rawContributions: {
          ...(current.rawContributions || current.contributions),
        },
      };
    }
  }

  return nextCandidates;
}

function mergeShortRuns(candidates, records, options) {
  const nextCandidates = candidates.map((candidate) => clone(candidate));
  let changed = true;

  while (changed) {
    changed = false;
    const runs = computeRuns(nextCandidates, records);

    for (const run of runs) {
      if (run.count >= options.majorityCount && run.durationMs >= options.minDurationMs) {
        continue;
      }

      const left = run.start > 0 ? nextCandidates[run.start - 1] : null;
      const right = run.end < nextCandidates.length - 1 ? nextCandidates[run.end + 1] : null;

      let replacement = null;
      if (left && right && left.hash === right.hash) {
        replacement = right;
      } else if (left && right) {
        replacement = run.durationMs <= getNeighborDuration(records, run.end + 1) ? left : right;
      } else {
        replacement = left || right;
      }

      if (!replacement) {
        continue;
      }

      for (let index = run.start; index <= run.end; index++) {
        const current = nextCandidates[index];
        nextCandidates[index] = {
          ...clone(replacement),
          mergedFromShortRun: true,
          rawHash: current.rawHash || current.hash,
          rawDominantDomain: current.rawDominantDomain || current.dominantDomain,
          rawNormalizedContributions: {
            ...(current.rawNormalizedContributions || current.normalizedContributions),
          },
          rawContributions: {
            ...(current.rawContributions || current.contributions),
          },
        };
      }
      changed = true;
    }
  }

  return nextCandidates;
}

function buildTransitions(
  observedCandidates,
  hysteresisCandidates,
  effectiveCandidates,
  effectiveRuns,
  records,
  options
) {
  const transitions = [];

  for (let runIndex = 0; runIndex < effectiveRuns.length; runIndex++) {
    const run = effectiveRuns[runIndex];
    const previousRun = effectiveRuns[runIndex - 1] || null;
    const effectiveHash = effectiveCandidates[run.start].hash;
    const effectiveDominantDomain = effectiveCandidates[run.start].dominantDomain;
    const confirmation = findCommitPoint(run, effectiveCandidates, records, options);
    const firstEvidenceIndex =
      previousRun === null
        ? run.start
        : findFirstEvidenceIndex(
            previousRun.commitIndex ?? previousRun.end,
            run.start,
            observedCandidates,
            effectiveDominantDomain
          );

    const firstEvidenceTime = getRecordTime(records[firstEvidenceIndex], firstEvidenceIndex);
    const commitTime = getRecordTime(records[confirmation.commitIndex], confirmation.commitIndex);
    const windowStart = previousRun === null ? 0 : (previousRun.commitIndex ?? previousRun.end) + 1;
    const leadupMetrics = collectTransitionLeadupMetrics({
      windowStart,
      windowEnd: confirmation.commitIndex,
      firstEvidenceIndex,
      observedCandidates,
      hysteresisCandidates,
      effectiveCandidates,
      records,
      effectiveDominantDomain,
    });

    const transition = {
      channelKey: getChannelKey(records[run.start]),
      runStart: run.start,
      runEnd: run.end,
      firstEvidenceIndex,
      firstEvidenceTime,
      commitIndex: confirmation.commitIndex,
      commitTime,
      commitDelay: Math.max(0, commitTime - firstEvidenceTime),
      commitDelayMs: Math.max(0, commitTime - firstEvidenceTime),
      confirmationFrames: confirmation.confirmationFrames,
      falseRejections: leadupMetrics.falseRejections,
      prematureCommits: confirmation.prematureCommit ? 1 : 0,
      rawFlipAttempts: leadupMetrics.rawFlipAttempts,
      rejectedSpikes: leadupMetrics.rejectedSpikes,
      hysteresisHoldMs: leadupMetrics.hysteresisHoldMs,
      effectiveHash,
      effectiveDominantDomain,
      effectiveRunDurationMs: run.durationMs,
      stabilityScore: computeStabilityScore({
        confirmationFrames: confirmation.confirmationFrames,
        rejectedSpikes: leadupMetrics.rejectedSpikes,
        rawFlipAttempts: leadupMetrics.rawFlipAttempts,
        commitDelayMs: Math.max(0, commitTime - firstEvidenceTime),
        hysteresisHoldMs: leadupMetrics.hysteresisHoldMs,
        minDurationMs: options.minDurationMs,
      }),
    };

    transitions.push(transition);
    run.commitIndex = confirmation.commitIndex;
  }

  return transitions;
}

function collectTransitionLeadupMetrics({
  windowStart,
  windowEnd,
  firstEvidenceIndex,
  observedCandidates,
  hysteresisCandidates,
  effectiveCandidates,
  records,
  effectiveDominantDomain,
}) {
  let rawFlipAttempts = 0;
  let rejectedSpikes = 0;
  let hysteresisHoldMs = 0;
  let falseRejections = 0;
  let lastObservedDifferent = false;

  for (let index = windowStart; index <= windowEnd; index++) {
    const observed = observedCandidates[index];
    const hysteresis = hysteresisCandidates[index];
    const effective = effectiveCandidates[index];
    const duration = getPointDuration(records, index);
    const observedSupportsTarget = observed.dominantDomain === effectiveDominantDomain;
    const effectiveSupportsTarget = effective.dominantDomain === effectiveDominantDomain;
    const rawDifferent = observed.hash !== effective.hash;

    if (rawDifferent && !lastObservedDifferent) {
      rawFlipAttempts += 1;
    }
    lastObservedDifferent = rawDifferent;

    if (hysteresis.hysteresisApplied && observedSupportsTarget && !effectiveSupportsTarget) {
      hysteresisHoldMs += duration;
    }

    if ((hysteresis.spikeRejected || effective.spikeRejected) && observedSupportsTarget && !effectiveSupportsTarget) {
      rejectedSpikes += 1;
    }

    if (index >= firstEvidenceIndex && observedSupportsTarget && !effectiveSupportsTarget) {
      falseRejections += 1;
    }
  }

  return {
    rawFlipAttempts,
    rejectedSpikes,
    hysteresisHoldMs: Math.max(0, Math.round(hysteresisHoldMs)),
    falseRejections,
  };
}

function buildTemporalIdentityMeta({
  record,
  index,
  observedCandidate,
  effectiveCandidate,
  hysteresisCandidate,
  confirmationCount,
  confirmed,
  run,
  transition,
  options,
}) {
  const metrics = transition
    ? {
        stabilityScore: transition.stabilityScore,
        confirmationFrames: transition.confirmationFrames,
        commitDelayMs: transition.commitDelayMs,
        rejectedSpikes: transition.rejectedSpikes,
        hysteresisHoldMs: transition.hysteresisHoldMs,
        rawFlipAttempts: transition.rawFlipAttempts,
        firstEvidenceTime: transition.firstEvidenceTime,
        commitTime: transition.commitTime,
        falseRejections: transition.falseRejections,
        prematureCommits: transition.prematureCommits,
      }
    : {
        stabilityScore: 1,
        confirmationFrames: confirmationCount,
        commitDelayMs: 0,
        rejectedSpikes: 0,
        hysteresisHoldMs: 0,
        rawFlipAttempts: 0,
        firstEvidenceTime: getRecordTime(record, index),
        commitTime: getRecordTime(record, index),
        falseRejections: 0,
        prematureCommits: 0,
      };

  return {
    channelKey: getChannelKey(record),
    rawHash: observedCandidate.hash,
    rawDominantDomain: observedCandidate.dominantDomain,
    rawContributions: { ...observedCandidate.contributions },
    rawNormalizedContributions: { ...observedCandidate.normalizedContributions },
    effectiveHash: effectiveCandidate.hash,
    effectiveDominantDomain: effectiveCandidate.dominantDomain,
    effectiveContributions: { ...effectiveCandidate.contributions },
    effectiveNormalizedContributions: { ...effectiveCandidate.normalizedContributions },
    state: deriveState({
      observedCandidate,
      effectiveCandidate,
      hysteresisCandidate,
      confirmed,
      transition,
    }),
    streakCount: run.count,
    streakDurationMs: run.durationMs,
    confirmationCount,
    hysteresisApplied: hysteresisCandidate.hysteresisApplied === true,
    minDurationMs: options.minDurationMs,
    majorityWindow: options.majorityWindow,
    majorityCount: options.majorityCount,
    metrics,
  };
}

function computeStabilityScore({
  confirmationFrames,
  rejectedSpikes,
  rawFlipAttempts,
  commitDelayMs,
  hysteresisHoldMs,
  minDurationMs,
}) {
  const evidenceStrength =
    confirmationFrames / Math.max(confirmationFrames + rejectedSpikes + rawFlipAttempts, 1);
  const responsiveness = minDurationMs / Math.max(minDurationMs, commitDelayMs || minDurationMs);
  const decisiveness = minDurationMs / Math.max(minDurationMs, hysteresisHoldMs || minDurationMs);
  const score = evidenceStrength * responsiveness * decisiveness;
  return Number(Math.max(0, Math.min(1, score)).toFixed(3));
}

function findCommitPoint(run, effectiveCandidates, records, options) {
  let confirmationFrames = run.count;
  let commitIndex = run.end;

  for (let index = run.start; index <= run.end; index++) {
    const segment = effectiveCandidates.slice(run.start, index + 1);
    const recentHashes = segment
      .slice(Math.max(0, segment.length - options.majorityWindow))
      .map((candidate) => candidate.hash);
    const confirmationCount = recentHashes.filter((hash) => hash === effectiveCandidates[run.start].hash).length;
    const durationMs = getSpanDuration(records, run.start, index);

    if (confirmationCount >= options.majorityCount && durationMs >= options.minDurationMs) {
      confirmationFrames = index - run.start + 1;
      commitIndex = index;
      break;
    }
  }

  const prematureCommit = getSpanDuration(records, run.start, commitIndex) < options.minDurationMs;

  return {
    commitIndex,
    confirmationFrames,
    prematureCommit,
  };
}

function findFirstEvidenceIndex(searchStart, runStart, observedCandidates, targetDominantDomain) {
  for (let index = Math.max(0, searchStart); index <= runStart; index++) {
    if (observedCandidates[index].dominantDomain === targetDominantDomain) {
      return index;
    }
  }
  return runStart;
}

function findTransitionForIndex(transitions, index) {
  for (const transition of transitions) {
    if (index >= transition.runStart && index <= transition.runEnd) {
      return transition;
    }
  }
  return null;
}

function computeRuns(candidates, records) {
  const runs = [];
  let start = 0;

  while (start < candidates.length) {
    let end = start;
    while (end + 1 < candidates.length && candidates[end + 1].hash === candidates[start].hash) {
      end += 1;
    }

    runs.push({
      start,
      end,
      count: end - start + 1,
      durationMs: getSpanDuration(records, start, end),
    });
    start = end + 1;
  }

  return runs;
}

function computeRunAtIndex(candidates, records, index) {
  let start = index;
  let end = index;

  while (start > 0 && candidates[start - 1].hash === candidates[index].hash) {
    start -= 1;
  }
  while (end < candidates.length - 1 && candidates[end + 1].hash === candidates[index].hash) {
    end += 1;
  }

  return {
    count: end - start + 1,
    durationMs: getSpanDuration(records, start, end),
  };
}

function createCandidate(record) {
  const contributions = { ...(record.contributions || {}) };
  const normalizedContributions = normalizeContributions(contributions);
  const dominantDomain = record.dominantDomain || getDominantDomain(normalizedContributions);

  return {
    dominantDomain,
    contributions,
    normalizedContributions,
    hash: hashPayload({
      dominantDomain,
      normalizedContributions,
    }),
    rawHash: null,
    rawDominantDomain: null,
    rawNormalizedContributions: null,
    rawContributions: null,
    hysteresisApplied: false,
    spikeRejected: false,
    mergedFromShortRun: false,
  };
}

function getDominantDomain(contributions) {
  const entries = Object.entries(contributions || {});
  if (entries.length === 0) {
    return "none";
  }

  return entries.reduce((winner, current) =>
    Math.abs(current[1]) > Math.abs(winner[1]) ? current : winner
  )[0];
}

function groupByChannel(records) {
  const channels = new Map();

  records.forEach((record, index) => {
    const key = getChannelKey(record);
    const list = channels.get(key) || [];
    list.push(index);
    channels.set(key, list);
  });

  return channels;
}

function getChannelKey(record) {
  return record.type || "unknown";
}

function getSpanDuration(records, start, end) {
  const startTime = getRecordTime(records[start], start);
  const endTime = getRecordTime(records[end + 1], end + 1, records[end], end);
  return Math.max(0, endTime - startTime);
}

function getNeighborDuration(records, index) {
  return getSpanDuration(records, Math.max(0, index), Math.min(records.length - 1, index));
}

function getPointDuration(records, index) {
  const previousTime = index > 0 ? getRecordTime(records[index - 1], index - 1) : null;
  const currentTime = getRecordTime(records[index], index);
  const nextTime = index < records.length - 1 ? getRecordTime(records[index + 1], index + 1) : null;

  if (Number.isFinite(previousTime) && Number.isFinite(nextTime)) {
    return Math.min(currentTime - previousTime, nextTime - currentTime);
  }
  if (Number.isFinite(nextTime)) {
    return nextTime - currentTime;
  }
  if (Number.isFinite(previousTime)) {
    return currentTime - previousTime;
  }

  return 0;
}

function getRecordTime(record, fallbackIndex, previousRecord = null, previousIndex = null) {
  if (record) {
    if (Number.isFinite(record.normalizedTime)) {
      return record.normalizedTime;
    }
    if (Number.isFinite(record.sessionTime)) {
      return record.sessionTime;
    }
    if (Number.isFinite(record.rawTime)) {
      return record.rawTime;
    }
  }

  if (previousRecord) {
    return getRecordTime(previousRecord, previousIndex) + 1;
  }

  return fallbackIndex;
}

function deriveState({ observedCandidate, effectiveCandidate, hysteresisCandidate, confirmed, transition }) {
  if (observedCandidate.hash === effectiveCandidate.hash && confirmed) {
    return "confirmed";
  }
  if (hysteresisCandidate.hysteresisApplied) {
    return "hysteresis-hold";
  }
  if (effectiveCandidate.spikeRejected) {
    return "spike-rejected";
  }
  if (effectiveCandidate.mergedFromShortRun) {
    return "merged-short-run";
  }
  if (transition && transition.commitIndex > transition.runStart) {
    return "warming";
  }
  return confirmed ? "confirmed" : "warming";
}

function clone(value) {
  return JSON.parse(JSON.stringify(value));
}

module.exports = {
  DEFAULT_TEMPORAL_IDENTITY_OPTIONS,
  evaluateTemporalIdentities,
  stabilizeTemporalIdentities,
};
