const { contextBridge, ipcRenderer } = require('electron');

// Expose protected methods that allow the renderer process to use
// the ipcRenderer without exposing the entire object
contextBridge.exposeInMainWorld('electronAPI', {
  // App info
  getVersion: () => ipcRenderer.invoke('app:getVersion'),
  getPlatform: () => ipcRenderer.invoke('app:getPlatform'),
  
  // Dialogs
  showMessageBox: (options) => ipcRenderer.invoke('app:showMessageBox', options),
  showSaveDialog: (options) => ipcRenderer.invoke('app:showSaveDialog', options),
  showOpenDialog: (options) => ipcRenderer.invoke('app:showOpenDialog', options),
  
  // File operations
  writeFile: (filePath, data) => ipcRenderer.invoke('app:writeFile', filePath, data),
  readFile: (filePath) => ipcRenderer.invoke('app:readFile', filePath),
  
  // DEWS events
  onDEWSAlert: (callback) => ipcRenderer.on('dews:alert', callback),
  sendDEWSAlert: (alert) => ipcRenderer.send('dews:alert', alert),
  
  // App events
  onSettings: (callback) => ipcRenderer.on('app:settings', callback),
  onCheckUpdates: (callback) => ipcRenderer.on('app:check-updates', callback),
  
  // DEWS events
  onNewSimulation: (callback) => ipcRenderer.on('dews:new-simulation', callback),
  onLoadScenario: (callback) => ipcRenderer.on('dews:load-scenario', callback),
  onSaveSimulation: (callback) => ipcRenderer.on('dews:save-simulation', callback),
  onQuickStart: (callback) => ipcRenderer.on('dews:quick-start', callback),
  onSafetyProtocol: (callback) => ipcRenderer.on('dews:safety-protocol', callback),
  onThreatScenario: (callback) => ipcRenderer.on('dews:threat-scenario', callback),
  onRealTimeMonitoring: (callback) => ipcRenderer.on('dews:real-time-monitoring', callback),
  onTelemetryAnalysis: (callback) => ipcRenderer.on('dews:telemetry-analysis', callback),
  onQuickSimulation: (callback) => ipcRenderer.on('dews:quick-simulation', callback),
  onSafetyCheck: (callback) => ipcRenderer.on('dews:safety-check', callback),
  
  // View events
  onDashboard: (callback) => ipcRenderer.on('view:dashboard', callback),
  onSimulation: (callback) => ipcRenderer.on('view:simulation', callback),
  onThreats: (callback) => ipcRenderer.on('view:threats', callback),
  onTelemetry: (callback) => ipcRenderer.on('view:telemetry', callback),
  
  // Remove listeners
  removeAllListeners: (channel) => ipcRenderer.removeAllListeners(channel)
});

// Security: Prevent node integration in renderer
window.nodeRequire = undefined;
window.require = undefined;
window.process = undefined;
window.global = undefined;
window.Buffer = undefined;
