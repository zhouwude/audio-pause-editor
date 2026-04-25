# 音频停顿编辑器 (Audio Pause Editor)

桌面应用程序，用于分析并精确调整音频文件中的句间停顿间隔。适合播客制作、有声书剪辑、语音课程等内容创作者，可以在不依赖专业音频编辑软件的情况下快速控制说话节奏。

## 功能

- **上传音频** — 支持 MP3、WAV、OGG、FLAC、M4A、AAC、WMA，最大 50MB
- **自动检测停顿** — 基于 ffmpeg `silencedetect` 动态计算底噪阈值，自适应不同录音环境
- **波形可视化** — Canvas 渲染音频波形，叠加紫色停顿条，点击定位播放
- **逐段编辑** — 对每个停顿精确到毫秒级别调整，实时显示与原值的差值
- **批量操作** — 一键统一设置所有停顿时长，或一键重置
- **重新生成** — 根据调整后的参数拼接音频段，输出 44.1kHz 立体声 WAV
- **可调参数** — 噪音灵敏度（-35dB 保守 ~ -10dB 敏感）、最小停顿时长

## 架构

```
┌─────────────────────────────────────────┐
│           Electron (主进程)              │
│  窗口管理 · 生命周期 · 注入 API 端口      │
├──────────────┬──────────────────────────┤
│  前端 (HTML)  │   后端 (Python/FastAPI)   │
│  Canvas 波形  │   ffmpeg 音频处理         │
│  拖拽上传     │   silencedetect 检测      │
│  播放控制     │   concat 重新生成         │
└──────────────┴──────────────────────────┘
```

### 技术栈

| 层 | 技术 | 说明 |
|---|---|---|
| 桌面外壳 | Electron 33.x | 窗口管理、进程生命周期 |
| 构建打包 | electron-builder 25.x | 打包为 Windows EXE / Linux AppImage |
| 后端框架 | FastAPI 0.115 + uvicorn | REST API |
| 音频处理 | ffmpeg / ffprobe | 静音检测、波形提取、片段裁剪、拼接 |
| 前端 | 原生 HTML / CSS / JS | 无构建工具，单文件 |
| 生产打包 | PyInstaller | Python 后端 + ffmpeg 打包为独立 exe |

### API 端点

| 方法 | 路径 | 说明 |
|---|---|---|
| `POST` | `/api/upload` | 上传音频文件 |
| `POST` | `/api/analyze/{file_id}` | 检测停顿，返回暂停列表、底噪、阈值 |
| `POST` | `/api/generate` | 根据调整后的停顿参数重新生成音频 |
| `GET` | `/api/waveform/{file_id}` | 获取波形峰值数据（约 5000 个点） |
| `GET` | `/api/download/{filename}` | 下载处理后的音频 |
| `DELETE` | `/api/cleanup/{file_id}` | 清理临时文件 |

## 环境要求

- **Node.js** 18+
- **Python** 3.10+
- **ffmpeg** — 需要 `ffmpeg` 和 `ffprobe` 在系统 PATH 中，或通过环境变量指定：
  ```
  FFMPEG_PATH=/path/to/ffmpeg
  FFPROBE_PATH=/path/to/ffprobe
  ```

## 开发

```bash
# 安装前端依赖
npm install

# 安装 Python 依赖
pip install -r backend/requirements.txt

# 启动开发模式
npm run dev
```

开发模式下 Electron 会自动启动 Python 后端（优先使用 `venv` 中的 Python）。

## 构建

### 打包 sidecar（生产环境后端）

```bash
npm run build-sidecar
```

这会用 PyInstaller 把 FastAPI 后端 + ffmpeg 打包成一个独立的 `audio-pause-server.exe`。

### 打包 Electron 应用

```bash
# 生成未打包目录（用于测试）
npm run build:dir

# 生成 Windows 安装包
npx electron-builder --win
```

### 一键构建（Windows）

```cmd
build.bat
```

### 一键构建（WSL / Linux）

```bash
./build.sh
```

## 停顿检测算法

后端通过以下步骤自动识别语音中的停顿：

1. **测量底噪** — 使用 `volumedetect` 获取 `mean_volume`，底噪 ≈ mean - 12dB
2. **计算阈值** — 根据用户设定的灵敏度（-35 ~ -10dB）和底噪动态计算检测阈值
3. **检测静音** — 运行 `silencedetect`，过滤出超过最小持续时间的静音段
4. **后处理**：
   - 合并间距 < 0.2s 的相邻静音段
   - 过滤音频开头/结尾 1s 内的停顿
   - 确保相邻停顿之间有至少 0.15s 的语音间隔
5. **返回结果** — 每个停顿的起始时间、结束时间、时长

## 项目结构

```
audio-pause-editor-electron/
├── backend/
│   ├── main.py              # FastAPI 服务（核心音频逻辑）
│   └── requirements.txt     # Python 依赖
├── electron/
│   └── main.js              # Electron 主进程
├── frontend/
│   └── index.html            # 完整前端（UI + CSS + JS）
├── sidecar/
│   ├── sidecar_main.py      # PyInstaller 入口点
│   └── build-sidecar.spec   # PyInstaller 配置
├── build/
│   └── installer.nsi        # NSIS 安装包脚本
├── build.bat                # Windows 构建脚本
├── build.sh                 # WSL/Linux 构建脚本
├── package.json
└── README.md
```

## 许可

MIT
