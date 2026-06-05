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
  
  // Security events
  onSecurityAlert: (callback) => ipcRenderer.on('security:alert', callback),
  sendSecurityAlert: (alert) => ipcRenderer.send('security:alert', alert),
  
  // App events
  onSettings: (callback) => ipcRenderer.on('app:settings', callback),
  onCheckUpdates: (callback) => ipcRenderer.on('app:check-updates', callback),
  
  // Security events
  onNewScan: (callback) => ipcRenderer.on('security:new-scan', callback),
  onQuickScan: (callback) => ipcRenderer.on('security:quick-scan', callback),
  onDeepScan: (callback) => ipcRenderer.on('security:deep-scan', callback),
  onViewLogs: (callback) => ipcRenderer.on('security:view-logs', callback),
  onSecuritySettings: (callback) => ipcRenderer.on('security:settings', callback),
  onOpenReport: (callback) => ipcRenderer.on('security:open-report', callback),
  onScan: (callback) => ipcRenderer.on('security:scan', callback),
  
  // View events
  onDashboard: (callback) => ipcRenderer.on('view:dashboard', callback),
  onThreats: (callback) => ipcRenderer.on('view:threats', callback),
  onReports: (callback) => ipcRenderer.on('view:reports', callback),
  
  // Remove listeners
  removeAllListeners: (channel) => ipcRenderer.removeAllListeners(channel)
});

// Security: Prevent node integration in renderer
window.nodeRequire = undefined;
window.require = undefined;
window.process = undefined;
window.global = undefined;
window.Buffer = undefined;
