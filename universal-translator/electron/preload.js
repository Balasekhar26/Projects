const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("translatorApp", {
  getState: () => ipcRenderer.invoke("translator:get-state"),
  refreshRuntime: () => ipcRenderer.invoke("translator:refresh-runtime"),
  getSettings: () => ipcRenderer.invoke("translator:get-settings"),
  saveSettings: (payload) => ipcRenderer.invoke("translator:save-settings", payload),
  start: (payload) => ipcRenderer.invoke("translator:start", payload),
  stop: () => ipcRenderer.invoke("translator:stop"),
  getDevices: () => ipcRenderer.invoke("translator:get-devices"),
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
