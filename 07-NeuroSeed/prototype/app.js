const stateKey = "neuroseed-project-7-prototype";

// Detect if running in Electron (desktop) or through the local NeuroSeed server.
const isElectron = typeof window !== "undefined" && typeof window.neuroSeedApi !== "undefined";
const apiBaseUrl = window.location.protocol === "http:" ? "" : "http://127.0.0.1:8765";

let backendReady = false;
let syncTimer = null;

const state = {
  seeds: [],
  logs: [],
  sessions: [],
  cuedIds: new Set(),
  activeSessionId: null,
  stageIndex: 0,
  sleepTimer: null,
  recallResults: [],
  consentLogs: []
};

const memoryBridge = {
  baseUrl: localStorage.getItem("neuroseed-memory-url") || "http://127.0.0.1:8077",
  online: false,
  hydrating: false,
  syncTimer: null,
  lastSyncedAt: null
};

const stageNames = ["N1", "N2", "N3", "REM"];
const consentModel = {
  version: "pilot-consent-v1",
  awakeConsentRequired: true,
  userSelectedContentOnly: true,
  unconsciousOnlyInjectionBlocked: true,
  hiddenPersuasionBlocked: true,
  removableLocalStorage: true,
  localMemoryRemovable: true,
  durableMemory: "universal-ai Chroma + SQLite when the local memory bridge is available",
  exportRequiresUserAction: true,
  safetyNote: "NeuroSeed stores only user-entered study text, consent choices, cue events, and recall checks in local memory."
};
const sampleText = `Hippocampus helps bind new episodic memories before they are gradually integrated with cortical networks.
Targeted memory reactivation links learned content with a sound or odor cue, then replays the cue during sleep to bias consolidation.
NeuroSeed must require awake consent before sleep cueing because memory affects autonomy and identity.
Sleep reinforcement can strengthen selected memories, but it cannot upload brand-new knowledge into an unconscious brain.`;

const els = {};

document.addEventListener("DOMContentLoaded", async () => {
  bindElements();
  await restoreState();
  bindEvents();
  renderAll();
  drawMemoryMap();
  window.setInterval(drawMemoryMap, 80);
  renderIcons();
  updateMemoryStatus();
  hydrateFromMemory();
});

function bindElements() {
  [
    "sourceText",
    "seedSize",
    "cueType",
    "generateBtn",
    "sampleBtn",
    "seedList",
    "seedCount",
    "approvedCount",
    "eligibleCount",
    "memoryCanvas",
    "startSleepBtn",
    "stopSleepBtn",
    "volumeSlider",
    "hapticSlider",
    "maxCues",
    "stageIndicator",
    "sessionLog",
    "cueCounter",
    "sleepStatus",
    "loadStatus",
    "recallList",
    "recallScore",
    "retentionFill",
    "retentionLabel",
    "totalSeedsStat",
    "approvedStat",
    "cuedStat",
    "saveBtn",
    "resetBtn",
    "viewTitle",
    "consentStatus",
    "memoryStatus",
    "sessionCountStat",
    "cuedRecallStat",
    "uncuedRecallStat",
    "memoryStatus",
    "exportJsonBtn",
    "exportCsvBtn",
    "sessionList"
  ].forEach((id) => {
    els[id] = document.getElementById(id);
  });
}

function bindEvents() {
  document.querySelectorAll(".tab-button").forEach((button) => {
    button.addEventListener("click", () => setView(button.dataset.view));
  });

  els.sampleBtn.addEventListener("click", () => {
    els.sourceText.value = sampleText;
  });

  els.generateBtn.addEventListener("click", generateSeeds);
  els.startSleepBtn.addEventListener("click", startSleepSession);
  els.stopSleepBtn.addEventListener("click", stopSleepSession);
  els.saveBtn.addEventListener("click", () => saveState());
  els.resetBtn.addEventListener("click", resetState);
  els.exportJsonBtn.addEventListener("click", () => exportJson());
  els.exportCsvBtn.addEventListener("click", () => exportCsv());
  els.volumeSlider.addEventListener("input", updateLoadStatus);
  els.hapticSlider.addEventListener("input", updateLoadStatus);
}

async function hydrateFromMemory() {
  memoryBridge.hydrating = true;
  let shouldSyncLocal = false;
  updateMemoryStatus("Checking");
  try {
    const response = await memoryFetch("/neuroseed/state");
    if (!response.ok) throw new Error(`Memory backend returned ${response.status}`);
    const payload = await response.json();
    memoryBridge.online = true;
    const remoteState = payload.state || {};
    if (hasStoredState(remoteState)) {
      applyStoredState(remoteState);
      persistLocalState();
      toastLog("Memory", "NeuroSeed local Chroma/SQLite memory loaded.");
      renderAll();
    } else if (hasStoredState(currentStatePayload())) {
      shouldSyncLocal = true;
    }
    updateMemoryStatus();
  } catch {
    memoryBridge.online = false;
    updateMemoryStatus("Browser");
  } finally {
    memoryBridge.hydrating = false;
    if (shouldSyncLocal) scheduleMemorySync(10);
  }
}

function scheduleMemorySync(delay = 250) {
  if (memoryBridge.hydrating) return;
  window.clearTimeout(memoryBridge.syncTimer);
  memoryBridge.syncTimer = window.setTimeout(syncMemoryState, delay);
}

async function syncMemoryState() {
  try {
    const response = await memoryFetch("/neuroseed/state", {
      method: "POST",
      body: JSON.stringify(currentStatePayload())
    });
    if (!response.ok) throw new Error(`Memory backend returned ${response.status}`);
    const payload = await response.json();
    memoryBridge.online = true;
    memoryBridge.lastSyncedAt = new Date().toISOString();
    if (payload.state && hasStoredState(payload.state)) {
      applyStoredState(payload.state);
      persistLocalState();
      renderAll();
    }
    updateMemoryStatus();
  } catch {
    memoryBridge.online = false;
    updateMemoryStatus("Browser");
  }
}

async function resetMemoryState() {
  try {
    const response = await memoryFetch("/neuroseed/state", { method: "DELETE" });
    memoryBridge.online = response.ok;
  } catch {
    memoryBridge.online = false;
  }
  updateMemoryStatus();
}

function memoryFetch(path, options = {}) {
  return fetch(`${memoryBridge.baseUrl}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {})
    }
  });
}

function currentStatePayload() {
  return {
    dataModel: consentModel,
    seeds: state.seeds,
    logs: state.logs,
    sessions: state.sessions,
    cuedIds: [...state.cuedIds],
    activeSessionId: state.activeSessionId,
    recallResults: state.recallResults
  };
}

function hasStoredState(payload) {
  return Boolean(
    (payload.seeds && payload.seeds.length) ||
      (payload.sessions && payload.sessions.length) ||
      (payload.recallResults && payload.recallResults.length)
  );
}

function applyStoredState(payload) {
  state.seeds = (payload.seeds || []).map((seed) => ({
    ...seed,
    consent: seed.consent || {
      status: seed.approved ? "awake-approved" : "pending",
      model: consentModel.version,
      approvedAt: null
    }
  }));
  state.logs = payload.logs || [];
  state.sessions = payload.sessions || [];
  state.cuedIds = new Set(payload.cuedIds || []);
  state.activeSessionId = payload.activeSessionId || null;
  state.recallResults = normalizeRecallResults(payload.recallResults);
  finalizeActiveSession();
}

function persistLocalState() {
  localStorage.setItem(stateKey, JSON.stringify(currentStatePayload()));
}

function updateMemoryStatus(label) {
  if (!els.memoryStatus) return;
  if (label) {
    els.memoryStatus.textContent = label;
    return;
  }
  els.memoryStatus.textContent = memoryBridge.online ? "Shared" : "Browser";
}

function setView(view) {
  const titles = {
    seed: "Seed Builder",
    sleep: "Sleep Reinforcement",
    recall: "Recall Verification",
    ethics: "Guard Layer"
  };

  document.querySelectorAll(".tab-button").forEach((button) => {
    button.classList.toggle("active", button.dataset.view === view);
  });
  document.querySelectorAll("[data-view-panel]").forEach((panel) => {
    panel.classList.toggle("active", panel.dataset.viewPanel === view);
  });
  els.viewTitle.textContent = titles[view];
  drawMemoryMap();
}

function generateSeeds() {
  const source = els.sourceText.value.trim();
  if (!source) {
    toastLog("Input", "No knowledge text found. Add notes before generating seeds.");
    return;
  }

  const chunkSize = { short: 110, balanced: 175, dense: 260 }[els.seedSize.value];
  const pieces = splitIntoChunks(source, chunkSize);
  state.seeds = pieces.map((text, index) => {
    const keywords = extractKeywords(text);
    return {
      id: randomId(),
      title: keywords.slice(0, 3).join(" / ") || `Seed ${index + 1}`,
      text,
      keywords,
      cue: makeCue(index, els.cueType.value),
      approved: false,
      consent: {
        status: "pending",
        model: consentModel.version,
        approvedAt: null
      },
      createdAt: new Date().toISOString()
    };
  });
  state.logs = [];
  state.sessions = [];
  state.cuedIds = new Set();
  state.activeSessionId = null;
  state.recallResults = [];
  toastLog("Seed", `${state.seeds.length} memory seeds generated.`);
  saveState(false);
  renderAll();
}

function randomId() {
  if (window.crypto && typeof window.crypto.randomUUID === "function") {
    return window.crypto.randomUUID();
  }
  return `seed-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function splitIntoChunks(text, targetLength) {
  const sentences = text
    .replace(/\s+/g, " ")
    .split(/(?<=[.!?])\s+/)
    .map((item) => item.trim())
    .filter(Boolean);

  const chunks = [];
  let current = "";

  sentences.forEach((sentence) => {
    if ((current + " " + sentence).trim().length > targetLength && current) {
      chunks.push(current.trim());
      current = sentence;
    } else {
      current = `${current} ${sentence}`.trim();
    }
  });

  if (current) {
    chunks.push(current.trim());
  }

  return chunks.slice(0, 12);
}

function extractKeywords(text) {
  const stop = new Set(["this", "that", "with", "from", "into", "while", "where", "when", "then", "than", "they", "their", "about", "because", "before", "after", "without", "memory", "brain"]);
  return text
    .toLowerCase()
    .replace(/[^a-z0-9\s-]/g, "")
    .split(/\s+/)
    .filter((word) => word.length > 4 && !stop.has(word))
    .reduce((unique, word) => {
      if (!unique.includes(word)) unique.push(word);
      return unique;
    }, [])
    .slice(0, 7);
}

function makeCue(index, type) {
  const base = 220 + index * 41;
  const tones = [base, base * 1.25, base * 1.5].map(Math.round);
  return {
    type,
    label: `${type.toUpperCase()}-${String(index + 1).padStart(2, "0")}`,
    tones,
    pattern: [80, 40, 120]
  };
}

function renderAll() {
  renderSeeds();
  renderSleep();
  renderRecall();
  updateStats();
  updateLoadStatus();
  renderIcons();
}

function renderIcons() {
  const labels = {
    sprout: "SE",
    moon: "SL",
    brain: "RC",
    "shield-check": "GD",
    save: "SV",
    "rotate-ccw": "RS",
    braces: "JS",
    table: "CSV",
    "wand-sparkles": "GN",
    sparkles: "SM",
    play: "PL",
    square: "ST",
    "lock-keyhole": "LK",
    "check-circle": "OK",
    ban: "NO",
    "volume-2": "CU",
    check: "AP"
  };

  document.querySelectorAll("[data-lucide]").forEach((icon) => {
    const name = icon.getAttribute("data-lucide") || "";
    icon.textContent = labels[name] || "..";
    icon.classList.add("local-icon");
    icon.setAttribute("aria-hidden", "true");
  });
}

function renderSeeds() {
  if (!state.seeds.length) {
    els.seedList.innerHTML = `<div class="empty-state">No seeds yet.</div>`;
    return;
  }

  els.seedList.innerHTML = state.seeds
    .map((seed) => `
      <article class="seed-card">
        <header>
          <div>
            <h4>${escapeHtml(seed.title)}</h4>
            <p>${escapeHtml(seed.text)}</p>
          </div>
          <span class="cue-badge">${escapeHtml(seed.cue.label)}</span>
        </header>
        <div class="seed-actions">
          <label class="check-line">
            <input type="checkbox" data-approve="${seed.id}" ${seed.approved ? "checked" : ""}>
            <span>Awake approved</span>
          </label>
          <button class="tool-button" type="button" data-play="${seed.id}">
            <i data-lucide="volume-2"></i>
            <span>Cue</span>
          </button>
        </div>
      </article>
    `)
    .join("");

  els.seedList.querySelectorAll("[data-approve]").forEach((input) => {
    input.addEventListener("change", () => {
      const seed = findSeed(input.dataset.approve);
      seed.approved = input.checked;
      seed.consent = {
        status: seed.approved ? "awake-approved" : "removed",
        model: consentModel.version,
        approvedAt: seed.approved ? new Date().toISOString() : null
      };
      toastLog("Consent", `${seed.title} ${seed.approved ? "approved" : "removed"}.`);
      saveState(false);
      renderAll();
    });
  });

  els.seedList.querySelectorAll("[data-play]").forEach((button) => {
    button.addEventListener("click", () => {
      const seed = findSeed(button.dataset.play);
      playCue(seed);
    });
  });
}

function renderSleep() {
  const approved = state.seeds.filter((seed) => seed.approved);
  const activeSession = getActiveSession();
  els.sessionLog.innerHTML = state.logs.length
    ? state.logs.map((log) => `
      <div class="log-entry">
        <time>${escapeHtml(log.time)}</time>
        <span>${escapeHtml(log.message)}</span>
      </div>
    `).join("")
    : `<div class="empty-state">No sleep session events.</div>`;

  els.eligibleCount.textContent = `${approved.length} eligible`;
  els.cueCounter.textContent = `${state.cuedIds.size} cues`;
  els.sleepStatus.textContent = activeSession ? "Running" : "Idle";
  if (els.memoryStatus) {
    els.memoryStatus.textContent = backendReady ? "universal-ai Chroma + SQLite" : "Browser cache";
  }
}

function renderRecall() {
  const session = latestSession();
  const approvedIds = new Set(session?.approvedSeedIds || []);
  const targets = session
    ? state.seeds.filter((seed) => approvedIds.has(seed.id))
    : state.seeds;

  if (!targets.length) {
    els.recallList.innerHTML = `<div class="empty-state">No recall targets yet.</div>`;
    renderSessions();
    return;
  }

  els.recallList.innerHTML = targets.map((seed) => {
    const condition = recallCondition(seed, session);
    const result = latestRecallResult(seed.id, session?.id || "manual");
    const value = result?.answer || "";
    const status = result ? `${Math.round(result.score * 100)}%` : "Pending";
    return `
      <article class="recall-card">
        <header>
          <div>
            <h4>${escapeHtml(seed.title)}</h4>
            <p>${escapeHtml(seed.text)}</p>
          </div>
          <span class="metric-pill">${condition} | ${status}</span>
        </header>
        <div class="answer-row">
          <input type="text" value="${escapeHtml(value)}" data-answer="${seed.id}" placeholder="Type remembered keywords">
          <button class="tool-button" type="button" data-check="${seed.id}">
            <i data-lucide="check"></i>
            <span>Check</span>
          </button>
        </div>
      </article>
    `;
  }).join("");

  els.recallList.querySelectorAll("[data-check]").forEach((button) => {
    button.addEventListener("click", () => {
      const seed = findSeed(button.dataset.check);
      const input = els.recallList.querySelector(`[data-answer="${seed.id}"]`);
      const score = scoreAnswer(seed, input.value);
      const currentSession = latestSession();
      const condition = recallCondition(seed, currentSession);
      state.recallResults.unshift({
        id: randomId(),
        sessionId: currentSession?.id || "manual",
        sessionStartedAt: currentSession?.startedAt || null,
        seedId: seed.id,
        seedTitle: seed.title,
        condition,
        answer: input.value,
        score,
        checkedAt: new Date().toISOString(),
        consentModel: consentModel.version
      });
      toastLog("Recall", `${seed.title}: ${condition} recall ${Math.round(score * 100)}% keyword match.`);
      saveState(false);
      renderAll();
    });
  });
  renderSessions();
}

function updateStats() {
  const total = state.seeds.length;
  const approved = state.seeds.filter((seed) => seed.approved).length;
  const cued = state.cuedIds.size;
  const scores = state.recallResults.map((result) => result.score);
  const cuedScores = state.recallResults.filter((result) => result.condition === "cued").map((result) => result.score);
  const uncuedScores = state.recallResults.filter((result) => result.condition === "uncued").map((result) => result.score);
  const average = scores.length ? scores.reduce((sum, score) => sum + score, 0) / scores.length : 0;
  const cuedAverage = averageScore(cuedScores);
  const uncuedAverage = averageScore(uncuedScores);

  els.seedCount.textContent = `${total} seeds`;
  els.approvedCount.textContent = `${approved} approved`;
  els.totalSeedsStat.textContent = total;
  els.approvedStat.textContent = approved;
  els.cuedStat.textContent = cued;
  els.sessionCountStat.textContent = state.sessions.length;
  els.cuedRecallStat.textContent = cuedScores.length ? `${Math.round(cuedAverage * 100)}%` : "-";
  els.uncuedRecallStat.textContent = uncuedScores.length ? `${Math.round(uncuedAverage * 100)}%` : "-";
  els.recallScore.textContent = `${Math.round(average * 100)}%`;
  els.retentionFill.style.width = `${Math.round(average * 100)}%`;
  els.retentionLabel.textContent = scores.length ? "Measured" : "No run";
  els.consentStatus.textContent = `${approved}/${total} awake`;
}

function updateLoadStatus() {
  const volume = Number(els.volumeSlider.value);
  const haptic = Number(els.hapticSlider.value);
  const load = volume + haptic;
  els.loadStatus.textContent = load > 38 ? "High" : load > 24 ? "Medium" : "Low";
}

function startSleepSession() {
  const approved = state.seeds.filter((seed) => seed.approved);
  if (!approved.length) {
    toastLog("Guard", "Sleep mode blocked: no awake-approved seeds.");
    renderSleep();
    return;
  }

  stopSleepSession(false);
  els.sleepStatus.textContent = "Running";
  const session = createSession(approved);
  toastLog("Sleep", "Session started.");
  let cueIndex = 0;
  let tick = 0;
  const maxCues = Number(els.maxCues.value);

  state.sleepTimer = window.setInterval(() => {
    state.stageIndex = tick % stageNames.length;
    els.stageIndicator.style.transform = `translateX(${state.stageIndex * 100}%)`;

    const stage = stageNames[state.stageIndex];
    const cueAllowed = stage === "N2" || stage === "N3";

    if (cueAllowed && cueIndex < Math.min(maxCues, approved.length)) {
      const seed = approved[cueIndex % approved.length];
      playCue(seed, true);
      state.cuedIds.add(seed.id);
      session.cueEvents.push({
        seedId: seed.id,
        seedTitle: seed.title,
        cueLabel: seed.cue.label,
        stage,
        cuedAt: new Date().toISOString()
      });
      toastLog(stage, `Reinforced ${seed.title}.`);
      cueIndex += 1;
      saveState(false);
    } else {
      toastLog(stage, cueAllowed ? "Cue window open." : "Cue held.");
    }

    tick += 1;
    renderAll();

    if (cueIndex >= Math.min(maxCues, approved.length) && tick > 5) {
      stopSleepSession();
    }
  }, 1400);
}

function stopSleepSession(logStop = true) {
  if (state.sleepTimer) {
    window.clearInterval(state.sleepTimer);
    state.sleepTimer = null;
  }
  finalizeActiveSession();
  els.sleepStatus.textContent = "Idle";
  if (logStop) {
    toastLog("Sleep", "Session stopped.");
    renderSleep();
  }
}

function playCue(seed, quiet = false) {
  const volume = quiet ? Math.min(Number(els.volumeSlider.value), 16) / 100 : 0.18;
  const AudioContext = window.AudioContext || window.webkitAudioContext;

  if (AudioContext) {
    const context = new AudioContext();
    let time = context.currentTime;
    seed.cue.tones.forEach((freq, index) => {
      const oscillator = context.createOscillator();
      const gain = context.createGain();
      oscillator.type = index % 2 ? "triangle" : "sine";
      oscillator.frequency.value = freq;
      gain.gain.setValueAtTime(0.0001, time);
      gain.gain.exponentialRampToValueAtTime(volume, time + 0.02);
      gain.gain.exponentialRampToValueAtTime(0.0001, time + 0.18);
      oscillator.connect(gain).connect(context.destination);
      oscillator.start(time);
      oscillator.stop(time + 0.2);
      time += 0.18;
    });
  }

  if ((seed.cue.type === "haptic" || seed.cue.type === "both") && navigator.vibrate) {
    navigator.vibrate(seed.cue.pattern.map((item) => Math.min(item, Number(els.hapticSlider.value) * 10)));
  }
}

function scoreAnswer(seed, answer) {
  const answerWords = new Set(
    answer.toLowerCase().replace(/[^a-z0-9\s-]/g, "").split(/\s+/).filter(Boolean)
  );
  if (!seed.keywords.length) return answer.trim() ? 0.5 : 0;
  const hits = seed.keywords.filter((word) => answerWords.has(word)).length;
  return Math.min(1, hits / Math.min(4, seed.keywords.length));
}

function toastLog(label, message) {
  state.logs.unshift({
    time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }),
    message: `${label}: ${message}`
  });
  state.logs = state.logs.slice(0, 28);
}

function findSeed(id) {
  return state.seeds.find((seed) => seed.id === id);
}

function saveState(showLog = true) {
  const payload = {
    dataModel: consentModel,
    seeds: state.seeds,
    logs: state.logs,
    sessions: state.sessions,
    cuedIds: [...state.cuedIds],
    activeSessionId: state.activeSessionId,
    recallResults: state.recallResults,
    consentLogs: state.consentLogs
  };
  
  // Always save to localStorage for backward compatibility
  localStorage.setItem(stateKey, JSON.stringify(payload));
  
  scheduleBackendSync(payload);
  
  if (showLog) {
    toastLog("Storage", "State saved.");
    renderAll();
  }
}

async function restoreState() {
  const raw = localStorage.getItem(stateKey);
  const remote = await loadBackendState();
  if (remote) {
    if (!hasStoredNeuroSeedData(remote) && raw) {
      try {
        applyStatePayload(JSON.parse(raw));
        toastLog("Memory", "Migrated browser cache into universal-ai memory.");
        saveState(false);
        return;
      } catch {
        localStorage.removeItem(stateKey);
      }
    }
    applyStatePayload(remote);
    toastLog("Memory", "Loaded from universal-ai local memory.");
    return;
  }

  if (!raw) return;
  try {
    applyStatePayload(JSON.parse(raw));
  } catch {
    localStorage.removeItem(stateKey);
  }
}

function applyStatePayload(payload) {
  // Handle both IPC format (from SQLite) and local format (from localStorage)
  state.seeds = (payload.seeds || []).map((seed) => {
    // Convert from SQLite row format if needed
    const normalized = {
      ...seed,
      keywords: typeof seed.keywords === 'string' ? JSON.parse(seed.keywords) : (seed.keywords || []),
      cue: typeof seed.cue === 'string' ? JSON.parse(seed.cue) : (seed.cue || {})
    };
    
    return {
      ...normalized,
      consent: normalized.consent || {
        status: normalized.approved || normalized.consentStatus === 'awake-approved' ? "awake-approved" : "pending",
        model: consentModel.version,
        approvedAt: normalized.approved_at || normalized.approvedAt || null
      }
    };
  });
  
  state.logs = payload.logs || [];
  
  state.sessions = (payload.sessions || []).map(session => {
    // Convert from SQLite row format if needed
    if (typeof session.approved_seed_ids === 'string') {
      return {
        ...session,
        approvedSeedIds: JSON.parse(session.approved_seed_ids),
        cueEvents: JSON.parse(session.cue_events),
        uncuedSeedIds: JSON.parse(session.uncued_seed_ids),
        settings: JSON.parse(session.settings),
        safetyBoundary: JSON.parse(session.safety_boundary)
      };
    }
    return session;
  });
  
  state.cuedIds = new Set(payload.cuedIds || []);
  state.activeSessionId = payload.activeSessionId || null;
  state.recallResults = normalizeRecallResults(payload.recallResults);
  state.consentLogs = payload.consentLogs || [];
  finalizeActiveSession();
}

function hasStoredNeuroSeedData(payload) {
  return Boolean(
    (payload.seeds && payload.seeds.length)
      || (payload.sessions && payload.sessions.length)
      || (payload.recallResults && payload.recallResults.length)
      || (payload.consentLogs && payload.consentLogs.length)
  );
}

function resetState() {
  stopSleepSession(false);
  state.seeds = [];
  state.logs = [];
  state.sessions = [];
  state.cuedIds = new Set();
  state.activeSessionId = null;
  state.recallResults = [];
  state.consentLogs = [];
  localStorage.removeItem(stateKey);
  syncNow({
    dataModel: { ...consentModel, resetRequested: true },
    seeds: [],
    logs: [],
    sessions: [],
    cuedIds: [],
    activeSessionId: null,
    recallResults: [],
    consentLogs: []
  });
  renderAll();
}

function createSession(approvedSeeds) {
  const maxCues = Number(els.maxCues.value);
  const session = {
    id: randomId(),
    startedAt: new Date().toISOString(),
    endedAt: null,
    status: "running",
    approvedSeedIds: approvedSeeds.map((seed) => seed.id),
    cueEvents: [],
    uncuedSeedIds: [],
    settings: {
      maxCues,
      volume: Number(els.volumeSlider.value),
      haptic: Number(els.hapticSlider.value),
      allowedStages: ["N2", "N3"]
    },
    safetyBoundary: { ...consentModel }
  };
  state.sessions.unshift(session);
  state.activeSessionId = session.id;
  return session;
}

function finalizeActiveSession() {
  const session = getActiveSession();
  if (!session) return;
  const cued = new Set(session.cueEvents.map((event) => event.seedId));
  session.uncuedSeedIds = session.approvedSeedIds.filter((id) => !cued.has(id));
  session.endedAt = session.endedAt || new Date().toISOString();
  session.status = "completed";
  state.activeSessionId = null;
}

function getActiveSession() {
  return state.sessions.find((session) => session.id === state.activeSessionId && session.status === "running") || null;
}

function latestSession() {
  return state.sessions[0] || null;
}

function recallCondition(seed, session) {
  if (!session) return state.cuedIds.has(seed.id) ? "cued" : "uncued";
  return session.cueEvents.some((event) => event.seedId === seed.id) ? "cued" : "uncued";
}

function latestRecallResult(seedId, sessionId) {
  return state.recallResults.find((result) => result.seedId === seedId && result.sessionId === sessionId);
}

function averageScore(scores) {
  return scores.length ? scores.reduce((sum, score) => sum + score, 0) / scores.length : 0;
}

function renderSessions() {
  if (!els.sessionList) return;
  if (!state.sessions.length) {
    els.sessionList.innerHTML = `<div class="empty-state compact">No study sessions yet.</div>`;
    return;
  }

  els.sessionList.innerHTML = state.sessions.slice(0, 8).map((session) => {
    const cued = new Set(session.cueEvents.map((event) => event.seedId));
    const results = state.recallResults.filter((result) => result.sessionId === session.id);
    const cuedScores = results.filter((result) => result.condition === "cued").map((result) => result.score);
    const uncuedScores = results.filter((result) => result.condition === "uncued").map((result) => result.score);
    return `
      <article class="session-card">
        <header>
          <strong>${escapeHtml(formatDateTime(session.startedAt))}</strong>
          <span>${escapeHtml(session.status)}</span>
        </header>
        <div class="session-metrics">
          <span>${session.approvedSeedIds.length} approved</span>
          <span>${cued.size} cued</span>
          <span>${session.uncuedSeedIds.length} uncued</span>
          <span>${results.length} recall checks</span>
        </div>
        <p>Cued avg: ${cuedScores.length ? `${Math.round(averageScore(cuedScores) * 100)}%` : "-"} | Uncued avg: ${uncuedScores.length ? `${Math.round(averageScore(uncuedScores) * 100)}%` : "-"}</p>
      </article>
    `;
  }).join("");
}

async function exportJson() {
  await syncNow();
  const payload = analysisPayload();
  downloadFile(`neuroseed-analysis-${dateStamp()}.json`, JSON.stringify(payload, null, 2), "application/json");
  toastLog("Export", "Analysis JSON exported by user action.");
  saveState(false);
  renderAll();
}

async function exportCsv() {
  await syncNow();
  const rows = [
    ["session_id", "session_started_at", "seed_id", "seed_title", "condition", "score", "checked_at", "answer"]
  ];
  state.recallResults.forEach((result) => {
    rows.push([
      result.sessionId,
      result.sessionStartedAt || "",
      result.seedId,
      result.seedTitle,
      result.condition,
      String(result.score),
      result.checkedAt,
      result.answer
    ]);
  });
  const csv = rows.map((row) => row.map(csvCell).join(",")).join("\n");
  downloadFile(`neuroseed-recall-${dateStamp()}.csv`, csv, "text/csv");
  toastLog("Export", "Recall CSV exported by user action.");
  saveState(false);
  renderAll();
}

function analysisPayload() {
  return {
    exportedAt: new Date().toISOString(),
    dataModel: consentModel,
    memory: {
      backend: memoryBridge.online ? "neuroseed_sqlite_chroma" : "browser_fallback",
      endpoint: memoryBridge.baseUrl,
      lastSyncedAt: memoryBridge.lastSyncedAt
    },
    seeds: state.seeds,
    sessions: state.sessions,
    recallResults: state.recallResults,
    consentLogs: state.consentLogs,
    summary: {
      seedCount: state.seeds.length,
      approvedCount: state.seeds.filter((seed) => seed.approved).length,
      sessionCount: state.sessions.length,
      cuedRecallAverage: averageScore(state.recallResults.filter((result) => result.condition === "cued").map((result) => result.score)),
      uncuedRecallAverage: averageScore(state.recallResults.filter((result) => result.condition === "uncued").map((result) => result.score))
    }
  };
}

async function loadBackendState() {
  try {
    const result = isElectron
      ? await window.neuroSeedApi.getState()
      : await fetchJson("/api/neuroseed/state");
    if (!result.ok) {
      backendReady = false;
      return null;
    }
    backendReady = true;
    return result;
  } catch (error) {
    console.error("Failed to load backend state:", error);
    backendReady = false;
    return null;
  }
}

function scheduleBackendSync(payload) {
  if (syncTimer) {
    window.clearTimeout(syncTimer);
  }
  syncTimer = window.setTimeout(() => {
    syncNow(payload);
  }, 120);
}

async function syncNow(payload = null) {
  const body = payload || {
    dataModel: consentModel,
    seeds: state.seeds,
    logs: state.logs,
    sessions: state.sessions,
    cuedIds: [...state.cuedIds],
    activeSessionId: state.activeSessionId,
    recallResults: state.recallResults,
    consentLogs: state.consentLogs
  };

  try {
    const result = isElectron
      ? await window.neuroSeedApi.putState(body)
      : await fetchJson("/api/neuroseed/state", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body)
        });
    if (!result.ok) throw new Error(result.error || "Unknown error");
    
    state.consentLogs = result.consentLogs || state.consentLogs;
    backendReady = true;
    renderSleep();
    return true;
  } catch (error) {
    console.error("Failed to sync state:", error);
    backendReady = false;
    renderSleep();
    return false;
  }
}

async function fetchJson(path, options = {}) {
  const response = await fetch(`${apiBaseUrl}${path}`, {
    cache: "no-store",
    ...options
  });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const payload = await response.json();
      detail = payload.error || detail;
    } catch {
      // Keep the HTTP status text when the response is not JSON.
    }
    throw new Error(detail);
  }
  return response.json();
}

function normalizeRecallResults(value) {
  if (Array.isArray(value)) return value;
  if (!value || typeof value !== "object") return [];
  return Object.entries(value).map(([seedId, result]) => ({
    id: randomId(),
    sessionId: "legacy",
    sessionStartedAt: null,
    seedId,
    seedTitle: findSeed(seedId)?.title || seedId,
    condition: state.cuedIds.has(seedId) ? "cued" : "uncued",
    answer: result.answer || "",
    score: Number(result.score) || 0,
    checkedAt: new Date().toISOString(),
    consentModel: consentModel.version
  }));
}

function downloadFile(filename, content, type) {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function csvCell(value) {
  return `"${String(value ?? "").replace(/"/g, '""')}"`;
}

function dateStamp() {
  return new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-");
}

function formatDateTime(value) {
  if (!value) return "Unknown";
  return new Date(value).toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
}

function drawMemoryMap() {
  const canvas = els.memoryCanvas;
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  const width = canvas.width;
  const height = canvas.height;
  const time = performance.now() / 1000;
  ctx.clearRect(0, 0, width, height);

  const gradient = ctx.createLinearGradient(0, 0, width, height);
  gradient.addColorStop(0, "#ecf8f0");
  gradient.addColorStop(0.5, "#eaf2ff");
  gradient.addColorStop(1, "#fff4df");
  ctx.fillStyle = gradient;
  ctx.fillRect(0, 0, width, height);

  const center = { x: width * 0.5, y: height * 0.52 };
  const nodes = state.seeds.length ? state.seeds : Array.from({ length: 7 }, (_, index) => ({ id: index, approved: index < 2 }));

  ctx.lineWidth = 2;
  nodes.forEach((seed, index) => {
    const angle = (Math.PI * 2 * index) / nodes.length + time * 0.08;
    const radius = 105 + (index % 3) * 38;
    const x = center.x + Math.cos(angle) * radius;
    const y = center.y + Math.sin(angle) * radius * 0.68;
    const approved = Boolean(seed.approved);
    const cued = state.cuedIds.has(seed.id);

    ctx.strokeStyle = approved ? "rgba(27, 138, 104, 0.58)" : "rgba(95, 107, 102, 0.25)";
    ctx.beginPath();
    ctx.moveTo(center.x, center.y);
    ctx.lineTo(x, y);
    ctx.stroke();

    ctx.beginPath();
    ctx.fillStyle = cued ? "#b87817" : approved ? "#1b8a68" : "#8fa09a";
    ctx.arc(x, y, cued ? 13 : 10, 0, Math.PI * 2);
    ctx.fill();

    if (cued) {
      ctx.strokeStyle = "rgba(184, 120, 23, 0.35)";
      ctx.lineWidth = 4;
      ctx.beginPath();
      ctx.arc(x, y, 22 + Math.sin(time * 4) * 4, 0, Math.PI * 2);
      ctx.stroke();
    }
  });

  ctx.fillStyle = "#18201c";
  ctx.beginPath();
  ctx.ellipse(center.x, center.y, 72, 48, 0, 0, Math.PI * 2);
  ctx.fill();

  ctx.strokeStyle = "#d2f5df";
  ctx.lineWidth = 5;
  for (let i = 0; i < 4; i += 1) {
    ctx.beginPath();
    ctx.arc(center.x - 24 + i * 16, center.y, 24 + Math.sin(time + i) * 3, Math.PI * 0.1, Math.PI * 1.35);
    ctx.stroke();
  }

  ctx.fillStyle = "#d2f5df";
  ctx.font = "700 18px Inter, sans-serif";
  ctx.textAlign = "center";
  ctx.fillText("NeuroSeed", center.x, center.y + 76);
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
