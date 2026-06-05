const LANGUAGES = [
  { code: "auto", label: "Auto-detect" },
  { code: "en", label: "English" },
  { code: "hi", label: "Hindi" },
  { code: "te", label: "Telugu" },
  { code: "ta", label: "Tamil" },
  { code: "kn", label: "Kannada" },
  { code: "ml", label: "Malayalam" },
  { code: "mr", label: "Marathi" },
  { code: "gu", label: "Gujarati" },
  { code: "pa", label: "Punjabi" },
  { code: "bn", label: "Bengali" },
  { code: "ur", label: "Urdu" },
  { code: "ar", label: "Arabic" },
  { code: "fa", label: "Persian" },
  { code: "he", label: "Hebrew" },
  { code: "zh", label: "Chinese" },
  { code: "ja", label: "Japanese" },
  { code: "ko", label: "Korean" },
  { code: "es", label: "Spanish" },
  { code: "fr", label: "French" },
  { code: "de", label: "German" },
  { code: "it", label: "Italian" },
  { code: "pt", label: "Portuguese" },
  { code: "ru", label: "Russian" },
  { code: "uk", label: "Ukrainian" },
  { code: "pl", label: "Polish" },
  { code: "nl", label: "Dutch" },
  { code: "sv", label: "Swedish" },
  { code: "tr", label: "Turkish" },
  { code: "id", label: "Indonesian" },
  { code: "vi", label: "Vietnamese" },
  { code: "th", label: "Thai" },
];

let isRunning = false;

function updateEngineNote(settings = {}, providerReadiness = null) {
  const note = document.getElementById("engine-note");
  if (!note) return;
  note.textContent = "Free/offline stack active. ULT uses local models and local audio tools only.";
}

function populateLangSelect(id, includeAuto = true, defaultCode = "en") {
  const sel = document.getElementById(id);
  sel.innerHTML = "";
  LANGUAGES.forEach(({ code, label }) => {
    if (!includeAuto && code === "auto") return;
    const option = document.createElement("option");
    option.value = code;
    option.textContent = label;
    if (code === defaultCode) option.selected = true;
    sel.appendChild(option);
  });
}

function showTab(id, btn) {
  document.querySelectorAll(".tab-panel").forEach((el) => el.classList.remove("active"));
  document.querySelectorAll(".tab").forEach((el) => el.classList.remove("active"));
  document.getElementById(`tab-${id}`).classList.add("active");
  btn.classList.add("active");
}

function setStatus(text, state = "idle") {
  document.getElementById("status-text").textContent = text;
  const dot = document.getElementById("status-dot");
  dot.className = "dot" + (state === "running" ? " running" : state === "error" ? " error" : "");
}

function setBlocking(active) {
  const badge = document.getElementById("blocking-badge");
  badge.textContent = active ? "Audio Blocked" : "Audio: Normal";
  badge.className = "blocking-badge " + (active ? "active" : "inactive");
}

function syncUI() {
  const btn = document.getElementById("start-btn");
  btn.textContent = isRunning ? "Stop" : "Start";
  btn.className = `start-btn ${isRunning ? "running" : "idle"}`;
  [
    "mic-device",
    "mic-src-lang",
    "mic-lang",
    "spk-device",
    "spk-src-lang",
    "spk-lang",
    "online-policy",
  ].forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.disabled = isRunning;
  });
  if (!isRunning) setBlocking(false);
}

async function toggleSession() {
  const btn = document.getElementById("start-btn");
  btn.disabled = true;

  if (isRunning) {
    setStatus("Stopping...");
    await window.translatorApp.stop();
    isRunning = false;
    setStatus("Stopped - ready to start again");
    setBlocking(false);
  } else {
    setStatus("Starting...");
    const result = await window.translatorApp.start({
      micDevice: document.getElementById("mic-device").value,
      micSrcLang: document.getElementById("mic-src-lang").value,
      micLang: document.getElementById("mic-lang").value,
      spkDevice: document.getElementById("spk-device").value,
      spkSrcLang: document.getElementById("spk-src-lang").value,
      spkLang: document.getElementById("spk-lang").value,
      onlinePolicy: document.getElementById("online-policy").value,
    });
    isRunning = Boolean(result?.isRunning);
    if (result?.error) {
      setStatus(`Error: ${result.error}`, "error");
      addLog(result.error, "error");
    } else if (isRunning) {
      setStatus("Running - speaker active, mic standby auto-on", "running");
      setBlocking(true);
      showTab("feed", document.querySelectorAll(".tab")[0]);
    }
  }

  btn.disabled = false;
  syncUI();
}

function addLog(message, level = "info") {
  const container = document.getElementById("logs");
  const entry = document.createElement("div");
  entry.className = "log-entry";
  entry.innerHTML = `<span class="log-time">${new Date().toLocaleTimeString()}</span><span class="log-${level}">${message}</span>`;
  container.prepend(entry);
  while (container.children.length > 300) container.removeChild(container.lastChild);
}

function addTranslation(event) {
  document.getElementById("feed-empty").style.display = "none";
  const container = document.getElementById("feed-items");
  const card = document.createElement("div");
  card.className = "feed-card";
  const isMic = event.source === "MIC";
  const srcLang = isMic ? document.getElementById("mic-src-lang").value : document.getElementById("spk-src-lang").value;
  const tgtLang = isMic ? document.getElementById("mic-lang").value : document.getElementById("spk-lang").value;
  card.innerHTML = `
    <span class="feed-badge ${isMic ? "mic" : "spk"}">${isMic ? "Mic" : "Speaker"}</span>
    <div class="feed-original">${event.transcript || ""}</div>
    <div class="feed-translated">${event.translatedText || ""}</div>
    <div class="feed-meta">${event.detectedLanguage || srcLang} -> ${tgtLang} | ${event.backend || ""} | ${event.latencyMs || "?"}ms</div>
  `;
  container.prepend(card);
  while (container.children.length > 100) container.removeChild(container.lastChild);
}

async function loadDevices() {
  const devices = await window.translatorApp.getDevices();

  const micSel = document.getElementById("mic-device");
  micSel.innerHTML = "";
  (devices?.inputDevices || []).forEach((d) => {
    const option = document.createElement("option");
    option.value = d.name;
    option.textContent = d.name;
    micSel.appendChild(option);
  });
  if (!micSel.options.length) micSel.innerHTML = '<option value="">Default Microphone</option>';

  const spkSel = document.getElementById("spk-device");
  spkSel.innerHTML = "";
  (devices?.outputDevices || []).forEach((d) => {
    const option = document.createElement("option");
    option.value = d.name;
    option.textContent = d.name;
    if (/speaker|high definition|realtek|analog/i.test(d.name)) option.selected = true;
    spkSel.appendChild(option);
  });
  if (!spkSel.options.length) spkSel.innerHTML = '<option value="">Default Speaker</option>';
}

async function loadEngineSettings() {
  updateEngineNote();
}

async function saveEngineSettings() {
  updateEngineNote();
  addLog("Free/offline engine settings are fixed for this build.", "info");
}

async function initialize() {
  populateLangSelect("mic-src-lang", true, "auto");
  populateLangSelect("mic-lang", false, "hi");
  populateLangSelect("spk-src-lang", true, "auto");
  populateLangSelect("spk-lang", false, "te");

  const state = await window.translatorApp.getState();
  isRunning = Boolean(state?.isRunning);
  const hw = state?.runtime?.bootstrap?.hardware;
  if (hw) {
    document.getElementById("hw-info").textContent = `${hw.profileId} | ${hw.cpuCount} CPU | ${hw.totalMemGb} GB RAM`;
  }
  updateEngineNote();

  await Promise.all([loadDevices(), loadEngineSettings()]);
  syncUI();
  setStatus("Ready - click Start to begin");
}

window.translatorApp.onLog((p) => addLog(p.message, p.level));

window.translatorApp.onEvent((p) => {
  if (p.type === "final_translation") addTranslation(p);
  if (p.type === "latency") {
    const el = document.getElementById(p.source === "MIC" ? "mic-latency" : "spk-latency");
    if (el) el.textContent = p.latencyMs;
  }
});

window.translatorApp.onState((p) => {
  isRunning = Boolean(p?.isRunning);
  syncUI();
});

initialize().catch((e) => addLog(e.message, "error"));
