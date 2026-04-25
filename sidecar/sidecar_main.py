"""Electron 版 Python Sidecar — PyInstaller 打包入口"""
import os
import signal
import socket
import subprocess
import sys
from pathlib import Path


def get_bundle_dir():
    """PyInstaller --onefile 运行时，所有资源解压在此"""
    if getattr(sys, 'frozen', False):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent


def find_free_port(preferred=8888):
    """找到空闲端口，占用时强制释放"""
    if preferred > 0:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind(('127.0.0.1', preferred))
                return preferred
        except OSError:
            if os.name == 'nt':
                result = subprocess.run(
                    ['netstat', '-ano'], capture_output=True, text=True
                )
                for line in result.stdout.splitlines():
                    if f':{preferred}' in line and 'LISTENING' in line:
                        parts = line.split()
                        pid = parts[-1]
                        subprocess.run(['taskkill', '/F', '/PID', pid], capture_output=True)
                        break
            else:
                result = subprocess.run(
                    ['lsof', '-ti', f':{preferred}'], capture_output=True, text=True
                )
                if result.stdout.strip():
                    subprocess.run(['kill', '-9', result.stdout.strip()], capture_output=True)
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    s.bind(('127.0.0.1', preferred))
                    return preferred
            except OSError:
                pass
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def main():
    bundle_dir = get_bundle_dir()

    # 设置 ffmpeg 路径
    ffmpeg_dir = bundle_dir / 'ffmpeg'
    if ffmpeg_dir.exists():
        if os.name == 'nt':
            ffmpeg_exe = ffmpeg_dir / 'ffmpeg.exe'
            ffprobe_exe = ffmpeg_dir / 'ffprobe.exe'
        else:
            ffmpeg_exe = ffmpeg_dir / 'ffmpeg'
            ffprobe_exe = ffmpeg_dir / 'ffprobe'
        if ffmpeg_exe.exists():
            os.environ['FFMPEG_PATH'] = str(ffmpeg_exe)
        if ffprobe_exe.exists():
            os.environ['FFPROBE_PATH'] = str(ffprobe_exe)

    # 找端口并打印
    port = find_free_port(8888)
    print(f'PORT:{port}', flush=True)

    # 让 Python 能找到 backend 模块
    sys.path.insert(0, str(bundle_dir))
    from backend.main import app
    import uvicorn

    # 优雅退出
    server = uvicorn.Server(
        config=uvicorn.Config(app, host='127.0.0.1', port=port, log_level='warning')
    )

    def _shutdown(signum=None, frame=None):
        server.should_exit = True

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    import asyncio
    asyncio.run(server.serve())


if __name__ == '__main__':
    main()
