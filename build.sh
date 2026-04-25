#!/bin/bash
# 音频停顿编辑器 - WSL 完整构建脚本
# 需要: sidecar/audio-pause-server.exe 已存在（在 Windows 上用 PyInstaller 构建）

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo ""
echo "========================================"
echo " 构建音频停顿编辑器 (Electron)"
echo "========================================"
echo ""

# 检查 sidecar exe
if [ ! -f "sidecar/audio-pause-server.exe" ]; then
    echo "缺少 sidecar exe: sidecar/audio-pause-server.exe"
    echo "请先在 Windows 上运行: pyinstaller --clean --onefile sidecar/build-sidecar.spec"
    echo "并将生成的 audio-pause-server.exe 复制到 sidecar/ 目录"
    exit 1
fi

echo "[1/2] 构建 Electron 应用..."
npx electron-builder --win --dir

echo "[2/2] 生成 NSIS 安装包..."
makensis build/installer.nsi

echo ""
echo "========================================"
echo " 构建完成！"
echo "========================================"
echo ""
echo "安装包: dist/audio-pause-editor_0.1.0_x64-setup.exe"
echo ""
