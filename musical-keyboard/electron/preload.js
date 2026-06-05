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
  
  // Keyboard events
  onKeyboardNotification: (callback) => ipcRenderer.on('keyboard:notification', callback),
  sendKeyboardNotification: (notification) => ipcRenderer.send('keyboard:notification', notification),
  
  // App events
  onSettings: (callback) => ipcRenderer.on('app:settings', callback),
  onCheckUpdates: (callback) => ipcRenderer.on('app:check-updates', callback),
  
  // Keyboard events
  onNewRecording: (callback) => ipcRenderer.on('keyboard:new-recording', callback),
  onOpenRecording: (callback) => ipcRenderer.on('keyboard:open-recording', callback),
  onSaveRecording: (callback) => ipcRenderer.on('keyboard:save-recording', callback),
  onInstrument: (callback) => ipcRenderer.on('keyboard:instrument', callback),
  onRecord: (callback) => ipcRenderer.on('keyboard:record', callback),
  onStopRecording: (callback) => ipcRenderer.on('keyboard:stop-recording', callback),
  onPlayback: (callback) => ipcRenderer.on('keyboard:playback', callback),
  onQuickPlay: (callback) => ipcRenderer.on('keyboard:quick-play', callback),
  
  // View events
  onKeyboard: (callback) => ipcRenderer.on('view:keyboard', callback),
  onSettings: (callback) => ipcRenderer.on('view:settings', callback),
  onRecordings: (callback) => ipcRenderer.on('view:recordings', callback),
  
  // Remove listeners
  removeAllListeners: (channel) => ipcRenderer.removeAllListeners(channel),
  
  // Focus events from main process
  onFocus: (callback) => ipcRenderer.on('app:focus', callback),
  onBlur: (callback) => ipcRenderer.on('app:blur', callback),
  
  // Background mode events from main process
  onToggleBackground: (callback) => ipcRenderer.on('app:toggle-background', callback),
  onBackgroundNote: (callback) => ipcRenderer.on('app:background-note', callback)
});

// Security: Prevent node integration in renderer
window.nodeRequire = undefined;
window.require = undefined;
window.process = undefined;
window.global = undefined;
window.Buffer = undefined;
