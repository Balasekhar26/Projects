#!/usr/bin/env node

/**
 * Demo: Live vs Deterministic Replay Comparison
 * 
 * This script demonstrates the clock abstraction in action:
 * 1. Run a session in LIVE mode (real timing)
 * 2. Record its timestamps
 * 3. Run the same session in DETERMINISTIC mode (replay with recorded times)
 * 4. Compare the sessionHash values
 * 
 * Usage:
 *   node demo-replay.js [output-dir]
 */

const path = require("path");
const fs = require("fs/promises");
const {
  UniversalLiveSession,
  SESSION_STATES,
} = require("./session/live-session");
const { ReplayManager } = require("./session/replay-manager");
const { createClockSource } = require("./session/clock-source");

async function main() {
  const outputDir = process.argv[2] || "./replay-demo-output";
  await fs.mkdir(outputDir, { recursive: true });

  console.log("🔵 DEMO: Live vs Deterministic Replay\n");

  // Minimal request for testing
  const testRequest = {
    platform: "demo",
    sourceLanguage: "en",
    autoDetectSource: false,
    targetLanguage: "es",
    sessionKind: "browser_debug",
    inputDeviceId: "default",
    outputDeviceId: "default",
    micInputDeviceId: "default",
    speakerOutputDeviceId: "default",
    micTargetLanguage: "es",
    speakerTargetLanguage: "es",
    routeProfileId: "demo-route",
    onlinePolicy: "offline-only",
    voiceProfileId: "generic:offline-default",
    preserveEmotion: false,
  };

  // ============================================================
  // PHASE 1: LIVE MODE (Record Timestamps)
  // ============================================================

  console.log("📍 Phase 1: Live Mode Execution");
  console.log("   Creating session with real clocks...\n");

  const liveSession = new UniversalLiveSession(testRequest, {
    debugMode: "full", // Capture all events
  });

  const replayManager = new ReplayManager();

  // Hook into event recording to capture timestamps
  const originalPublish = liveSession.publish.bind(liveSession);
  liveSession.publish = function (type, payload) {
    originalPublish(type, payload);
    replayManager.recordTimestamps(this);
  };

  // Start session
  try {
    await liveSession.start();
  } catch (error) {
    console.error("⚠️  Session startup warning:", error.message);
  }

  // Simulate some events
  console.log("   Simulating events...");
  liveSession.publish("status", { message: "Event 1: System check" });
  liveSession.publish("routing_state", { message: "Event 2: Routing configured" });
  liveSession.publish("health", { health: liveSession.health });

  // Get debug dump
  const liveDump = liveSession.getDebugSessionDump({ mode: "full" });
  const liveHashes = liveDump.events.map((e) => ({
    id: e.id,
    hash: e.integrityHash,
    arrival: e.arrivalIndex,
  }));

  console.log(`   ✓ Recorded ${liveDump.recordCount} events\n`);

  // ============================================================
  // PHASE 2: DETERMINISTIC MODE (Replay with Recorded Times)
  // ============================================================

  console.log("🔴 Phase 2: Deterministic Replay");
  console.log("   Creating replay clock with recorded timestamps...\n");

  // Create deterministic clock from recorded timestamps
  const replayClock = replayManager.createReplayClock();

  // Create new session with deterministic clock
  const replaySession = new UniversalLiveSession(testRequest, {
    clock: replayClock,
    debugMode: "full",
  });

  // Hook into event recording (same as before)
  const originalReplayPublish = replaySession.publish.bind(replaySession);
  replaySession.publish = function (type, payload) {
    originalReplayPublish(type, payload);
  };

  // Start session
  try {
    await replaySession.start();
  } catch (error) {
    console.error("⚠️  Replay session startup warning:", error.message);
  }

  // Publish same events in same order
  console.log("   Replaying events...");
  replaySession.publish("status", { message: "Event 1: System check" });
  replaySession.publish("routing_state", { message: "Event 2: Routing configured" });
  replaySession.publish("health", { health: replaySession.health });

  // Get debug dump
  const replayDump = replaySession.getDebugSessionDump({ mode: "full" });
  const replayHashes = replayDump.events.map((e) => ({
    id: e.id,
    hash: e.integrityHash,
    arrival: e.arrivalIndex,
  }));

  console.log(`   ✓ Replayed ${replayDump.recordCount} events\n`);

  // ============================================================
  // PHASE 3: COMPARISON
  // ============================================================

  console.log("📊 Comparison Results\n");

  let hashMatches = 0;
  let hashMismatches = 0;

  console.log("Event Hashes:");
  for (let i = 0; i < Math.max(liveHashes.length, replayHashes.length); i++) {
    const liveHash = liveHashes[i];
    const replayHash = replayHashes[i];

    if (!liveHash) {
      console.log(
        `  [${i}] LIVE: missing | REPLAY: ${replayHash.hash.slice(0, 8)}...`
      );
    } else if (!replayHash) {
      console.log(
        `  [${i}] LIVE: ${liveHash.hash.slice(0, 8)}... | REPLAY: missing`
      );
    } else {
      const match = liveHash.hash === replayHash.hash;
      if (match) hashMatches++;
      else hashMismatches++;

      const icon = match ? "✓" : "✗";
      console.log(
        `  [${i}] ${icon} LIVE: ${liveHash.hash.slice(0, 8)}... | REPLAY: ${replayHash.hash.slice(0, 8)}...`
      );
    }
  }

  console.log(`\nHash Match Rate: ${hashMatches} / ${hashMatches + hashMismatches}`);

  if (hashMismatches === 0) {
    console.log("✅ SUCCESS: Deterministic replay produced identical hashes!");
    console.log("   This proves the logic is stable independent of timing.");
  } else {
    console.log(
      "⚠️  Nondeterminism detected: replay hashes differ from live."
    );
    console.log("   This indicates timing is affecting logic outcomes.");
  }

  // ============================================================
  // SAVE RESULTS
  // ============================================================

  console.log("\n📝 Saving results...");

  const results = {
    timestamp: new Date().toISOString(),
    summary: {
      liveDump: liveDump.recordCount,
      replayDump: replayDump.recordCount,
      hashMatches,
      hashMismatches,
    },
    timestampStats: replayManager.getStatistics(),
    liveHashes,
    replayHashes,
  };

  await fs.writeFile(
    path.join(outputDir, "replay-comparison.json"),
    JSON.stringify(results, null, 2)
  );

  // Save timestamp recording for future analysis
  await replayManager.saveTimestampRecording(
    path.join(outputDir, "recorded-timestamps.json")
  );

  // Save session dumps
  await liveSession.persistDebugSessionDump(path.join(outputDir, "dumps"));
  await replaySession.persistDebugSessionDump(path.join(outputDir, "dumps"));

  console.log(`✓ Results saved to ${outputDir}`);
  console.log("\nFiles created:");
  console.log("  - replay-comparison.json (summary)");
  console.log("  - recorded-timestamps.json (for offline replay)");
  console.log("  - dumps/ (session debug dumps)");
}

main().catch((error) => {
  console.error("❌ Demo error:", error);
  process.exit(1);
});
