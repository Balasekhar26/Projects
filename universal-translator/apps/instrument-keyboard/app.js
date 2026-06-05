"use strict";

const INSTRUMENTS = {
  piano: {
    label: "Piano",
    type: "triangle",
    gain: 0.64,
    attack: 0.008,
    decay: 0.22,
    sustain: 0.22,
    release: 0.58,
    filter: 5200,
    detune: [0, 5],
  },
  guitar: {
    label: "Guitar",
    type: "sawtooth",
    gain: 0.36,
    attack: 0.004,
    decay: 0.18,
    sustain: 0.16,
    release: 0.7,
    filter: 2400,
    detune: [0, -8, 8],
  },
  flute: {
    label: "Flute",
    type: "sine",
    gain: 0.5,
    attack: 0.045,
    decay: 0.16,
    sustain: 0.46,
    release: 0.5,
    filter: 4600,
    detune: [0, 3],
    vibrato: true,
  },
  organ: {
    label: "Organ",
    type: "square",
    gain: 0.32,
    attack: 0.015,
    decay: 0.08,
    sustain: 0.72,
    release: 0.3,
    filter: 3600,
    detune: [0, 7, 12],
  },
  synth: {
    label: "Synth Lead",
    type: "sawtooth",
    gain: 0.42,
    attack: 0.018,
    decay: 0.14,
    sustain: 0.42,
    release: 0.42,
    filter: 6200,
    detune: [0, -11, 11],
    vibrato: true,
  },
  bass: {
    label: "Bass",
    type: "square",
    gain: 0.5,
    attack: 0.01,
    decay: 0.18,
    sustain: 0.5,
    release: 0.36,
    filter: 900,
    detune: [0, -5],
    octaveOffset: -1,
  },
  bell: {
    label: "Bell",
    type: "sine",
    gain: 0.5,
    attack: 0.002,
    decay: 0.34,
    sustain: 0.08,
    release: 1.15,
    filter: 7800,
    detune: [0, 1200, 1900],
  },
};

const KEY_ROWS = [
  [
    "Escape",
    "F1",
    "F2",
    "F3",
    "F4",
    "F5",
    "F6",
    "F7",
    "F8",
    "F9",
    "F10",
    "F11",
    "F12",
  ],
  [
    "Backquote",
    "Digit1",
    "Digit2",
    "Digit3",
    "Digit4",
    "Digit5",
    "Digit6",
    "Digit7",
    "Digit8",
    "Digit9",
    "Digit0",
    "Minus",
    "Equal",
    "Backspace",
  ],
  [
    "Tab",
    "KeyQ",
    "KeyW",
    "KeyE",
    "KeyR",
    "KeyT",
    "KeyY",
    "KeyU",
    "KeyI",
    "KeyO",
    "KeyP",
    "BracketLeft",
    "BracketRight",
    "Backslash",
  ],
  [
    "CapsLock",
    "KeyA",
    "KeyS",
    "KeyD",
    "KeyF",
    "KeyG",
    "KeyH",
    "KeyJ",
    "KeyK",
    "KeyL",
    "Semicolon",
    "Quote",
    "Enter",
  ],
  [
    "ShiftLeft",
    "KeyZ",
    "KeyX",
    "KeyC",
    "KeyV",
    "KeyB",
    "KeyN",
    "KeyM",
    "Comma",
    "Period",
    "Slash",
    "ShiftRight",
  ],
  [
    "ControlLeft",
    "AltLeft",
    "MetaLeft",
    "Space",
    "MetaRight",
    "AltRight",
    "ControlRight",
    "ArrowLeft",
    "ArrowUp",
    "ArrowDown",
    "ArrowRight",
  ],
  ["Insert", "Delete", "Home", "End", "PageUp", "PageDown", "Numpad7", "Numpad8", "Numpad9"],
  [
    "Numpad4",
    "Numpad5",
    "Numpad6",
    "Numpad1",
    "Numpad2",
    "Numpad3",
    "Numpad0",
    "NumpadDecimal",
    "NumpadEnter",
  ],
];

const NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];
const pressedCodes = new Set();
const activeVoices = new Map();
const buttonsByCode = new Map();

let audioContext;
let masterGain;
let analyser;
let scopeCanvas;
let scopeContext;
let scopeFrame;

const instrumentSelect = document.getElementById("instrument-select");
const octaveSelect = document.getElementById("octave-select");
const sustainToggle = document.getElementById("sustain-toggle");
const panicButton = document.getElementById("panic-button");
const lastKey = document.getElementById("last-key");
const lastNote = document.getElementById("last-note");
const offlineStatus = document.getElementById("offline-status");
const keyboardGrid = document.getElementById("keyboard-grid");

function init() {
  populateInstruments();
  renderKeyboard();
  scopeCanvas = document.getElementById("scope");
  scopeContext = scopeCanvas.getContext("2d");

  window.addEventListener("keydown", handleKeyDown);
  window.addEventListener("keyup", handleKeyUp);
  window.addEventListener("blur", stopAllNotes);
  panicButton.addEventListener("click", stopAllNotes);

  if ("serviceWorker" in navigator && window.isSecureContext) {
    navigator.serviceWorker
      .register("./sw.js")
      .then(() => {
        offlineStatus.textContent = "Installable offline";
      })
      .catch(() => {
        offlineStatus.textContent = "Offline files ready";
      });
  }
}

function populateInstruments() {
  for (const [id, instrument] of Object.entries(INSTRUMENTS)) {
    const option = document.createElement("option");
    option.value = id;
    option.textContent = instrument.label;
    instrumentSelect.appendChild(option);
  }
}

function renderKeyboard() {
  for (const row of KEY_ROWS) {
    const rowElement = document.createElement("div");
    rowElement.className = "key-row";
    for (const code of row) {
      const button = document.createElement("button");
      const label = labelForCode(code);
      const note = noteForCode(code);
      button.type = "button";
      button.className = classForCode(code);
      button.dataset.code = code;
      button.innerHTML = `<span class="key-label">${escapeHtml(label)}</span><span class="key-note">${note.name}</span>`;
      button.addEventListener("pointerdown", (event) => {
        event.preventDefault();
        playKey(code);
      });
      button.addEventListener("pointerup", (event) => {
        event.preventDefault();
        releaseKey(code);
      });
      button.addEventListener("pointerleave", () => releaseKey(code));
      rowElement.appendChild(button);
      buttonsByCode.set(code, button);
    }
    keyboardGrid.appendChild(rowElement);
  }
}

function handleKeyDown(event) {
  if (event.repeat) {
    return;
  }

  const code = event.code || normalizeFallbackCode(event.key);
  if (!code) {
    return;
  }

  if (!event.ctrlKey && !event.metaKey && !event.altKey) {
    event.preventDefault();
  }

  playKey(code, event.key);
}

function handleKeyUp(event) {
  const code = event.code || normalizeFallbackCode(event.key);
  if (!code) {
    return;
  }
  releaseKey(code);
}

function playKey(code, rawKey = "") {
  ensureAudio();
  if (pressedCodes.has(code)) {
    return;
  }

  pressedCodes.add(code);
  const note = noteForCode(code);
  const instrument = INSTRUMENTS[instrumentSelect.value] || INSTRUMENTS.piano;
  const voice = createVoice(note.frequency, instrument);
  activeVoices.set(code, voice);
  markButton(code, true);
  lastKey.textContent = labelForCode(code, rawKey);
  lastNote.textContent = `${note.name} · ${instrument.label}`;
}

function releaseKey(code) {
  pressedCodes.delete(code);
  markButton(code, false);
  if (sustainToggle.checked) {
    return;
  }

  const voice = activeVoices.get(code);
  if (!voice) {
    return;
  }

  voice.stop();
  activeVoices.delete(code);
}

function stopAllNotes() {
  for (const voice of activeVoices.values()) {
    voice.stop(true);
  }
  activeVoices.clear();
  pressedCodes.clear();
  for (const button of buttonsByCode.values()) {
    button.classList.remove("playing");
  }
}

function ensureAudio() {
  if (audioContext) {
    if (audioContext.state === "suspended") {
      void audioContext.resume();
    }
    return;
  }

  const AudioContextClass = window.AudioContext || window.webkitAudioContext;
  audioContext = new AudioContextClass();
  masterGain = audioContext.createGain();
  masterGain.gain.value = 0.82;
  analyser = audioContext.createAnalyser();
  analyser.fftSize = 1024;
  masterGain.connect(analyser);
  analyser.connect(audioContext.destination);
  drawScope();
}

function createVoice(baseFrequency, instrument) {
  const now = audioContext.currentTime;
  const output = audioContext.createGain();
  const filter = audioContext.createBiquadFilter();
  const vibrato = audioContext.createOscillator();
  const vibratoGain = audioContext.createGain();
  const oscillators = [];
  const targetFrequency = baseFrequency * Math.pow(2, instrument.octaveOffset || 0);
  const gainPeak = instrument.gain;
  const sustainLevel = Math.max(0.0001, gainPeak * instrument.sustain);

  filter.type = "lowpass";
  filter.frequency.setValueAtTime(instrument.filter, now);
  filter.Q.value = 0.8;

  output.gain.setValueAtTime(0.0001, now);
  output.gain.exponentialRampToValueAtTime(gainPeak, now + instrument.attack);
  output.gain.exponentialRampToValueAtTime(sustainLevel, now + instrument.attack + instrument.decay);

  if (instrument.vibrato) {
    vibrato.type = "sine";
    vibrato.frequency.value = 5.4;
    vibratoGain.gain.value = 5;
    vibrato.connect(vibratoGain);
    vibrato.start(now);
  }

  for (const detune of instrument.detune) {
    const oscillator = audioContext.createOscillator();
    oscillator.type = instrument.type;
    oscillator.frequency.setValueAtTime(targetFrequency, now);
    oscillator.detune.value = detune;
    if (instrument.vibrato) {
      vibratoGain.connect(oscillator.detune);
    }
    oscillator.connect(filter);
    oscillator.start(now);
    oscillators.push(oscillator);
  }

  filter.connect(output);
  output.connect(masterGain);

  return {
    stop(immediate = false) {
      const stopAt = audioContext.currentTime + (immediate ? 0.03 : instrument.release);
      output.gain.cancelScheduledValues(audioContext.currentTime);
      output.gain.setTargetAtTime(0.0001, audioContext.currentTime, immediate ? 0.01 : instrument.release / 4);
      for (const oscillator of oscillators) {
        oscillator.stop(stopAt + 0.04);
      }
      if (instrument.vibrato) {
        vibrato.stop(stopAt + 0.04);
      }
      setTimeout(() => output.disconnect(), Math.ceil((stopAt - audioContext.currentTime + 0.1) * 1000));
    },
  };
}

function noteForCode(code) {
  const allCodes = KEY_ROWS.flat();
  const index = allCodes.includes(code) ? allCodes.indexOf(code) : hashCode(code) % 88;
  const octaveBase = Number(octaveSelect.value || 3);
  const midi = 12 * (octaveBase + 1) + index;
  const name = `${NOTE_NAMES[midi % 12]}${Math.floor(midi / 12) - 1}`;
  const frequency = 440 * Math.pow(2, (midi - 69) / 12);
  return { name, frequency };
}

function labelForCode(code, rawKey = "") {
  if (rawKey && rawKey.length === 1) {
    return rawKey === " " ? "Space" : rawKey.toUpperCase();
  }

  const labels = {
    Backquote: "`",
    Minus: "-",
    Equal: "=",
    BracketLeft: "[",
    BracketRight: "]",
    Backslash: "\\",
    Semicolon: ";",
    Quote: "'",
    Comma: ",",
    Period: ".",
    Slash: "/",
    Space: "Space",
    NumpadDecimal: "Num .",
    NumpadEnter: "Num Enter",
  };

  if (labels[code]) {
    return labels[code];
  }
  if (code.startsWith("Key")) {
    return code.slice(3);
  }
  if (code.startsWith("Digit")) {
    return code.slice(5);
  }
  if (code.startsWith("Numpad")) {
    return `Num ${code.slice(6)}`;
  }
  return code.replace(/(Left|Right)$/, " $1");
}

function classForCode(code) {
  const classes = ["key-button"];
  if (/Shift|Control|Alt|Meta|CapsLock|Tab|Enter|Backspace|Escape/.test(code)) {
    classes.push("special");
  }
  if (/Shift|Control|Alt|Meta/.test(code)) {
    classes.push("modifier");
  }
  if (code === "Space") {
    classes.push("wide");
  }
  return classes.join(" ");
}

function markButton(code, playing) {
  const button = buttonsByCode.get(code);
  if (button) {
    button.classList.toggle("playing", playing);
  }
}

function normalizeFallbackCode(key) {
  if (!key) {
    return "";
  }
  if (key.length === 1) {
    if (/[a-z]/i.test(key)) {
      return `Key${key.toUpperCase()}`;
    }
    if (/[0-9]/.test(key)) {
      return `Digit${key}`;
    }
  }
  return key.replace(/\s+/g, "");
}

function hashCode(value) {
  let hash = 0;
  for (let index = 0; index < value.length; index += 1) {
    hash = (hash * 31 + value.charCodeAt(index)) >>> 0;
  }
  return hash;
}

function drawScope() {
  if (!scopeContext || !analyser) {
    return;
  }

  const buffer = new Uint8Array(analyser.frequencyBinCount);
  const draw = () => {
    analyser.getByteTimeDomainData(buffer);
    const { width, height } = scopeCanvas;
    scopeContext.clearRect(0, 0, width, height);
    scopeContext.fillStyle = "#0b1018";
    scopeContext.fillRect(0, 0, width, height);
    scopeContext.lineWidth = 4;
    scopeContext.strokeStyle = "#64d2a7";
    scopeContext.beginPath();
    for (let index = 0; index < buffer.length; index += 1) {
      const x = (index / (buffer.length - 1)) * width;
      const y = (buffer[index] / 255) * height;
      if (index === 0) {
        scopeContext.moveTo(x, y);
      } else {
        scopeContext.lineTo(x, y);
      }
    }
    scopeContext.stroke();
    scopeFrame = requestAnimationFrame(draw);
  };
  cancelAnimationFrame(scopeFrame);
  draw();
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

init();
