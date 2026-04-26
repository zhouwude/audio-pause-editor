const { app, BrowserWindow, dialog, ipcMain } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const fs = require('fs');
const os = require('os');

let mainWindow = null;
let backendProcess = null;
let apiPort = null;

// IPC: renderer asks for API port
ipcMain.handle('get-api-port', () => apiPort);

// IPC: renderer asks for frontend resources path (production)
ipcMain.handle('get-frontend-path', () => {
  const candidates = [
    process.resourcesPath && path.join(process.resourcesPath, 'frontend', 'index.html'),
    path.join(__dirname, '..', 'frontend', 'index.html'),
  ].filter(Boolean);
  for (const p of candidates) {
    if (fs.existsSync(p)) return p;
  }
  return null;
});

function killBackend() {
  if (!backendProcess) return;
  const pid = backendProcess.pid;
  if (pid) {
    console.log('[Main] Killing backend PID:', pid);
    if (os.platform() === 'win32') {
      require('child_process').spawn('taskkill', ['/F', '/T', '/PID', String(pid)], {
        stdio: 'ignore',
        windowsHide: true,
      });
    } else {
      try { backendProcess.kill('SIGKILL'); } catch (e) {}
    }
  }
  backendProcess = null;
  apiPort = null;
}

function startBackend(resolve) {
  if (apiPort) { resolve(apiPort); return; }

  // 生产模式：使用 onedir 打包的 sidecar
  const sidecarExe = process.resourcesPath
    ? path.join(process.resourcesPath, 'audio-pause-server', 'audio-pause-server.exe')
    : null;

  if (sidecarExe && fs.existsSync(sidecarExe)) {
    backendProcess = spawn(sidecarExe, [], {
      stdio: ['pipe', 'pipe', 'pipe'],
      env: { ...process.env },
      windowsHide: true,
      detached: false,
    });
    console.log('[Backend] Spawning sidecar exe:', sidecarExe);
  } else {
    const pythonExe = os.platform() === 'win32' ? 'python.exe' : 'python3';
    let pythonCmd = pythonExe;
    const venvPython = path.join(__dirname, '..', 'venv', os.platform() === 'win32' ? 'Scripts' : 'bin', pythonExe);
    if (fs.existsSync(venvPython)) pythonCmd = venvPython;

    const backendDir = path.join(__dirname, '..', 'backend');
    backendProcess = spawn(pythonCmd, [path.join(backendDir, 'main.py')], {
      stdio: ['pipe', 'pipe', 'pipe'],
      env: { ...process.env },
      windowsHide: true,
    });
    console.log('[Backend] Spawning python:', pythonCmd, backendDir);
  }

  backendProcess.stdout.on('data', (data) => {
    const match = data.toString().match(/PORT:(\d+)/);
    if (match) {
      apiPort = parseInt(match[1], 10);
      resolve(apiPort);
    }
  });

  backendProcess.stderr.on('data', (data) => {
    console.error('[Backend]', data.toString());
  });

  backendProcess.on('error', (err) => {
    console.error('[Backend] Failed to start:', err.message);
    if (!apiPort) resolve(null);
  });

  backendProcess.on('exit', (code) => {
    console.log(`[Backend] Exited with code ${code}`);
    if (!apiPort) resolve(null);
    backendProcess = null;
    apiPort = null;
  });
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 900,
    frame: false,
    titleBarStyle: 'hidden',
    center: true,
    resizable: true,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.js'),
    },
  });

  const portPromise = new Promise((resolve) => startBackend(resolve));

  portPromise.then((port) => {
    if (!port) {
      dialog.showErrorBox('启动失败', '无法启动 Python 后端，请确认已安装 Python 3.10+ 并安装了 fastapi、uvicorn 依赖。');
      app.quit();
      return;
    }

    // 端口存在内存中，preload 通过 IPC 获取
    console.log('[Main] API port:', port);

    // 加载前端页面
    const frontendPath = process.resourcesPath && fs.existsSync(path.join(process.resourcesPath, 'frontend', 'index.html'))
      ? path.join(process.resourcesPath, 'frontend', 'index.html')
      : path.join(__dirname, '..', 'frontend', 'index.html');

    mainWindow.loadFile(frontendPath);
    console.log('[Main] loadFile:', frontendPath);

    // Debug mode
    if (!process.resourcesPath) {
      mainWindow.webContents.openDevTools();
    }
  }).catch(() => {
    dialog.showErrorBox('启动失败', '无法启动后端服务。');
    app.quit();
  });

  mainWindow.on('closed', () => { mainWindow = null; });

  // Ensure backend is killed when the window closes
  mainWindow.on('close', () => {
    killBackend();
  });
}

const WINDOW_ACTIONS = new Set(['window-minimize', 'window-maximize', 'window-close']);

ipcMain.on('window-control', (event, action) => {
  if (!WINDOW_ACTIONS.has(action) || !mainWindow) return;
  const method = action.replace('window-', '');
  if (method === 'maximize') {
    mainWindow.isMaximized() ? mainWindow.unmaximize() : mainWindow.maximize();
  } else {
    mainWindow[method]();
  }
});

app.commandLine.appendSwitch('--disable-gpu');

app.whenReady().then(createWindow);

app.on('window-all-closed', () => {
  killBackend();
  app.quit();
});

app.on('before-quit', () => {
  killBackend();
});

process.on('SIGINT', () => {
  killBackend();
  app.quit();
});

// Ultimate fallback: kill backend if Node exits for any reason
process.on('exit', killBackend);

app.on('activate', () => {
  if (mainWindow === null) createWindow();
});
