#!/usr/bin/env node

/**
 * Determinism Test: Run 3 Identical Sessions
 * 
 * Tests whether the system makes consistent decisions despite timing variance.
 * 
 * Usage:
 *   node test-determinism.js
 */

const path = require("path");
const fs = require("fs/promises");
const { UniversalLiveSession } = require("./src/session/live-session");

async function runSession(runNumber) {
  const config = {
    tempDir: path.join(__dirname, ".tmp"),
    modelsDir: path.join(__dirname, "models"),
  };

  const request = {
    platform: "desktop",
    sourceLanguage: "en",
    autoDetectSource: false,
    targetLanguage: "es",
    sessionKind: "microphone",
    inputDeviceId: "default",
    outputDeviceId: "default",
    micInputDeviceId: "default",
    speakerOutputDeviceId: "default",
    micTargetLanguage: "es",
    speakerTargetLanguage: "es",
    routeProfileId: "default",
    onlinePolicy: "offline-only",
    voiceProfileId: "generic:offline-default",
    preserveEmotion: false,
  };

  console.log(`\n⏱️  RUN ${runNumber}: Creating session...\n`);

  const session = new UniversalLiveSession(request, {
    config,
    clockMode: "live",
    debugMode: "full",
  });

  try {
    await session.start();

    // IDENTICAL event sequence for all 3 runs
    // This is the key: same input, same order
    session.publish("status", { message: "Session initialized" });
    await sleep(5);

    session.publish("routing_state", {
      routeProfileId: request.routeProfileId,
      inputDeviceId: request.inputDeviceId,
      outputDeviceId: request.outputDeviceId,
    });
    await sleep(5);

    // Chunk 1
    session.publish("partial_transcript", {
      chunkNumber: 1,
      transcript: "Hello world",
      detectedLanguage: "en",
      confidence: 0.95,
    });
    await sleep(5);

    session.publish("translation_progress", {
      chunkNumber: 1,
      progress: 0.5,
      partialTranslation: "Hola",
    });
    await sleep(5);

    session.publish("final_translation", {
      chunkNumber: 1,
      transcript: "Hello world",
      translatedText: "Hola mundo",
      detectedLanguage: "en",
      confidence: 0.98,
    });
    await sleep(5);

    session.publish("tts_started", {
      chunkNumber: 1,
      translatedText: "Hola mundo",
    });
    await sleep(5);

    session.publish("tts_finished", {
      chunkNumber: 1,
      translatedText: "Hola mundo",
    });
    await sleep(5);

    session.publish("health", { health: session.health });

    await session.stop();
    console.log(`✓ Session ${runNumber} completed`);

    return session.getDebugSessionDump({ mode: "full" });
  } catch (error) {
    console.error(`✗ Session ${runNumber} error:`, error.message);
    throw error;
  }
}

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

function findEventByType(events, type) {
  return events.find(e => e.type === type);
}

async function main() {
  console.log("╔═══════════════════════════════════════════════════════════╗");
  console.log("║     DETERMINISM TEST: 3 IDENTICAL SESSIONS                  ║");
  console.log("║     Measuring Logic Stability vs Timing Variance            ║");
  console.log("╚═══════════════════════════════════════════════════════════╝");

  const runs = [];

  // Run 3 identical sessions
  for (let i = 1; i <= 3; i++) {
    const dump = await runSession(i);
    runs.push(dump);
  }

  console.log("\n\n╔═══════════════════════════════════════════════════════════╗");
  console.log("║     RESULTS: SESSION-LEVEL HASHES                          ║");
  console.log("╚═══════════════════════════════════════════════════════════╝");

  console.log("\n📊 DECISION HASH (Logic Determinism):\n");
  runs.forEach((dump, i) => {
    console.log(`Run ${i + 1}: ${dump.decisionSessionHash}`);
  });

  const decisionMatch =
    runs[0].decisionSessionHash === runs[1].decisionSessionHash &&
    runs[1].decisionSessionHash === runs[2].decisionSessionHash;

  if (decisionMatch) {
    console.log("\n✅ DECISION HASHES MATCH → Logic is deterministic\n");
  } else {
    console.log("\n⚠️  DECISION HASHES DIFFER → Logic has variability\n");
  }

  console.log("📊 TIMING HASH (Temporal Behavior):\n");
  runs.forEach((dump, i) => {
    console.log(`Run ${i + 1}: ${dump.timingSessionHash}`);
  });

  const timingMatch =
    runs[0].timingSessionHash === runs[1].timingSessionHash &&
    runs[1].timingSessionHash === runs[2].timingSessionHash;

  if (timingMatch) {
    console.log("\n⚠️  TIMING HASHES MATCH → No timing variance detected\n");
  } else {
    console.log("\n✅ TIMING HASHES DIFFER → Timing variance present (expected)\n");
  }

  // ===================================================================
  // EVENT-LEVEL COMPARISON
  // ===================================================================

  console.log("\n╔═══════════════════════════════════════════════════════════╗");
  console.log("║     EVENT-LEVEL COMPARISON                                ║");
  console.log("║     Picking: final_translation                            ║");
  console.log("╚═══════════════════════════════════════════════════════════╝\n");

  const eventType = "final_translation";
  const events = runs.map(dump => findEventByType(dump.events, eventType));

  if (events.some(e => !e)) {
    console.log(`⚠️  Event type "${eventType}" not found in all runs\n`);
    process.exit(1);
  }

  console.log("Event Data Across 3 Runs:\n");

  events.forEach((evt, i) => {
    console.log(`Run ${i + 1}:`);
    console.log(`  normalizedTime: ${evt.normalizedTime}`);
    console.log(`  dominantDomain: ${evt.dominantDomain}`);
    console.log(`  logicHash: ${evt.logicHash}`);
    console.log(`  timingHash: ${evt.timingHash}`);
    console.log(`  contributions:`, evt.contributions);
    console.log();
  });

  // ===================================================================
  // DIFF ANALYSIS
  // ===================================================================

  console.log("╔═══════════════════════════════════════════════════════════╗");
  console.log("║     DIFF: Run 1 vs Run 2 (Same Event)                     ║");
  console.log("╚═══════════════════════════════════════════════════════════╝\n");

  const e1 = events[0];
  const e2 = events[1];

  console.log(`dominantDomainChanged: ${e1.dominantDomain !== e2.dominantDomain}`);
  console.log(`normalizedTimeDelta: ${e2.normalizedTime - e1.normalizedTime} ms`);
  console.log(`logicHashMatch: ${e1.logicHash === e2.logicHash}`);
  console.log(`timingHashMatch: ${e1.timingHash === e2.timingHash}`);

  // Contribution delta
  const contrib1 = e1.contributions;
  const contrib2 = e2.contributions;
  const contributionDelta = {};

  const allDomains = new Set([...Object.keys(contrib1), ...Object.keys(contrib2)]);
  for (const domain of allDomains) {
    const v1 = contrib1[domain] || 0;
    const v2 = contrib2[domain] || 0;
    const delta = v2 - v1;
    if (Math.abs(delta) > 0.001) {
      contributionDelta[domain] = delta.toFixed(4);
    }
  }

  console.log(`\nContribution Deltas (Run1 → Run2):`);
  if (Object.keys(contributionDelta).length === 0) {
    console.log(`  (none - contributions stable)`);
  } else {
    Object.entries(contributionDelta).forEach(([domain, delta]) => {
      console.log(`  ${domain}: ${delta}`);
    });
  }

  // ===================================================================
  // CLASSIFICATION
  // ===================================================================

  console.log("\n╔═══════════════════════════════════════════════════════════╗");
  console.log("║     CLASSIFICATION                                        ║");
  console.log("╚═══════════════════════════════════════════════════════════╝\n");

  const logicStable = decisionMatch;
  const timingVariant = !timingMatch;
  const eventLogicStable = e1.logicHash === e2.logicHash;
  const eventDomainStable = e1.dominantDomain === e2.dominantDomain;
  const eventContributionsStable = Object.keys(contributionDelta).length === 0;

  console.log("Session Level:");
  console.log(`  • Decision Determinism: ${logicStable ? "✅ YES" : "❌ NO"}`);
  console.log(`  • Timing Variance: ${timingVariant ? "✅ YES" : "⚠️  NO"}`);

  console.log("\nEvent Level:");
  console.log(`  • Logic Hash Match: ${eventLogicStable ? "✅ YES" : "❌ NO"}`);
  console.log(`  • Domain Stable: ${eventDomainStable ? "✅ YES" : "❌ NO"}`);
  console.log(`  • Contributions Stable: ${eventContributionsStable ? "✅ YES" : "❌ NO"}`);

  console.log("\n");

  if (logicStable && timingVariant && eventLogicStable) {
    console.log("🟢 CASE 1 - STRONG SYSTEM");
    console.log("   Logic is deterministic, timing has benign variance.");
    console.log("   → Timeline UI path is safe to pursue");
  } else if (logicStable && !eventContributionsStable) {
    console.log("🟡 CASE 2 - SURFACE STABLE, DEEP DRIFT");
    console.log("   Decisions are stable but internal reasoning drifts.");
    console.log("   → Monitor for hidden instability later");
  } else if (!logicStable) {
    console.log("🔴 CASE 3 - TRUE INSTABILITY");
    console.log("   Logic depends on timing/order.");
    console.log("   → Deeper investigation needed");
  } else {
    console.log("? UNKNOWN PATTERN");
    console.log("   Unexpected combination of metrics.");
  }

  console.log();
}

main().catch(error => {
  console.error("\n❌ Test failed:", error.message);
  process.exit(1);
});
