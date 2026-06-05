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

  // AI events
  onAINotification: (callback) => ipcRenderer.on('ai:notification', callback),
  sendAINotification: (notification) => ipcRenderer.send('ai:notification', notification),

  // App events
  onSettings: (callback) => ipcRenderer.on('app:settings', callback),
  onCheckUpdates: (callback) => ipcRenderer.on('app:check-updates', callback),

  // AI events
  onNewConversation: (callback) => ipcRenderer.on('ai:new-conversation', callback),
  onLoadConversation: (callback) => ipcRenderer.on('ai:load-conversation', callback),
  onSaveConversation: (callback) => ipcRenderer.on('ai:save-conversation', callback),
  onSingleAgent: (callback) => ipcRenderer.on('ai:single-agent', callback),
  onMultiAgent: (callback) => ipcRenderer.on('ai:multi-agent', callback),
  onToolSelection: (callback) => ipcRenderer.on('ai:tool-selection', callback),
  onPerformance: (callback) => ipcRenderer.on('ai:performance', callback),
  onAISettings: (callback) => ipcRenderer.on('ai:settings', callback),
  onAssistant: (callback) => ipcRenderer.on('ai:assistant', callback),
  sendAIMessage: (prompt) => ipcRenderer.invoke('ai:sendMessage', prompt),

  // View events
  onDashboard: (callback) => ipcRenderer.on('view:dashboard', callback),
  onAgents: (callback) => ipcRenderer.on('view:agents', callback),
  onConversations: (callback) => ipcRenderer.on('view:conversations', callback),

  // Remove listeners
  removeAllListeners: (channel) => ipcRenderer.removeAllListeners(channel)
});

// Security: Prevent node integration in renderer
window.nodeRequire = undefined;
window.require = undefined;
window.process = undefined;
window.global = undefined;
window.Buffer = undefined;
