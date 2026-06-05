const path = require('path');
const { UniversalLiveSession } = require('./src/session/live-session');

async function runNoiseTest(runId) {
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

  const perturbations = [
    { type: 'translation_progress', chunkNumber: 1, progress: 0.1, partialTranslation: 'H' },
    { type: 'translation_progress', chunkNumber: 1, progress: 0.2, partialTranslation: 'He' },
    { type: 'translation_progress', chunkNumber: 1, progress: 0.3, partialTranslation: 'Hel' },
    { type: 'translation_progress', chunkNumber: 1, progress: 0.4, partialTranslation: 'Hell' },
    { type: 'translation_progress', chunkNumber: 1, progress: 0.5, partialTranslation: 'Hello' },
    { type: 'final_translation', chunkNumber: 1, transcript: 'Hello world', translatedText: 'Hola mundo', detectedLanguage: 'en', confidence: 0.98 }
  ];

  for (const pert of perturbations) {
    if (pert.type === 'translation_progress') {
      session.publish('translation_progress', {
        chunkNumber: pert.chunkNumber,
        progress: pert.progress,
        partialTranslation: pert.partialTranslation,
      });
    } else if (pert.type === 'final_translation') {
      session.publish('final_translation', {
        chunkNumber: pert.chunkNumber,
        transcript: pert.transcript,
        translatedText: pert.translatedText,
        detectedLanguage: pert.detectedLanguage,
        confidence: pert.confidence,
      });
    }
    await sleep(5);
  }

  session.publish('health', { health: session.health });
  await session.stop();

  const dump = session.getDebugSessionDump({ mode: 'full' });
  return dump;
}

async function main() {
  console.log('🔬 DETAILED NOISE BURST INVESTIGATION');
  console.log('='.repeat(60));

  const dumps = [];
  for (let i = 0; i < 3; i++) {
    const dump = await runNoiseTest(i);
    dumps.push(dump);
  }

  // Compare event-by-event hashes
  console.log('\nEVENT-BY-EVENT DECISION HASH COMPARISON\n');
  
  const maxEvents = Math.max(...dumps.map(d => d.events.length));
  
  for (let eventIdx = 0; eventIdx < maxEvents; eventIdx++) {
    const hashes = dumps.map((dump, runIdx) => {
      const event = dump.events[eventIdx];
      if (!event) return 'N/A';
      return `${event.type}:${event.decisionHash.slice(0, 8)}`;
    });

    const allSame = hashes.filter(h => h !== 'N/A').every(h => h === hashes[0]);
    const marker = allSame ? '✅' : '❌';

    console.log(`Event ${eventIdx}: ${marker}`);
    dumps.forEach((dump, runIdx) => {
      const event = dump.events[eventIdx];
      if (event) {
        console.log(`  Run ${runIdx}: ${event.type.padEnd(20)} decisionHash=${event.decisionHash.slice(0, 8)} contributions=${JSON.stringify(event.contributions)}`);
      }
    });
    console.log();
  }

  // Check unique decision hashes per run
  console.log('\nUNIQUE DECISION HASHES PER RUN\n');
  dumps.forEach((dump, runIdx) => {
    const uniqueDecisionHashes = [...new Set(dump.events.map(e => e.decisionHash))];
    console.log(`Run ${runIdx}: ${uniqueDecisionHashes.length} unique decision hashes`);
    uniqueDecisionHashes.forEach(h => {
      const count = dump.events.filter(e => e.decisionHash === h).length;
      console.log(`  ${h.slice(0, 8)}: ${count} events`);
    });
  });

  // Check if set of unique hashes matches
  console.log('\nSESSION-LEVEL ANALYSIS\n');
  dumps.forEach((dump, runIdx) => {
    const uniqueDecisionHashes = [...new Set(dump.events.map(e => e.decisionHash))].sort();
    const sessionHash = require('crypto')
      .createHash('sha256')
      .update(uniqueDecisionHashes.join('|'))
      .digest('hex')
      .slice(0, 16);
    console.log(`Run ${runIdx}: decisionSessionHash=${dump.decisionSessionHash} (computed from unique=${sessionHash})`);
  });
}

main().catch((error) => {
  console.error('Investigation failed:', error);
  process.exit(1);
});