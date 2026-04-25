const { contextBridge, ipcRenderer } = require('electron');
const fs = require('fs');
const path = require('path');

// Read port from temp file written by main process
let apiPort = null;
try {
  const portFile = path.join(
    process.env.TEMP || process.env.TMP || '/tmp',
    '.audio-pause-editor-port'
  );
  apiPort = parseInt(fs.readFileSync(portFile, 'utf-8').trim(), 10);
} catch (e) {
  apiPort = null;
}

contextBridge.exposeInMainWorld('electronAPI', {
  apiPort,
  windowControl: (action) => ipcRenderer.send('window-control', action),
});
