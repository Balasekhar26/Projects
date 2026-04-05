const sourceLanguageSelect = document.getElementById("source-language");
const targetLanguageSelect = document.getElementById("target-language");
const sessionKindSelect = document.getElementById("session-kind");
const onlinePolicySelect = document.getElementById("online-policy");
const routeProfileSelect = document.getElementById("route-profile");
const inputDeviceSelect = document.getElementById("input-device");
const outputDeviceSelect = document.getElementById("output-device");
const voiceProfileSelect = document.getElementById("voice-profile");
const toggleSessionButton = document.getElementById("toggle-session");
const refreshRuntimeButton = document.getElementById("refresh-runtime");
const clearLogsButton = document.getElementById("clear-logs");
const logsContainer = document.getElementById("logs");
const liveFeedContainer = document.getElementById("live-feed");
const stateText = document.getElementById("state-text");
const runtimeSummary = document.getElementById("runtime-summary");

let isRunning = false;

function addLog(message, level = "info", timestamp = new Date().toLocaleTimeString()) {
  const entry = document.createElement("div");
  entry.className = `log-entry log-${level}`;
  entry.innerHTML = `
    <span class="log-time">${timestamp}</span>
    <span class="log-message">${message}</span>
  `;
  logsContainer.prepend(entry);
}

function addTranslation(event) {
  const entry = document.createElement("article");
  entry.className = "feed-card";
  entry.innerHTML = `
    <div class="feed-meta">
      <span>Chunk ${event.chunkNumber ?? "n/a"}</span>
      <span>${event.detectedLanguage ?? "unknown"}</span>
      <span>${event.backend ?? "unknown"}</span>
    </div>
    <p class="feed-label">Transcript</p>
    <p class="feed-value">${event.transcript || "No transcript available."}</p>
    <p class="feed-label">Translated Output</p>
    <p class="feed-value feed-translated">${event.translatedText || "No translated text."}</p>
  `;
  liveFeedContainer.prepend(entry);
}

function syncUiState() {
  toggleSessionButton.textContent = isRunning ? "Stop" : "Start";
  toggleSessionButton.classList.toggle("is-stop", isRunning);
  stateText.textContent = isRunning ? "Running" : "Idle";
}

function fillSelect(select, items, currentValue, fallbackSelector) {
  select.innerHTML = "";
  const fallback = typeof fallbackSelector === "function" ? fallbackSelector(items) : items[0];
  const chosenValue =
    items.find((item) => item.value === currentValue)?.value || fallback?.value || "";

  items.forEach((item) => {
    const option = document.createElement("option");
    option.value = item.value;
    option.textContent = item.label;
    select.append(option);
  });

  select.value = chosenValue;
}

function applyRuntime(runtime) {
  if (!runtime) {
    return;
  }

  const topology = runtime.topology || { inputDevices: [], outputDevices: [], routeProfiles: [] };
  const voiceProfiles = Array.isArray(runtime.voiceProfiles) ? runtime.voiceProfiles : [];
  const bootstrap = runtime.bootstrap;

  fillSelect(
    routeProfileSelect,
    topology.routeProfiles.map((profile) => ({
      value: profile.id,
      label: `${profile.label} (${profile.status})`,
    })),
    routeProfileSelect.value
  );
  fillSelect(
    inputDeviceSelect,
    topology.inputDevices.map((device) => ({ value: device.name, label: device.name })),
    inputDeviceSelect.value
  );
  fillSelect(
    outputDeviceSelect,
    topology.outputDevices.map((device) => ({ value: device.name, label: device.name })),
    outputDeviceSelect.value
  );
  fillSelect(
    voiceProfileSelect,
    voiceProfiles.map((profile) => ({ value: profile.id, label: profile.label })),
    voiceProfileSelect.value
  );

  runtimeSummary.textContent = bootstrap
    ? `${bootstrap.hardware.profileId} profile / ${bootstrap.hardware.cpuCount} CPU threads / ${bootstrap.hardware.totalMemGb} GB RAM`
    : "Runtime summary unavailable";
}

async function initialize() {
  const state = await window.translatorApp.getState();
  isRunning = Boolean(state?.isRunning);
  syncUiState();
  applyRuntime(state?.runtime);
  addLog("Electron desktop shell ready", "status");
}

toggleSessionButton.addEventListener("click", async () => {
  if (isRunning) {
    const result = await window.translatorApp.stop();
    isRunning = Boolean(result?.isRunning);
    syncUiState();
    return;
  }

  const payload = {
    sourceLanguage: sourceLanguageSelect.value,
    targetLanguage: targetLanguageSelect.value,
    sessionKind: sessionKindSelect.value,
    onlinePolicy: onlinePolicySelect.value,
    routeProfileId: routeProfileSelect.value,
    inputDeviceId: inputDeviceSelect.value,
    outputDeviceId: outputDeviceSelect.value,
    voiceProfileId: voiceProfileSelect.value,
  };

  const result = await window.translatorApp.start(payload);
  isRunning = Boolean(result?.isRunning);
  syncUiState();
});

refreshRuntimeButton.addEventListener("click", async () => {
  const runtime = await window.translatorApp.refreshRuntime();
  applyRuntime(runtime);
  addLog("Runtime inventory refreshed", "status");
});

clearLogsButton.addEventListener("click", () => {
  logsContainer.innerHTML = "";
  liveFeedContainer.innerHTML = "";
  addLog("Logs cleared", "status");
});

window.translatorApp.onLog((payload) => {
  addLog(payload.message, payload.level, payload.timestamp);
});

window.translatorApp.onEvent((payload) => {
  if (payload.type === "final_translation") {
    addTranslation(payload);
  }
});

window.translatorApp.onState((payload) => {
  isRunning = Boolean(payload?.isRunning);
  syncUiState();
  applyRuntime(payload?.runtime);
});

initialize().catch((error) => {
  addLog(error instanceof Error ? error.message : "Unable to initialize desktop shell", "error");
});
