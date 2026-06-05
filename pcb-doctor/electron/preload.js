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
  
  // PCB events
  onPCBAlert: (callback) => ipcRenderer.on('pcb:alert', callback),
  sendPCBAlert: (alert) => ipcRenderer.send('pcb:alert', alert),
  
  // App events
  onSettings: (callback) => ipcRenderer.on('app:settings', callback),
  onCheckUpdates: (callback) => ipcRenderer.on('app:check-updates', callback),
  
  // PCB events
  onNewDiagnosis: (callback) => ipcRenderer.on('pcb:new-diagnosis', callback),
  onOpenImage: (callback) => ipcRenderer.on('pcb:open-image', callback),
  onSaveReport: (callback) => ipcRenderer.on('pcb:save-report', callback),
  onQuickScan: (callback) => ipcRenderer.on('pcb:quick-scan', callback),
  onDeepAnalysis: (callback) => ipcRenderer.on('pcb:deep-analysis', callback),
  onComponentDetection: (callback) => ipcRenderer.on('pcb:component-detection', callback),
  onVisionAnalysis: (callback) => ipcRenderer.on('pcb:vision-analysis', callback),
  onTraceAnalysis: (callback) => ipcRenderer.on('pcb:trace-analysis', callback),
  onQuickDiagnosis: (callback) => ipcRenderer.on('pcb:quick-diagnosis', callback),
  onScan: (callback) => ipcRenderer.on('pcb:scan', callback),
  
  // View events
  onDashboard: (callback) => ipcRenderer.on('view:dashboard', callback),
  onAnalysis: (callback) => ipcRenderer.on('view:analysis', callback),
  onReports: (callback) => ipcRenderer.on('view:reports', callback),
  onHistory: (callback) => ipcRenderer.on('view:history', callback),
  
  // Remove listeners
  removeAllListeners: (channel) => ipcRenderer.removeAllListeners(channel)
});

// Security: Prevent node integration in renderer
window.nodeRequire = undefined;
window.require = undefined;
window.process = undefined;
window.global = undefined;
window.Buffer = undefined;
