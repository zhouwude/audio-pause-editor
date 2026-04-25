#!/usr/bin/env python3
"""
音频停顿编辑器后端
FastAPI + ffmpeg 实现音频分析、停顿调整、重新导出
"""

import os
import re
import tempfile
import uuid
import json
import shutil
import struct
import subprocess
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

app = FastAPI(title="音频停顿编辑器", description="分析并调整音频中的句间停顿")

# CORS — Electron 从 file:// 加载，需要允许跨域
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 临时文件目录 — 使用系统 TEMP，Linux 下优先用 TMPDIR
TEMP_DIR = Path(os.environ.get('TMPDIR', os.environ.get('TEMP', tempfile.gettempdir()))) / 'audio-pause-editor'
TEMP_DIR.mkdir(parents=True, exist_ok=True)

# 上传文件最大 50MB
MAX_UPLOAD_SIZE = 50 * 1024 * 1024

# ffmpeg / ffprobe 路径（桌面打包时通过环境变量指定）
FFMPEG = os.environ.get('FFMPEG_PATH', 'ffmpeg')
FFPROBE = os.environ.get('FFPROBE_PATH', 'ffprobe')

# 停顿检测参数
MERGE_GAP = 0.2        # 间距 < 0.2s 的相邻静音合并为一个
EDGE_MARGIN = 1.0      # 过滤音频开头/结尾 1 秒内的停顿
SPEECH_MIN = 0.15      # 两个停顿之间至少要有 0.15s 语音才算独立


class PauseInfo(BaseModel):
    """停顿信息"""
    index: int
    start: float       # 静音段开始时间（秒）
    end: float         # 静音段结束时间（秒）
    duration: float    # 静音段时长（秒）
    adjusted_duration: Optional[float] = None  # 调整后的时长（秒），None 表示未调整


class AudioAnalysisResponse(BaseModel):
    """音频分析响应"""
    file_id: str
    duration: float
    sample_rate: int
    channels: int
    pauses: list[PauseInfo]
    format: str
    noise_floor: float  # 检测到的底噪（dB）
    threshold: float    # 实际使用的检测阈值（dB）


class GenerateRequest(BaseModel):
    """生成音频请求"""
    file_id: str
    pauses: list[dict]  # [{"index": 0, "adjusted_duration": 0.5}, ...]
    noise: Optional[float] = -20.0  # 静音灵敏度，接受 null 时回退到默认值


@app.post("/api/upload")
async def upload_audio(file: UploadFile = File(...)):
    """上传音频文件"""
    if not file.filename:
        raise HTTPException(status_code=400, detail="缺少文件名")

    ext = Path(file.filename).suffix.lower()
    if ext not in ['.mp3', '.wav', '.ogg', '.flac', '.m4a', '.aac', '.wma']:
        raise HTTPException(status_code=400, detail=f"不支持的格式: {ext}")

    file_id = str(uuid.uuid4())[:8]
    save_path = TEMP_DIR / f"{file_id}{ext}"

    content = await file.read()
    if len(content) > MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=413, detail="文件过大，最大支持 50MB")

    with open(save_path, "wb") as f:
        f.write(content)

    return {"file_id": file_id, "filename": file.filename, "size": len(content)}


def _probe_audio(source: Path) -> dict:
    """获取音频基本信息"""
    probe_cmd = [
        FFPROBE, "-v", "error",
        "-show_entries", "format=duration,format_name",
        "-show_entries", "stream=sample_rate,channels",
        "-of", "json", str(source)
    ]
    result = subprocess.run(probe_cmd, capture_output=True, text=True, timeout=30)
    data = json.loads(result.stdout)
    return {
        "duration": float(data.get("format", {}).get("duration", 0)),
        "sample_rate": int(data.get("streams", [{}])[0].get("sample_rate", 0)),
        "channels": int(data.get("streams", [{}])[0].get("channels", 0)),
        "format_name": data.get("format", {}).get("format_name", ""),
    }


def _measure_noise_floor(source: Path) -> float:
    """
    测量音频底噪（dB）。
    使用 volumedetect 得到 mean_volume，底噪 ≈ mean - 12dB。
    """
    cmd = [
        FFMPEG, "-i", str(source),
        "-af", "volumedetect",
        "-f", "null", "-"
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    mean_match = re.search(r"mean_volume:\s*([-\d.]+)", result.stderr)
    if mean_match:
        mean_volume = float(mean_match.group(1))
        return round(mean_volume - 12, 1)
    return -45.0  # 默认值，适用于无法检测的情况


def _detect_silences(source: Path, noise_db: float, min_dur: float = 0.1) -> list[dict]:
    """运行 silencedetect，返回原始静音段列表"""
    cmd = [
        FFMPEG, "-i", str(source),
        "-af", f"silencedetect=noise={noise_db}dB:d={min_dur}",
        "-f", "null", "-"
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    stderr = result.stderr

    silence_starts = re.findall(r"silence_start:\s*([\d.]+)", stderr)
    silence_ends = re.findall(r"silence_end:\s*([\d.]+)\s*\|\s*silence_duration:\s*([\d.]+)", stderr)

    segments = []
    for i, start_str in enumerate(silence_starts):
        start = float(start_str)
        if i < len(silence_ends):
            end = float(silence_ends[i][0])
            duration = float(silence_ends[i][1])
        else:
            end = None
            duration = None
        segments.append({"start": start, "end": end, "duration": duration})

    return segments


def _post_process(raw_segments: list[dict], total_duration: float) -> list[dict]:
    """
    后处理原始静音段：
    1. 填补缺失的 end（延续到音频末尾）
    2. 合并间距 < MERGE_GAP 的相邻静音
    3. 过滤首尾 EDGE_MARGIN 内的停顿
    4. 确保相邻停顿间有至少 SPEECH_MIN 的语音
    """
    # 填补缺失的 end
    segments = []
    for seg in raw_segments:
        if seg["end"] is None:
            seg["end"] = total_duration
            seg["duration"] = total_duration - seg["start"]
        segments.append(seg)

    if not segments:
        return []

    # 合并间距小的相邻静音
    merged = [segments[0].copy()]
    for seg in segments[1:]:
        gap = seg["start"] - merged[-1]["end"]
        if gap < MERGE_GAP:
            # 合并：扩展到当前段的 end
            merged[-1]["end"] = seg["end"]
            merged[-1]["duration"] = merged[-1]["end"] - merged[-1]["start"]
        else:
            merged.append(seg.copy())

    # 过滤首尾停顿 + 确保有足够语音
    result = []
    for seg in merged:
        # 跳过开头/结尾 margin 内的停顿
        if seg["start"] < EDGE_MARGIN or seg["end"] > total_duration - EDGE_MARGIN:
            continue
        # 与前一个停顿之间要有足够语音
        if result and (seg["start"] - result[-1]["end"]) < SPEECH_MIN:
            continue
        result.append(seg)

    return result


def _find_audio(source_id: str) -> Optional[Path]:
    """根据 file_id 查找音频文件"""
    for ext in ['.mp3', '.wav', '.ogg', '.flac', '.m4a', '.aac', '.wma']:
        p = TEMP_DIR / f"{source_id}{ext}"
        if p.exists():
            return p
    return None


def _compute_threshold(noise_floor: float, sensitivity: float) -> float:
    """
    根据底噪和灵敏度计算实际检测阈值。
    sensitivity 范围 -35（保守）到 -10（敏感）。
    offset 范围 3dB 到 15dB，threshold = noise_floor + offset。
    """
    fraction = (sensitivity + 35) / 25.0  # 0.0 ~ 1.0
    offset = 3 + fraction * 12            # 3 ~ 15 dB
    return round(noise_floor + offset, 1)


def analyze_pauses(
    source: Path,
    sensitivity: float = -20.0,
    min_pause_dur: float = 0.1,
) -> tuple[list[PauseInfo], float, float]:
    """
    完整的气口检测流程：测底噪 → 算阈值 → 检测静音 → 后处理
    返回 (pauses, noise_floor, threshold)
    """
    info = _probe_audio(source)
    duration = info["duration"]
    if duration <= 0:
        return [], 0, 0

    noise_floor = _measure_noise_floor(source)
    threshold = _compute_threshold(noise_floor, sensitivity)

    raw = _detect_silences(source, noise_db=threshold, min_dur=min_pause_dur)
    processed = _post_process(raw, duration)

    pauses = []
    for idx, seg in enumerate(processed):
        pauses.append(PauseInfo(
            index=idx,
            start=round(seg["start"], 3),
            end=round(seg["end"], 3),
            duration=round(seg["duration"], 3),
            adjusted_duration=None,
        ))

    return pauses, noise_floor, threshold


@app.post("/api/analyze/{file_id}")
async def analyze_audio(file_id: str, noise: float = -20.0, min_duration: float = 0.1):
    """分析音频，检测句间停顿

    Args:
        file_id: 文件 ID
        noise: 灵敏度（-35 保守 → -10 敏感），默认 -20。
               实际阈值根据音频底噪动态计算。
        min_duration: 最小静音持续时间（秒），默认 0.1
    """
    source = _find_audio(file_id)
    if not source:
        raise HTTPException(status_code=404, detail="文件不存在")

    info = _probe_audio(source)
    pauses, noise_floor, threshold = analyze_pauses(source, sensitivity=noise, min_pause_dur=min_duration)

    return AudioAnalysisResponse(
        file_id=file_id,
        duration=round(info["duration"], 3),
        sample_rate=info["sample_rate"],
        channels=info["channels"],
        pauses=pauses,
        format=info["format_name"],
        noise_floor=noise_floor,
        threshold=threshold,
    )


@app.post("/api/generate")
async def generate_audio(req: GenerateRequest):
    """根据调整后的停顿参数重新生成音频"""
    file_id = req.file_id
    effective_noise = req.noise if req.noise is not None else -20.0

    source = _find_audio(file_id)
    if not source:
        raise HTTPException(status_code=404, detail="源文件不存在")

    # 构建停顿调整映射
    pause_map = {}
    for p in req.pauses:
        if p.get("adjusted_duration") is not None:
            pause_map[p["index"]] = p["adjusted_duration"]

    # 获取总时长 + 底噪
    info = _probe_audio(source)
    total_duration = info["duration"]
    noise_floor = _measure_noise_floor(source)
    threshold = _compute_threshold(noise_floor, effective_noise)

    # 检测并后处理停顿（与 analyze 保持一致）
    raw = _detect_silences(source, noise_db=threshold, min_dur=0.1)
    pauses_info = _post_process(raw, total_duration)
    for idx, seg in enumerate(pauses_info):
        seg["index"] = idx

    if not pauses_info:
        output_path = TEMP_DIR / f"{file_id}_output{source.suffix}"
        shutil.copy(source, output_path)
        return _create_download_response(output_path)

    # 构建语音段 + 停顿段列表
    work_dir = TEMP_DIR / f"work_{file_id}"
    work_dir.mkdir(exist_ok=True)

    segments = []
    last_end = 0.0

    for pi in pauses_info:
        # 语音段
        speech_start = last_end
        speech_end = pi["start"]
        if speech_end - speech_start > 0.01:
            segments.append(("speech", speech_start, speech_end))

        # 停顿段
        new_duration = pause_map.get(pi["index"], pi["duration"])
        if new_duration > 0.001:
            segments.append(("pause", new_duration, None))

        last_end = pi["end"]

    # 最后一段语音
    if total_duration - last_end > 0.01:
        segments.append(("speech", last_end, total_duration))

    # 处理每个段
    parts = []
    for i, seg in enumerate(segments):
        part_path = work_dir / f"part_{i:03d}.wav"

        if seg[0] == "speech":
            start, end = seg[1], seg[2]
            dur = end - start
            cmd = [
                FFMPEG, "-y", "-i", str(source),
                "-ss", str(start),
                "-t", str(dur),
                "-acodec", "pcm_s16le",
                "-ar", "44100",
                "-ac", "2",
                str(part_path)
            ]
            subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            parts.append(part_path)

        else:
            duration = seg[1]
            cmd = [
                FFMPEG, "-y",
                "-f", "lavfi",
                "-i", "anullsrc=r=44100:cl=stereo",
                "-t", str(duration),
                "-acodec", "pcm_s16le",
                str(part_path)
            ]
            subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            parts.append(part_path)

    # concat 拼接
    concat_list_path = work_dir / "concat_list.txt"
    with open(concat_list_path, "w") as f:
        for part in parts:
            f.write(f"file '{part}'\n")

    output_path = TEMP_DIR / f"{file_id}_output.wav"
    concat_cmd = [
        FFMPEG, "-y", "-f", "concat",
        "-safe", "0",
        "-i", str(concat_list_path),
        "-acodec", "pcm_s16le",
        "-ar", "44100",
        "-ac", "2",
        str(output_path)
    ]
    result = subprocess.run(concat_cmd, capture_output=True, text=True, timeout=120)

    if result.returncode != 0:
        raise HTTPException(status_code=500, detail=f"音频处理失败: {result.stderr[:500]}")

    try:
        shutil.rmtree(work_dir)
    except Exception:
        pass

    return _create_download_response(output_path)


def _create_download_response(path: Path):
    """创建下载响应"""
    filename = path.name
    return {
        "download_url": f"/api/download/{filename}",
        "filename": filename,
        "size": path.stat().st_size
    }


@app.get("/api/download/{filename}")
async def download_audio(filename: str):
    """下载处理后的音频"""
    filepath = TEMP_DIR / filename
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(filepath, filename=filename, media_type="audio/wav")


@app.get("/api/waveform/{file_id}")
async def get_waveform(file_id: str):
    """获取音频波形数据"""
    source = _find_audio(file_id)
    if not source:
        raise HTTPException(status_code=404, detail="文件不存在")

    cmd = [
        FFMPEG, "-y", "-i", str(source),
        "-f", "f32le",
        "-acodec", "pcm_f32le",
        "-ar", "44100",
        "-ac", "1",
        "-"
    ]
    result = subprocess.run(cmd, capture_output=True, timeout=60)

    if result.returncode != 0:
        raise HTTPException(status_code=500, detail="无法提取波形数据")

    pcm_data = result.stdout
    num_samples = len(pcm_data) // 4

    samples_per_point = max(1, num_samples // 5000)
    waveform = []
    for i in range(0, num_samples, samples_per_point):
        chunk = pcm_data[i * 4:(i + samples_per_point) * 4]
        if chunk:
            values = struct.unpack(f"<{len(chunk) // 4}f", chunk)
            peak = max(abs(v) for v in values)
            waveform.append(round(peak, 6))

    return {
        "samples": waveform,
        "num_samples": len(waveform),
        "samples_per_point": samples_per_point,
        "sample_rate": 44100
    }


@app.delete("/api/cleanup/{file_id}")
async def cleanup(file_id: str):
    """清理临时文件"""
    deleted = []
    for f in TEMP_DIR.iterdir():
        if f.name.startswith(file_id):
            f.unlink()
            deleted.append(f.name)
    return {"deleted": deleted}


if __name__ == "__main__":
    import signal
    import socket
    import subprocess
    import uvicorn

    def _find_free_port(preferred: int = 8888) -> int:
        """Find free port, killing existing process if needed."""

        if preferred > 0:
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    s.bind(('127.0.0.1', preferred))
                    return preferred
            except OSError:
                # Port occupied — find and kill the process
                try:
                    if os.name == 'nt':  # Windows
                        result = subprocess.run(
                            ['netstat', '-ano'], capture_output=True, text=True
                        )
                        for line in result.stdout.splitlines():
                            if f':{preferred}' in line and 'LISTENING' in line:
                                parts = line.split()
                                pid = parts[-1]
                                subprocess.run(['taskkill', '/F', '/PID', pid], capture_output=True)
                                break
                    else:  # Linux/Mac
                        result = subprocess.run(
                            ['lsof', '-ti', f':{preferred}'], capture_output=True, text=True
                        )
                        if result.stdout.strip():
                            pid = result.stdout.strip()
                            subprocess.run(['kill', '-9', pid], capture_output=True)
                except Exception:
                    pass
                # Try again
                try:
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                        s.bind(('127.0.0.1', preferred))
                        return preferred
                except OSError:
                    pass

        # Fallback: OS-assigned port
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('127.0.0.1', 0))
            return s.getsockname()[1]

    port = _find_free_port(8888)
    print(f"PORT:{port}", flush=True)

    # Graceful shutdown on SIGINT (Ctrl+C)
    server = uvicorn.Server(config=uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))

    def _shutdown(signum=None, frame=None):
        server.should_exit = True

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    import asyncio
    asyncio.run(server.serve())
