const path = require('path');
const { UniversalLiveSession } = require('./live-session');

async function main() {
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
  console.log('recordCount', dump.recordCount, 'decisionSessionHash', dump.decisionSessionHash, 'logicSessionHash', dump.logicSessionHash, 'timingSessionHash', dump.timingSessionHash);
  dump.events.forEach((e) => console.log(e.sequence, e.type, e.decisionHash, e.logicHash, e.normalizedTime, JSON.stringify(e.contributions)));
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});