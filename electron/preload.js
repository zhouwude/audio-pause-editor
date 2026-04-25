// Preload: 读取后端端口并注入到 window
const fs = require('fs');
const path = require('path');

try {
  const portFile = path.join(__dirname, '..', '.electron-port');
  const port = fs.readFileSync(portFile, 'utf-8').trim();
  window.__ELECTRON_API_PORT__ = parseInt(port, 10);
} catch (e) {
  console.warn('[preload] Failed to load port:', e.message);
}
