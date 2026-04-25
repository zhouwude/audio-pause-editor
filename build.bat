@echo off
REM 音频停顿编辑器 - 完整构建脚本 (Windows)
REM 在 Windows PowerShell/CMD 中运行

setlocal
set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

echo.
echo ========================================
echo  构建音频停顿编辑器 (Electron)
echo ========================================
echo.

echo [1/3] 构建 Python Sidecar...
call venv\Scripts\activate.bat
pyinstaller --clean --onefile sidecar\build-sidecar.spec
if %errorlevel% neq 0 (
    echo Sidecar 构建失败！
    pause
    exit /b 1
)

REM 复制 sidecar exe 到 sidecar/ 目录（PyInstaller 默认输出到 dist/）
copy /Y dist\audio-pause-server.exe sidecar\audio-pause-server.exe >nul

echo.
echo [2/3] 构建 Electron 应用...
call npm run build:dir
if %errorlevel% neq 0 (
    echo Electron 构建失败！
    pause
    exit /b 1
)

echo.
echo [3/3] 生成 NSIS 安装包...
cd build
makensis installer.nsi
cd ..

echo.
echo ========================================
echo  构建完成！
echo ========================================
echo.
echo 安装包: dist\audio-pause-editor_0.1.0_x64-setup.exe
echo.
pause
