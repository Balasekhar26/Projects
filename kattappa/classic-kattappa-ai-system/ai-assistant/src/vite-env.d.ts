/// <reference types="vite/client" />

declare interface ElectronAPI {
  sendAIMessage: (prompt: string) => Promise<{ success: boolean; message: string; error?: string }>
}

declare interface Window {
  electronAPI?: ElectronAPI
}
