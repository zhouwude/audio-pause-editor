const { app, BrowserWindow, dialog, ipcMain } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const fs = require('fs');
const os = require('os');

let mainWindow = null;
let backendProcess = null;
let apiPort = null;

function startBackend(resolve) {
  if (apiPort) { resolve(apiPort); return; }

  // 生产模式：使用打包好的 sidecar exe
  const sidecarExe = process.resourcesPath
    ? path.join(process.resourcesPath, 'audio-pause-server.exe')
    : null;

  if (sidecarExe && fs.existsSync(sidecarExe)) {
    backendProcess = spawn(sidecarExe, [], {
      stdio: ['pipe', 'pipe', 'pipe'],
      env: { ...process.env },
    });
    console.log('[Backend] Spawning sidecar exe:', sidecarExe);
  } else {
    // 开发模式：python backend/main.py
    const pythonExe = os.platform() === 'win32' ? 'python.exe' : 'python3';
    let pythonCmd = pythonExe;
    const venvPython = path.join(__dirname, '..', 'venv', os.platform() === 'win32' ? 'Scripts' : 'bin', pythonExe);
    if (fs.existsSync(venvPython)) pythonCmd = venvPython;

    const backendDir = path.join(__dirname, '..', 'backend');
    backendProcess = spawn(pythonCmd, [path.join(backendDir, 'main.py')], {
      stdio: ['pipe', 'pipe', 'pipe'],
      env: { ...process.env },
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

    // 写端口到系统临时目录（开发+生产统一路径）
    const portFile = path.join(
      os.tmpdir(),
      '.audio-pause-editor-port'
    );
    fs.writeFileSync(portFile, String(port));
    console.log('[Main] Port file written:', portFile, 'port:', port);

    // 生产模式从 resources 读，开发模式从项目目录读
    const frontendPath = process.resourcesPath && fs.existsSync(path.join(process.resourcesPath, 'frontend', 'index.html'))
      ? path.join(process.resourcesPath, 'frontend', 'index.html')
      : path.join(__dirname, '..', 'frontend', 'index.html');

    mainWindow.loadFile(frontendPath);
    console.log('[Main] loadFile:', frontendPath);

    // Debug mode: open DevTools (development only)
    if (!process.resourcesPath) {
      mainWindow.webContents.openDevTools();
    }
  }).catch(() => {
    dialog.showErrorBox('启动失败', '无法启动后端服务。');
    app.quit();
  });

  mainWindow.on('closed', () => { mainWindow = null; });
}

// Window control IPC handlers with channel validation
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
  if (backendProcess) {
    backendProcess.kill('SIGINT');
    backendProcess = null;
  }
  app.quit();
});

process.on('SIGINT', () => {
  if (backendProcess) backendProcess.kill('SIGINT');
  app.quit();
});

app.on('activate', () => {
  if (mainWindow === null) createWindow();
});
