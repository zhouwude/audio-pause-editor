const { app, BrowserWindow, dialog } = require('electron');
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
    title: '音频停顿编辑器',
    center: true,
    resizable: true,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: false,
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

    // 生产模式：从 resources 读前端文件；开发模式：从项目目录读
    const frontendPath = process.resourcesPath && fs.existsSync(path.join(process.resourcesPath, 'frontend', 'index.html'))
      ? path.join(process.resourcesPath, 'frontend', 'index.html')
      : path.join(__dirname, '..', 'frontend', 'index.html');

    // 写端口到临时文件，preload 脚本读取
    const portFile = path.join(__dirname, '..', '.electron-port');
    fs.writeFileSync(portFile, String(port));

    mainWindow.loadFile(frontendPath);

    // Debug mode: open DevTools automatically (development only, no resourcesPath)
    if (!process.resourcesPath) {
      mainWindow.webContents.openDevTools();
    }
  }).catch(() => {
    dialog.showErrorBox('启动失败', '无法启动后端服务。');
    app.quit();
  });

  mainWindow.on('closed', () => { mainWindow = null; });
}

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
