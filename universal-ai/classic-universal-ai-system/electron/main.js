const { app, BrowserWindow, ipcMain, Menu, Tray, dialog } = require('electron');
const path = require('path');
const fs = require('fs');
const { spawn } = require('child_process');

let mainWindow = null;
let tray = null;
const isDev = process.env.NODE_ENV === 'development';

const appIcon = path.join(__dirname, 'assets', 'icon.png');
const iconExists = fs.existsSync(appIcon);

// Create system tray
function createTray() {
  if (!iconExists) {
    return;
  }

  tray = new Tray(appIcon);

  const contextMenu = Menu.buildFromTemplate([
    {
      label: 'Show Universal AI System',
      click: () => {
        if (mainWindow) {
          mainWindow.show();
          mainWindow.focus();
        }
      }
    },
    {
      label: 'AI Assistant',
      click: () => {
        if (mainWindow) {
          mainWindow.webContents.send('ai:assistant');
        }
      }
    },
    {
      label: 'Multi-Agent Mode',
      click: () => {
        if (mainWindow) {
          mainWindow.webContents.send('ai:multi-agent');
        }
      }
    },
    { type: 'separator' },
    {
      label: 'Settings',
      click: () => {
        if (mainWindow) {
          mainWindow.webContents.send('app:settings');
        }
      }
    },
    {
      label: 'Exit',
      click: () => {
        app.quit();
      }
    }
  ]);

  tray.setToolTip('Universal AI System - Multi-Agent Intelligence');
  tray.setContextMenu(contextMenu);

  tray.on('click', () => {
    if (mainWindow) {
      mainWindow.isVisible() ? mainWindow.hide() : mainWindow.show();
    }
  });
}

// Create main window
function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 1000,
    minHeight: 700,
    icon: iconExists ? appIcon : undefined,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      enableRemoteModule: false,
      preload: path.join(__dirname, 'preload.js'),
      webSecurity: true,
      allowRunningInsecureContent: false
    },
    show: false,
    titleBarStyle: 'default',
    backgroundColor: '#0f0f23'
  });

  // Load the app
  const startUrl = isDev
    ? 'http://localhost:5173'
    : `file://${path.join(__dirname, '../ai-assistant/dist/index.html')}`;

  mainWindow.loadURL(startUrl);

  // Show window when ready
  mainWindow.once('ready-to-show', () => {
    mainWindow.show();

    // Open DevTools in development
    if (isDev) {
      mainWindow.webContents.openDevTools();
    }
  });

  // Handle window closed
  mainWindow.on('closed', () => {
    mainWindow = null;
  });

  // Handle external links
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    require('electron').shell.openExternal(url);
    return { action: 'deny' };
  });

  // Create application menu
  createMenu();
}

// Create application menu
function createMenu() {
  const template = [
    {
      label: 'File',
      submenu: [
        {
          label: 'New Conversation',
          accelerator: 'CmdOrCtrl+N',
          click: () => {
            if (mainWindow) {
              mainWindow.webContents.send('ai:new-conversation');
            }
          }
        },
        {
          label: 'Load Conversation',
          accelerator: 'CmdOrCtrl+O',
          click: async () => {
            const result = await dialog.showOpenDialog(mainWindow, {
              properties: ['openFile'],
              filters: [
                { name: 'AI Conversations', extensions: ['json', 'txt'] },
                { name: 'All Files', extensions: ['*'] }
              ]
            });

            if (!result.canceled) {
              mainWindow.webContents.send('ai:load-conversation', result.filePaths[0]);
            }
          }
        },
        {
          label: 'Save Conversation',
          accelerator: 'CmdOrCtrl+S',
          click: () => {
            if (mainWindow) {
              mainWindow.webContents.send('ai:save-conversation');
            }
          }
        },
        { type: 'separator' },
        {
          label: 'Exit',
          accelerator: process.platform === 'darwin' ? 'Cmd+Q' : 'Ctrl+Q',
          click: () => {
            app.quit();
          }
        }
      ]
    },
    {
      label: 'AI',
      submenu: [
        {
          label: 'Single Agent',
          accelerator: 'CmdOrCtrl+1',
          click: () => {
            if (mainWindow) {
              mainWindow.webContents.send('ai:single-agent');
            }
          }
        },
        {
          label: 'Multi-Agent',
          accelerator: 'CmdOrCtrl+2',
          click: () => {
            if (mainWindow) {
              mainWindow.webContents.send('ai:multi-agent');
            }
          }
        },
        {
          label: 'Tool Selection',
          accelerator: 'CmdOrCtrl+T',
          click: () => {
            if (mainWindow) {
              mainWindow.webContents.send('ai:tool-selection');
            }
          }
        },
        { type: 'separator' },
        {
          label: 'Performance Monitor',
          accelerator: 'CmdOrCtrl+P',
          click: () => {
            if (mainWindow) {
              mainWindow.webContents.send('ai:performance');
            }
          }
        },
        {
          label: 'Agent Settings',
          accelerator: 'CmdOrCtrl+,',
          click: () => {
            if (mainWindow) {
              mainWindow.webContents.send('ai:settings');
            }
          }
        }
      ]
    },
    {
      label: 'View',
      submenu: [
        {
          label: 'Dashboard',
          accelerator: 'CmdOrCtrl+Shift+D',
          click: () => {
            if (mainWindow) {
              mainWindow.webContents.send('view:dashboard');
            }
          }
        },
        {
          label: 'Agents',
          accelerator: 'CmdOrCtrl+Shift+A',
          click: () => {
            if (mainWindow) {
              mainWindow.webContents.send('view:agents');
            }
          }
        },
        {
          label: 'Conversations',
          accelerator: 'CmdOrCtrl+Shift+C',
          click: () => {
            if (mainWindow) {
              mainWindow.webContents.send('view:conversations');
            }
          }
        },
        { type: 'separator' },
        {
          label: 'Reload',
          accelerator: 'CmdOrCtrl+R',
          click: () => {
            if (mainWindow) {
              mainWindow.reload();
            }
          }
        },
        {
          label: 'Toggle Developer Tools',
          accelerator: 'F12',
          click: () => {
            if (mainWindow) {
              mainWindow.webContents.toggleDevTools();
            }
          }
        }
      ]
    },
    {
      label: 'Window',
      submenu: [
        {
          label: 'Minimize',
          accelerator: 'CmdOrCtrl+M',
          role: 'minimize'
        },
        {
          label: 'Close',
          accelerator: 'CmdOrCtrl+W',
          role: 'close'
        }
      ]
    },
    {
      label: 'Help',
      submenu: [
        {
          label: 'About Universal AI System',
          click: () => {
            dialog.showMessageBox(mainWindow, {
              type: 'info',
              title: 'About Universal AI System',
              message: 'Universal AI System',
              detail: 'Multi-Agent AI Platform\nVersion 1.0.0\n\nAdvanced AI system with multiple agents, tool selection, and intelligent orchestration for complex problem-solving.',
              buttons: ['OK']
            });
          }
        },
        {
          label: 'Documentation',
          click: () => {
            require('electron').shell.openExternal('https://github.com/balasekhar26/universal-ai-system');
          }
        },
        {
          label: 'Check for Updates',
          click: () => {
            if (mainWindow) {
              mainWindow.webContents.send('app:check-updates');
            }
          }
        }
      ]
    }
  ];

  const menu = Menu.buildFromTemplate(template);
  Menu.setApplicationMenu(menu);
}

// IPC handlers
ipcMain.handle('app:getVersion', () => {
  return app.getVersion();
});

ipcMain.handle('app:getPlatform', () => {
  return process.platform;
});

ipcMain.handle('app:showMessageBox', async (event, options) => {
  const result = await dialog.showMessageBox(mainWindow, options);
  return result;
});

ipcMain.handle('app:showSaveDialog', async (event, options) => {
  const result = await dialog.showSaveDialog(mainWindow, options);
  return result;
});

ipcMain.handle('app:showOpenDialog', async (event, options) => {
  const result = await dialog.showOpenDialog(mainWindow, options);
  return result;
});

ipcMain.handle('app:writeFile', async (event, filePath, data) => {
  try {
    await fs.promises.writeFile(filePath, data);
    return { success: true };
  } catch (error) {
    return { success: false, error: error.message };
  }
});

ipcMain.handle('app:readFile', async (event, filePath) => {
  try {
    const data = await fs.promises.readFile(filePath, 'utf8');
    return { success: true, data };
  } catch (error) {
    return { success: false, error: error.message };
  }
});

function findPythonExecutable() {
  const candidates = [process.env.PYTHON, process.env.PYTHONPATH, 'python', 'python3', 'py'];
  return candidates.find((candidate) => typeof candidate === 'string' && candidate.trim().length > 0);
}

function runPythonPrompt(prompt) {
  return new Promise((resolve, reject) => {
    const pythonCommand = findPythonExecutable();
    if (!pythonCommand) {
      return reject(new Error('Python executable not found. Please install Python or set the PYTHON environment variable.'));
    }

    const scriptPath = path.join(__dirname, '../ai_universal_system.py');
    const child = spawn(pythonCommand, [scriptPath, '--once', prompt, '--no-setup'], {
      cwd: path.join(__dirname, '..'),
      env: process.env,
      stdio: ['ignore', 'pipe', 'pipe'],
    });

    let stdout = '';
    let stderr = '';

    child.stdout.on('data', (data) => {
      stdout += data.toString();
    });

    child.stderr.on('data', (data) => {
      stderr += data.toString();
    });

    child.on('error', (error) => {
      reject(error);
    });

    child.on('close', (code) => {
      if (code === 0) {
        resolve(stdout.trim());
      } else {
        reject(new Error(stderr.trim() || stdout.trim() || `Python execution failed with code ${code}`));
      }
    });
  });
}

ipcMain.handle('ai:sendMessage', async (event, prompt) => {
  try {
    const message = await runPythonPrompt(prompt);
    return { success: true, message };
  } catch (error) {
    return { success: false, error: error instanceof Error ? error.message : String(error) };
  }
});

// AI system events
ipcMain.on('ai:notification', (event, notification) => {
  // Show system notification for important AI events
  const { Notification } = require('electron');

  if (Notification.isSupported()) {
    new Notification({
      title: 'AI System Alert',
      body: notification.message,
      urgency: notification.priority === 'high' ? 'critical' : 'normal'
    }).show();
  }
});

// Auto-start functionality
function setupAutoStart() {
  if (process.platform === 'win32') {
    const { app } = require('electron');
    app.setLoginItemSettings({
      openAtLogin: true,
      path: app.getPath('exe'),
      args: []
    });
  }
}

// Single instance enforcement
const gotTheLock = app.requestSingleInstanceLock();

if (!gotTheLock) {
  app.quit();
} else {
  app.on('second-instance', () => {
    // Someone tried to run a second instance, we should focus our window
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.focus();
    }
  });
}

// App events
app.whenReady().then(() => {
  createWindow();
  createTray();

  // Setup auto-start
  setupAutoStart();
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    createWindow();
  }
});

app.on('before-quit', () => {
  // Cleanup before quitting
  if (tray) {
    tray.destroy();
  }
});

// Security: prevent navigation to external sites
app.on('web-contents-created', (event, contents) => {
  contents.on('will-navigate', (event, navigationUrl) => {
    const parsedUrl = new URL(navigationUrl);

    if (parsedUrl.origin !== 'http://localhost:3000' && !navigationUrl.startsWith('file://')) {
      event.preventDefault();
      require('electron').shell.openExternal(navigationUrl);
    }
  });
});

// Handle certificate errors
app.on('certificate-error', (event, webContents, url, error, certificate, callback) => {
  // On production, you might want to handle certificate errors more carefully
  if (isDev) {
    // Allow all certificates in development
    event.preventDefault();
    callback(true);
  } else {
    callback(false);
  }
});

module.exports = { mainWindow, tray };
