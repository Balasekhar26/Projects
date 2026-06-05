#!/usr/bin/env node

const fs = require('fs');
const path = require('path');
const readline = require('readline');
const { execSync } = require('child_process');

const rl = readline.createInterface({
  input: process.stdin,
  output: process.stdout
});

function question(prompt) {
  return new Promise((resolve) => {
    rl.question(prompt, resolve);
  });
}

function clearScreen() {
  console.clear();
}

function showHeader(step, title) {
  console.log('='.repeat(60));
  console.log(`   ULT TRANSLATOR - FIRST-RUN SETUP WIZARD`);
  console.log(`   Step ${step}/8: ${title}`);
  console.log('='.repeat(60));
  console.log();
}

async function checkSystemRequirements() {
  showHeader(1, 'System Requirements Check');

  console.log('Checking system requirements...\n');

  // Check Node.js
  try {
    const nodeVersion = execSync('node --version', { encoding: 'utf8' }).trim();
    console.log(`✓ Node.js: ${nodeVersion}`);
  } catch (e) {
    console.log('✗ Node.js: Not found');
    return false;
  }

  // Check Python
  try {
    const pythonVersion = execSync('python --version', { encoding: 'utf8' }).trim();
    console.log(`✓ Python: ${pythonVersion}`);
  } catch (e) {
    try {
      const pyVersion = execSync('py --version', { encoding: 'utf8' }).trim();
      console.log(`✓ Python: ${pyVersion}`);
    } catch (e) {
      console.log('✗ Python: Not found');
      return false;
    }
  }

  // Check virtual environment
  if (fs.existsSync(path.join(__dirname, 'venv'))) {
    console.log('✓ Python virtual environment: Present');
  } else {
    console.log('✗ Python virtual environment: Missing');
    return false;
  }

  // Check database
  if (fs.existsSync(path.join(__dirname, 'ult.db'))) {
    console.log('✓ Database: Initialized');
  } else {
    console.log('⚠ Database: Will be initialized');
  }

  console.log('\n✓ All system requirements met!');
  await question('Press Enter to continue...');
  return true;
}

async function configureAudioDevices() {
  showHeader(2, 'Audio Device Configuration');

  console.log('ULT requires audio device configuration for optimal performance.\n');

  console.log('Available audio devices:');
  try {
    const devices = execSync('powershell -Command "Get-AudioDevice -List | Format-Table -Property Name,Type,Default | Out-String"', { encoding: 'utf8' });
    console.log(devices);
  } catch (e) {
    console.log('Could not enumerate audio devices. Please ensure audio drivers are installed.');
  }

  console.log('\nFor full functionality, install VB-Audio Virtual Cable:');
  console.log('https://vb-audio.com/Cable/\n');

  const hasVBCable = await question('Do you have VB-Cable or similar virtual audio driver installed? (y/n): ');
  if (hasVBCable.toLowerCase() !== 'y') {
    console.log('\n⚠ WARNING: Audio interception features will be limited without virtual audio drivers.');
    console.log('Install VB-Cable and reboot before using speaker interception mode.\n');
  }

  await question('Press Enter to continue...');
  return true;
}

async function configureLanguages() {
  showHeader(3, 'Language Configuration');

  console.log('ULT supports real-time translation between 40+ languages.\n');

  console.log('Available STT languages (Whisper):');
  console.log('- English, Spanish, French, German, Italian, Portuguese, Russian');
  console.log('- Chinese, Japanese, Korean, Arabic, Hindi, and many more...\n');

  console.log('Available translation languages (Argos Translate):');
  console.log('- All major world languages with neural machine translation\n');

  const sourceLang = await question('Enter your primary source language (default: English): ') || 'English';
  const targetLang = await question('Enter your primary target language (default: Spanish): ') || 'Spanish';

  console.log(`\nConfigured: ${sourceLang} → ${targetLang}`);
  console.log('You can change these settings in the app preferences.\n');

  // Save to config
  const config = {
    languages: {
      source: sourceLang,
      target: targetLang
    }
  };

  fs.writeFileSync(path.join(__dirname, 'config', 'user-config.json'), JSON.stringify(config, null, 2));
  await question('Press Enter to continue...');
  return true;
}

async function configureVoiceSettings() {
  showHeader(4, 'Voice & TTS Configuration');

  console.log('ULT preserves voice characteristics and emotions during translation.\n');

  console.log('Available TTS engines:');
  console.log('1. XTTS v2 - High-quality neural voice cloning');
  console.log('2. ElevenLabs - Premium voice synthesis');
  console.log('3. PyTTSx3 - Local system TTS (fallback)\n');

  const ttsChoice = await question('Choose TTS engine (1-3, default: 1): ') || '1';

  let ttsEngine = 'xtts';
  switch (ttsChoice) {
    case '1': ttsEngine = 'xtts'; break;
    case '2': ttsEngine = 'elevenlabs'; break;
    case '3': ttsEngine = 'pyttsx3'; break;
  }

  console.log(`Selected TTS engine: ${ttsEngine.toUpperCase()}\n`);

  const preserveVoice = await question('Enable voice preservation/cloning? (y/n, default: y): ') || 'y';
  const emotionAnalysis = await question('Enable emotion analysis? (y/n, default: y): ') || 'y';

  // Update config
  const configPath = path.join(__dirname, 'config', 'user-config.json');
  let config = {};
  if (fs.existsSync(configPath)) {
    config = JSON.parse(fs.readFileSync(configPath, 'utf8'));
  }

  config.voice = {
    ttsEngine,
    preserveVoice: preserveVoice.toLowerCase() === 'y',
    emotionAnalysis: emotionAnalysis.toLowerCase() === 'y'
  };

  fs.writeFileSync(configPath, JSON.stringify(config, null, 2));
  await question('Press Enter to continue...');
  return true;
}

async function configureNetworkSettings() {
  showHeader(5, 'Network & API Configuration');

  console.log('ULT can operate in offline mode or with online AI services.\n');

  const onlineMode = await question('Enable online mode for enhanced AI features? (y/n, default: n): ') || 'n';

  if (onlineMode.toLowerCase() === 'y') {
    console.log('\nOnline mode requires API keys for:');
    console.log('- OpenAI GPT (optional, for advanced features)');
    console.log('- ElevenLabs (if using ElevenLabs TTS)');
    console.log('- Other AI services\n');

    const openaiKey = await question('OpenAI API Key (leave blank to skip): ');
    const elevenlabsKey = await question('ElevenLabs API Key (leave blank to skip): ');

    // Update .env file
    let envContent = '';
    if (fs.existsSync(path.join(__dirname, '.env'))) {
      envContent = fs.readFileSync(path.join(__dirname, '.env'), 'utf8');
    }

    if (openaiKey) {
      envContent = envContent.replace(/OPENAI_API_KEY=.*/, `OPENAI_API_KEY=${openaiKey}`);
      if (!envContent.includes('OPENAI_API_KEY=')) {
        envContent += `\nOPENAI_API_KEY=${openaiKey}`;
      }
    }

    if (elevenlabsKey) {
      envContent = envContent.replace(/ELEVENLABS_API_KEY=.*/, `ELEVENLABS_API_KEY=${elevenlabsKey}`);
      if (!envContent.includes('ELEVENLABS_API_KEY=')) {
        envContent += `\nELEVENLABS_API_KEY=${elevenlabsKey}`;
      }
    }

    fs.writeFileSync(path.join(__dirname, '.env'), envContent);
    console.log('\n✓ API keys configured');
  } else {
    console.log('\n✓ Operating in offline mode');
  }

  // Update config
  const configPath = path.join(__dirname, 'config', 'user-config.json');
  let config = {};
  if (fs.existsSync(configPath)) {
    config = JSON.parse(fs.readFileSync(configPath, 'utf8'));
  }

  config.network = {
    onlineMode: onlineMode.toLowerCase() === 'y'
  };

  fs.writeFileSync(configPath, JSON.stringify(config, null, 2));
  await question('Press Enter to continue...');
  return true;
}

async function configurePerformance() {
  showHeader(6, 'Performance Configuration');

  console.log('Configure performance settings for your system.\n');

  console.log('Available models:');
  console.log('1. Fast (Whisper Tiny) - Low latency, basic accuracy');
  console.log('2. Balanced (Whisper Base) - Good balance');
  console.log('3. Accurate (Whisper Small) - High accuracy, slower');
  console.log('4. Ultra (Whisper Medium) - Maximum accuracy\n');

  const modelChoice = await question('Choose STT model (1-4, default: 2): ') || '2';

  let modelSize = 'base';
  switch (modelChoice) {
    case '1': modelSize = 'tiny'; break;
    case '2': modelSize = 'base'; break;
    case '3': modelSize = 'small'; break;
    case '4': modelSize = 'medium'; break;
  }

  console.log(`Selected model: Whisper ${modelSize.toUpperCase()}\n`);

  const chunkSize = await question('Audio chunk size in seconds (1-10, default: 3): ') || '3';
  const overlap = await question('Chunk overlap in seconds (0-2, default: 0.5): ') || '0.5';

  // Update config
  const configPath = path.join(__dirname, 'config', 'user-config.json');
  let config = {};
  if (fs.existsSync(configPath)) {
    config = JSON.parse(fs.readFileSync(configPath, 'utf8'));
  }

  config.performance = {
    sttModel: modelSize,
    chunkSize: parseFloat(chunkSize),
    overlap: parseFloat(overlap)
  };

  fs.writeFileSync(configPath, JSON.stringify(config, null, 2));
  await question('Press Enter to continue...');
  return true;
}

async function configurePrivacy() {
  showHeader(7, 'Privacy & Security');

  console.log('ULT takes privacy seriously. Configure your preferences.\n');

  const saveTranscripts = await question('Save translation transcripts to database? (y/n, default: y): ') || 'y';
  const saveAudio = await question('Save audio recordings? (y/n, default: n): ') || 'n';
  const analytics = await question('Enable anonymous usage analytics? (y/n, default: n): ') || 'n';

  console.log('\nSecurity features:');
  console.log('- Voice profiles are encrypted locally');
  console.log('- No audio data sent to external servers in offline mode');
  console.log('- API keys are stored securely in .env file\n');

  // Update config
  const configPath = path.join(__dirname, 'config', 'user-config.json');
  let config = {};
  if (fs.existsSync(configPath)) {
    config = JSON.parse(fs.readFileSync(configPath, 'utf8'));
  }

  config.privacy = {
    saveTranscripts: saveTranscripts.toLowerCase() === 'y',
    saveAudio: saveAudio.toLowerCase() === 'y',
    analytics: analytics.toLowerCase() === 'y'
  };

  fs.writeFileSync(configPath, JSON.stringify(config, null, 2));
  await question('Press Enter to continue...');
  return true;
}

async function finalizeSetup() {
  showHeader(8, 'Setup Complete');

  console.log('🎉 ULT Translator setup is complete!\n');

  console.log('Configuration summary:');
  const configPath = path.join(__dirname, 'config', 'user-config.json');
  if (fs.existsSync(configPath)) {
    const config = JSON.parse(fs.readFileSync(configPath, 'utf8'));
    console.log(`- Languages: ${config.languages?.source || 'English'} → ${config.languages?.target || 'Spanish'}`);
    console.log(`- TTS Engine: ${config.voice?.ttsEngine?.toUpperCase() || 'XTTS'}`);
    console.log(`- Voice Preservation: ${config.voice?.preserveVoice ? 'Enabled' : 'Disabled'}`);
    console.log(`- Online Mode: ${config.network?.onlineMode ? 'Enabled' : 'Disabled'}`);
    console.log(`- STT Model: Whisper ${config.performance?.sttModel?.toUpperCase() || 'BASE'}`);
  }

  console.log('\nNext steps:');
  console.log('1. Launch the ULT Translator application');
  console.log('2. Test audio input/output devices');
  console.log('3. Try a translation session');
  console.log('4. Adjust settings as needed\n');

  console.log('For help and documentation:');
  console.log('- Press F1 in the app for keyboard shortcuts');
  console.log('- Check the settings panel for advanced options');
  console.log('- Visit the project README for troubleshooting\n');

  await question('Press Enter to start ULT Translator...');

  // Create setup complete flag
  fs.writeFileSync(path.join(__dirname, 'setup_complete.flag'), '');

  rl.close();
  return true;
}

async function main() {
  clearScreen();

  try {
    const steps = [
      checkSystemRequirements,
      configureAudioDevices,
      configureLanguages,
      configureVoiceSettings,
      configureNetworkSettings,
      configurePerformance,
      configurePrivacy,
      finalizeSetup
    ];

    for (const step of steps) {
      clearScreen();
      const success = await step();
      if (!success) {
        console.log('\nSetup failed. Please resolve the issues and run setup again.');
        process.exit(1);
      }
    }

    console.log('\nStarting ULT Translator...');
    process.exit(0);

  } catch (error) {
    console.error('\nSetup wizard encountered an error:', error.message);
    process.exit(1);
  }
}

main();