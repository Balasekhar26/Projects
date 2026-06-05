#!/usr/bin/env node

const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

console.log('========================================');
console.log('  ULT Translator - Dependency Check');
console.log('========================================');
console.log();

let allGood = true;

function checkDependency(name, command, required = true) {
  try {
    const result = execSync(command, { encoding: 'utf8', stdio: 'pipe' });
    const version = result.trim().split('\n')[0];
    console.log(`✓ ${name}: ${version}`);
    return true;
  } catch (error) {
    if (required) {
      console.log(`✗ ${name}: Not found or failed`);
      allGood = false;
      return false;
    } else {
      console.log(`⚠ ${name}: Not found (optional)`);
      return true;
    }
  }
}

function checkFile(name, filePath, required = true) {
  if (fs.existsSync(filePath)) {
    console.log(`✓ ${name}: Present`);
    return true;
  } else {
    if (required) {
      console.log(`✗ ${name}: Missing`);
      allGood = false;
      return false;
    } else {
      console.log(`⚠ ${name}: Missing (optional)`);
      return true;
    }
  }
}

function checkDirectory(name, dirPath, required = true) {
  if (fs.existsSync(dirPath) && fs.statSync(dirPath).isDirectory()) {
    console.log(`✓ ${name}: Present`);
    return true;
  } else {
    if (required) {
      console.log(`✗ ${name}: Missing`);
      allGood = false;
      return false;
    } else {
      console.log(`⚠ ${name}: Missing (optional)`);
      return true;
    }
  }
}

// Core system requirements
console.log('System Requirements:');
console.log('-------------------');
checkDependency('Node.js', 'node --version');
checkDependency('npm', 'npm --version');

// Python environment
console.log();
console.log('Python Environment:');
console.log('-------------------');
checkDependency('Python', 'python --version', false);
if (!checkDependency('Python (py command)', 'py --version', false)) {
  console.log('  Note: Python not found via standard commands');
}
checkDirectory('Python venv', path.join(__dirname, 'venv'));

// Check Python packages if venv exists
if (fs.existsSync(path.join(__dirname, 'venv'))) {
  try {
    execSync('call venv\\Scripts\\activate.bat && python -c "import torch; print(f\'PyTorch: {torch.__version__}\')"', { stdio: 'pipe' });
    console.log('✓ PyTorch: Available');
  } catch (e) {
    console.log('✗ PyTorch: Not available');
    allGood = false;
  }

  try {
    execSync('call venv\\Scripts\\activate.bat && python -c "import faster_whisper; print(\'Faster Whisper: Available\')"', { stdio: 'pipe' });
    console.log('✓ Faster Whisper: Available');
  } catch (e) {
    console.log('⚠ Faster Whisper: Not available (will use alternative STT)');
    // Don't fail on this - system can work with alternatives
  }

  try {
    execSync('call venv\\Scripts\\activate.bat && python -c "import argostranslate; print(\'Argos Translate: Available\')"', { stdio: 'pipe' });
    console.log('✓ Argos Translate: Available');
  } catch (e) {
    console.log('✗ Argos Translate: Not available');
    allGood = false;
  }
}

// Node.js dependencies
console.log();
console.log('Node.js Dependencies:');
console.log('--------------------');
checkFile('package.json', path.join(__dirname, 'package.json'));
checkDirectory('node_modules', path.join(__dirname, 'node_modules'));

// Application files
console.log();
console.log('Application Files:');
console.log('------------------');
checkFile('Main Electron file', path.join(__dirname, 'electron', 'main.js'));
checkFile('Next.js app', path.join(__dirname, 'package.json')); // Already checked above
checkDirectory('Models directory', path.join(__dirname, 'models'));

// Database
console.log();
console.log('Database:');
console.log('---------');
checkFile('Database file', path.join(__dirname, 'ult.db'), false);

// Audio drivers (optional but recommended)
console.log();
console.log('Audio Drivers (Recommended):');
console.log('----------------------------');
try {
  const audioDevices = execSync('powershell -Command "Get-AudioDevice -List | Where-Object { $_.Name -like \'*VB-*\' -or $_.Name -like \'*VoiceMeeter*\' } | Measure-Object | Select-Object -ExpandProperty Count"', { encoding: 'utf8' }).trim();
  if (parseInt(audioDevices) > 0) {
    console.log('✓ Virtual audio drivers: Detected');
  } else {
    console.log('⚠ Virtual audio drivers: Not detected');
    console.log('  Note: Install VB-Cable for full audio interception: https://vb-audio.com/Cable/');
  }
} catch (e) {
  console.log('⚠ Virtual audio drivers: Could not check (AudioDeviceTools module not available)');
  console.log('  Note: Install VB-Cable for full audio interception: https://vb-audio.com/Cable/');
}

// Configuration
console.log();
console.log('Configuration:');
console.log('--------------');
checkFile('Environment file', path.join(__dirname, '.env'), false);
checkFile('User config', path.join(__dirname, 'config', 'user-config.json'), false);
checkFile('Setup complete flag', path.join(__dirname, 'setup_complete.flag'), false);

// Performance check
console.log();
console.log('Performance Check:');
console.log('------------------');
try {
  const memInfo = execSync('wmic computersystem get totalphysicalmemory /value', { encoding: 'utf8' });
  const ramMatch = memInfo.match(/TotalPhysicalMemory=(\d+)/);
  if (ramMatch) {
    const ramGB = Math.round(parseInt(ramMatch[1]) / 1024 / 1024 / 1024);
    if (ramGB >= 4) {
      console.log(`✓ System RAM: ${ramGB} GB (Recommended: 4GB+)`);
    } else {
      console.log(`⚠ System RAM: ${ramGB} GB (Recommended: 4GB+)`);
    }
  }
} catch (e) {
  console.log('⚠ System RAM: Could not check');
}

console.log();
console.log('========================================');

if (allGood) {
  console.log('✓ All critical dependencies satisfied!');
  console.log('========================================');
  process.exit(0);
} else {
  console.log('✗ Some dependencies are missing or failed!');
  console.log('========================================');
  console.log();
  console.log('Please run setup.bat to fix missing dependencies.');
  process.exit(1);
}
