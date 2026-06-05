const path = require('path');
const { UniversalLiveSession } = require('./src/session/live-session');

async function runIdenticalSession(sessionId) {
  const config = {
    tempDir: path.join(__dirname, '.tmp'),
    modelsDir: path.join(__dirname, '..', '..', 'packages', 'ult-core', 'models'),
  };

  const request = {
    platform: 'desktop',
    sourceLanguage: 'en',
    autoDetectSource: false,
    targetLanguage: 'es',
    sessionKind: 'microphone',
    inputDeviceId: 'default',
    outputDeviceId: 'default',
    micInputDeviceId: 'default',
    speakerOutputDeviceId: 'default',
    micTargetLanguage: 'es',
    speakerTargetLanguage: 'es',
    routeProfileId: 'default',
    onlinePolicy: 'offline-only',
    voiceProfileId: 'generic:offline-default',
    preserveEmotion: false,
  };

  const session = new UniversalLiveSession(request, {
    config,
    clockMode: 'live',
    debugMode: 'full',
  });

  await session.start();
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

  // IDENTICAL event sequence across all runs
  session.publish('status', { message: 'Session initialized' });
  await sleep(5);
  session.publish('routing_state', {
    routeProfileId: request.routeProfileId,
    inputDeviceId: request.inputDeviceId,
    outputDeviceId: request.outputDeviceId,
  });
  await sleep(5);
  session.publish('partial_transcript', {
    chunkNumber: 1,
    transcript: 'Hello world',
    detectedLanguage: 'en',
    confidence: 0.95,
  });
  await sleep(5);
  session.publish('translation_progress', {
    chunkNumber: 1,
    progress: 0.5,
    partialTranslation: 'Hola',
  });
  await sleep(5);
  session.publish('final_translation', {
    chunkNumber: 1,
    transcript: 'Hello world',
    translatedText: 'Hola mundo',
    detectedLanguage: 'en',
    confidence: 0.98,
  });
  await sleep(5);
  session.publish('tts_started', {
    chunkNumber: 1,
    translatedText: 'Hola mundo',
  });
  await sleep(5);
  session.publish('tts_finished', {
    chunkNumber: 1,
    translatedText: 'Hola mundo',
  });
  await sleep(5);
  session.publish('health', { health: session.health });

  await session.stop();

  const dump = session.getDebugSessionDump({ mode: 'full' });
  return dump;
}

async function main() {
  console.log('╔═══════════════════════════════════════════════════════════╗');
  console.log('║     EVENT-LEVEL DETERMINISM: 5 IDENTICAL SESSIONS        ║');
  console.log('║     Testing if identical input → identical event hashes   ║');
  console.log('╚═══════════════════════════════════════════════════════════╝\n');

  const runs = [];
  for (let i = 0; i < 5; i++) {
    console.log(`Running session ${i}...`);
    const dump = await runIdenticalSession(i);
    runs.push(dump);
  }

  // Check unique decision hashes across runs
  console.log('\nUNIQUE DECISION HASHES PER RUN:\n');
  runs.forEach((dump, runIdx) => {
    const uniqueHashes = [...new Set(dump.events.map(e => e.decisionHash))].sort();
    console.log(`Run ${runIdx}: ${uniqueHashes.length} unique decision hashes`);
    uniqueHashes.forEach(h => {
      const count = dump.events.filter(e => e.decisionHash === h).length;
      const eventTypes = dump.events
        .filter(e => e.decisionHash === h)
        .map(e => e.type)
        .join(', ');
      console.log(`  ${h.slice(0, 8)}: ${count} events (${eventTypes})`);
    });
  });

  // Check if all runs have the same unique hash sets
  console.log('\nCOMPARISON:\n');
  const uniqueHashSets = runs.map((dump) => {
    return [...new Set(dump.events.map(e => e.decisionHash))].sort().join('|');
  });

  const allSame = uniqueHashSets.every(s => s === uniqueHashSets[0]);
  console.log(`All runs have identical unique hash sets: ${allSame ? '✅ YES' : '❌ NO'}\n`);

  if (!allSame) {
    console.log('Hash set differences:');
    uniqueHashSets.forEach((set, idx) => {
      console.log(`Run ${idx}: ${set.split('|').length} unique hashes`);
    });
    
    // Find which hashes differ
    const allHashes = new Set();
    runs.forEach(dump => {
      dump.events.forEach(e => allHashes.add(e.decisionHash));
    });
    
    console.log('\nHash presence per run:');
    Array.from(allHashes).sort().forEach(hash => {
      const presence = runs.map((dump, idx) => {
        return dump.events.some(e => e.decisionHash === hash) ? '✓' : '✗';
      }).join('  ');
      console.log(`${hash.slice(0, 8)}: ${presence}`);
    });
  }

  // Check event count per run
  console.log('\nEVENT COUNT PER RUN:\n');
  runs.forEach((dump, idx) => {
    console.log(`Run ${idx}: ${dump.events.length} events`);
    const typeCounts = {};
    dump.events.forEach(e => {
      typeCounts[e.type] = (typeCounts[e.type] || 0) + 1;
    });
    Object.entries(typeCounts).forEach(([type, count]) => {
      console.log(`  ${type}: ${count}`);
    });
  });

  // Final verdict
  console.log('\n╔═══════════════════════════════════════════════════════════╗');
  console.log('║     VERDICT                                              ║');
  console.log('╚═══════════════════════════════════════════════════════════╝\n');
  
  if (allSame && runs.every(r => r.events.length === runs[0].events.length)) {
    console.log('🛡️ IDENTITY HOLDS: Identical input produces identical events and hashes');
  } else if (allSame && !runs.every(r => r.events.length === runs[0].events.length)) {
    console.log('⚠️ PARTIAL: Same unique hashes but different event counts');
    console.log('   → Duplicate events being created');
  } else {
    console.log('❌ IDENTITY BROKEN: Identical input produces different event hashes');
    console.log('   → Something non-deterministic in event generation');
  }
}

main().catch((error) => {
  console.error('Test failed:', error);
  process.exit(1);
});