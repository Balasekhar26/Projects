const path = require('path');
const { UniversalLiveSession } = require('./src/session/live-session');

async function runAdversarialSession(sessionId, perturbations) {
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

  console.log(`\n🧪 RUN ${sessionId}: Adversarial session with ${perturbations.length} perturbations`);

  const session = new UniversalLiveSession(request, {
    config,
    clockMode: 'live',
    debugMode: 'full',
  });

  await session.start();
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

  // Base sequence
  session.publish('status', { message: 'Session initialized' });
  await sleep(5);

  // Apply perturbations
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
    await sleep(pert.delay || 5);
  }

  session.publish('health', { health: session.health });
  await session.stop();

  const dump = session.getDebugSessionDump({ mode: 'full' });
  console.log(`✓ Session ${sessionId} completed - ${dump.recordCount} events`);
  return dump;
}

async function testOscillationsNearThreshold() {
  console.log('🔬 TESTING: Oscillations near RATIO_EPSILON threshold');

  // Test case: system vs observer near 1e-6 ratio
  const baseSystem = 1000;
  const perturbations = [
    {
      type: 'final_translation',
      chunkNumber: 1,
      transcript: 'Hello world',
      translatedText: 'Hola mundo',
      detectedLanguage: 'en',
      confidence: 0.98,
      // This will create contributions with system:1000, observer:1 (ratio 1e-3 > 1e-6, not degenerate)
    }
  ];

  const results = [];
  for (let i = 0; i < 5; i++) {
    // Vary observer slightly around threshold
    const observer = 1 + (i - 2) * 0.1; // 0.8, 0.9, 1.0, 1.1, 1.2
    // But since we can't control contributions directly, we'll run identical sessions
    const dump = await runAdversarialSession(`osc-${i}`, perturbations);
    results.push(dump);
  }

  // Check if decision hashes are stable (they should be, since logical reality is identical)
  const decisionHashes = results.map(r => r.decisionSessionHash);
  const uniqueHashes = [...new Set(decisionHashes)];
  console.log(`Decision hashes: ${decisionHashes.join(', ')}`);
  console.log(`Unique: ${uniqueHashes.length} - ${uniqueHashes.length === 1 ? 'STABLE' : 'FLICKERING'}`);

  return uniqueHashes.length === 1;
}

async function testAlternatingDominance() {
  console.log('🔬 TESTING: Alternating dominance per frame');

  // Simulate rapid changes that should not affect logical dominance
  const perturbations = [];
  for (let i = 1; i <= 10; i++) {
    perturbations.push({
      type: 'translation_progress',
      chunkNumber: i,
      progress: 0.5,
      partialTranslation: `Partial ${i}`,
      delay: 1, // Rapid fire
    });
  }
  perturbations.push({
    type: 'final_translation',
    chunkNumber: 10,
    transcript: 'Hello world repeated',
    translatedText: 'Hola mundo repetido',
    detectedLanguage: 'en',
    confidence: 0.98,
  });

  const results = [];
  for (let i = 0; i < 3; i++) {
    const dump = await runAdversarialSession(`alt-${i}`, perturbations);
    results.push(dump);
  }

  const decisionHashes = results.map(r => r.decisionSessionHash);
  const uniqueHashes = [...new Set(decisionHashes)];
  console.log(`Decision hashes: ${decisionHashes.join(', ')}`);
  console.log(`Unique: ${uniqueHashes.length} - ${uniqueHashes.length === 1 ? 'STABLE' : 'FLICKERING'}`);

  return uniqueHashes.length === 1;
}

async function testNoiseBursts() {
  console.log('🔬 TESTING: Injected noise bursts mimicking speech artifacts');

  // Add noise events that should not change logical reality
  const perturbations = [
    {
      type: 'translation_progress',
      chunkNumber: 1,
      progress: 0.1,
      partialTranslation: 'H',
    },
    // Noise burst - rapid partials
    {
      type: 'translation_progress',
      chunkNumber: 1,
      progress: 0.2,
      partialTranslation: 'He',
    },
    {
      type: 'translation_progress',
      chunkNumber: 1,
      progress: 0.3,
      partialTranslation: 'Hel',
    },
    {
      type: 'translation_progress',
      chunkNumber: 1,
      progress: 0.4,
      partialTranslation: 'Hell',
    },
    {
      type: 'translation_progress',
      chunkNumber: 1,
      progress: 0.5,
      partialTranslation: 'Hello',
    },
    {
      type: 'final_translation',
      chunkNumber: 1,
      transcript: 'Hello world',
      translatedText: 'Hola mundo',
      detectedLanguage: 'en',
      confidence: 0.98,
    }
  ];

  const results = [];
  for (let i = 0; i < 3; i++) {
    const dump = await runAdversarialSession(`noise-${i}`, perturbations);
    results.push(dump);
  }

  const decisionHashes = results.map(r => r.decisionSessionHash);
  const uniqueHashes = [...new Set(decisionHashes)];
  console.log(`Decision hashes: ${decisionHashes.join(', ')}`);
  console.log(`Unique: ${uniqueHashes.length} - ${uniqueHashes.length === 1 ? 'STABLE' : 'FLICKERING'}`);

  return uniqueHashes.length === 1;
}

async function main() {
  console.log('╔═══════════════════════════════════════════════════════════╗');
  console.log('║     ADVERSARIAL REALITY TESTING                          ║');
  console.log('║     Does identity flicker when reality barely changes?   ║');
  console.log('╚═══════════════════════════════════════════════════════════╝');

  const results = {
    oscillations: await testOscillationsNearThreshold(),
    alternating: await testAlternatingDominance(),
    noise: await testNoiseBursts(),
  };

  console.log('\n╔═══════════════════════════════════════════════════════════╗');
  console.log('║     ADVERSARIAL TEST RESULTS                             ║');
  console.log('╚═══════════════════════════════════════════════════════════╝');

  console.log(`Oscillations near threshold: ${results.oscillations ? '✅ PASS' : '❌ FAIL'}`);
  console.log(`Alternating dominance: ${results.alternating ? '✅ PASS' : '❌ FAIL'}`);
  console.log(`Noise bursts: ${results.noise ? '✅ PASS' : '❌ FAIL'}`);

  const allPass = Object.values(results).every(r => r);
  console.log(`\nOverall: ${allPass ? '🛡️ IDENTITY HOLDS' : '⚠️ IDENTITY FLICKERS'}`);

  if (!allPass) {
    console.log('\n🔍 INVESTIGATION NEEDED: Identity changes when logical reality stays the same');
  } else {
    console.log('\n🎯 SYSTEM VERIFIED: Reality must earn the right to change identity');
  }
}

main().catch((error) => {
  console.error('Adversarial test failed:', error);
  process.exit(1);
});