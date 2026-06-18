const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("translatorApp", {
  getState: () => ipcRenderer.invoke("translator:get-state"),
  refreshRuntime: () => ipcRenderer.invoke("translator:refresh-runtime"),
  getSettings: () => ipcRenderer.invoke("translator:get-settings"),
  saveSettings: (payload) => ipcRenderer.invoke("translator:save-settings", payload),
  start: (payload) => ipcRenderer.invoke("translator:start", payload),
  stop: () => ipcRenderer.invoke("translator:stop"),
  getDevices: () => ipcRenderer.invoke("translator:get-devices"),
  transcribeVideo: (payload) => ipcRenderer.invoke("translator:transcribe-video", payload),
  onLog: (callback) => {
    const listener = (_event, payload) => callback(payload);
    ipcRenderer.on("translator:log", listener);
    return () => ipcRenderer.removeListener("translator:log", listener);
  },
  onEvent: (callback) => {
    const listener = (_event, payload) => callback(payload);
    ipcRenderer.on("translator:event", listener);
    return () => ipcRenderer.removeListener("translator:event", listener);
  },
  onState: (callback) => {
    const listener = (_event, payload) => callback(payload);
    ipcRenderer.on("translator:state", listener);
    return () => ipcRenderer.removeListener("translator:state", listener);
  },
});

// NeuroSeed API for consent-first memory reinforcement
contextBridge.exposeInMainWorld("neuroSeedApi", {
  getState: () => ipcRenderer.invoke("neuroseed:get-state"),
  putState: (payload) => ipcRenderer.invoke("neuroseed:put-state", payload),
});
