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
  return {
    runNumber,
    id: event.id,
    causalityKey: event.causalityKey,
    weights: event.weights,
    confidences: event.confidences,
    ignoredDomainsDecision: event.ignoredDomainsDecision,
    contributions: event.contributions,
    logicHash: event.logicHash,
    decisionHash: event.decisionHash,
  };
}

async function main() {
  const results = [];
  for (let i = 1; i <= 3; i += 1) {
    const result = await runSession(i);
    console.log(JSON.stringify(result, null, 2));
    results.push(result);
  }
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
