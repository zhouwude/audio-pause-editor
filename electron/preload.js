const { contextBridge, ipcRenderer } = require('electron');
const fs = require('fs');
const path = require('path');

// Read port from temp file — loadFile is called AFTER main writes this file
let apiPort = null;
try {
  const tmpDir = process.env.TEMP || process.env.TMP || process.env.TMPDIR || '/tmp';
  const portFile = path.join(tmpDir, '.audio-pause-editor-port');
  apiPort = parseInt(fs.readFileSync(portFile, 'utf-8').trim(), 10);
} catch (e) {
  apiPort = null;
}

contextBridge.exposeInMainWorld('electronAPI', {
  apiPort,
  windowControl: (action) => ipcRenderer.send('window-control', action),
});
