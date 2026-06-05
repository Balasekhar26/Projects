const path = require('path');
const { UniversalLiveSession } = require('./src/session/live-session');

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function runSession(runNumber) {
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
    config: {
      tempDir: path.join(__dirname, '.tmp'),
      modelsDir: path.join(__dirname, 'models'),
    },
    clockMode: 'live',
    debugMode: 'full',
  });

  await session.start();
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
  session.publish('tts_started', { chunkNumber: 1, translatedText: 'Hola mundo' });
  await sleep(5);
  session.publish('tts_finished', { chunkNumber: 1, translatedText: 'Hola mundo' });
  await sleep(5);
  session.publish('health', { health: session.health });
  await session.stop();

  const dump = session.getDebugSessionDump({ mode: 'full' });
  const eventSummary = dump.events.find((e) => e.type === 'final_translation');
  const event = session.getDebugEvent(eventSummary.id, 'full');
  
  const raw = event.contributions || {};
  const normalized = {};
  const decisionDomains = ["system", "observer"].filter((domain) => Object.prototype.hasOwnProperty.call(raw, domain));
  const primaryTotal = decisionDomains.reduce((sum, domain) => sum + Math.abs(raw[domain] || 0), 0);

  for (const domain of Object.keys(raw).sort()) {
    if (decisionDomains.length > 0 && decisionDomains.includes(domain)) {
      normalized[domain] = primaryTotal === 0 ? 0 : Number((raw[domain] / primaryTotal).toFixed(6));
    } else {
      normalized[domain] = raw[domain] === 0 ? 0 : 1;
    }
  }

  return {
    runNumber,
    raw: raw,
    normalized: normalized,
    decisionHash: event.decisionHash,
    logicHash: event.logicHash,
  };
}

async function main() {
  const results = [];
  for (let i = 1; i <= 3; i += 1) {
    const result = await runSession(i);
    results.push(result);
  }

  console.log('\n╔═══════════════════════════════════════════════════════════╗');
  console.log('║     NORMALIZED CONTRIBUTION VERIFICATION                  ║');
  console.log('╚═══════════════════════════════════════════════════════════╝\n');

  results.forEach((result) => {
    console.log(`Run ${result.runNumber}:`);
    console.log(`  Raw contributions:        ${JSON.stringify(result.raw)}`);
    console.log(`  Normalized contributions: ${JSON.stringify(result.normalized)}`);
    console.log(`  Decision Hash: ${result.decisionHash}`);
    console.log(`  Logic Hash:    ${result.logicHash}`);
    console.log();
  });

  console.log('\n╔═══════════════════════════════════════════════════════════╗');
  console.log('║     STABILITY CHECK (Normalized system/observer ratio)    ║');
  console.log('╚═══════════════════════════════════════════════════════════╝\n');

  const systemObserverRatios = results.map((r) => {
    const sys = r.normalized.system || 0;
    const obs = r.normalized.observer || 0;
    return obs !== 0 ? Number((sys / obs).toFixed(6)) : 'N/A';
  });

  console.log('System/Observer Ratios Across Runs:');
  systemObserverRatios.forEach((ratio, i) => {
    console.log(`  Run ${i + 1}: ${ratio}`);
  });

  const ratiosEqual = systemObserverRatios.every((r, i) => {
    if (i === 0) return true;
    const prev = systemObserverRatios[i - 1];
    if (typeof r === 'string' || typeof prev === 'string') return r === prev;
    return Math.abs(r - prev) < 0.0001;
  });

  console.log(`\n✓ Ratios Stable: ${ratiosEqual ? 'YES ✅' : 'NO ❌'}`);
  console.log();
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
