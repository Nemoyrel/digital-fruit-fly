"""把身体帧与脑活动帧逐帧并排（左身体、右脑），写出合成视频。

依赖 numpy 与 imageio（flygym 的 Renderer 也用 imageio 写视频，故 flygym_env 中可用）。
不依赖系统 ffmpeg：imageio-ffmpeg 自带编码器。
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

import numpy as np


def _to_even(frame: np.ndarray) -> np.ndarray:
    """把帧的高/宽裁成偶数（libx264 要求）。"""
    h, w = frame.shape[:2]
    return frame[: h - (h % 2), : w - (w % 2)]


def _pad_to_height(frame: np.ndarray, height: int) -> np.ndarray:
    h, w = frame.shape[:2]
    if h == height:
        return frame
    if h > height:
        return frame[:height]
    pad = np.zeros((height - h, w, frame.shape[2]), dtype=frame.dtype)
    return np.concatenate([frame, pad], axis=0)


def hstack_frame(body: np.ndarray, brain: np.ndarray, *, gap_px: int = 6) -> np.ndarray:
    """水平拼接一对帧（左身体、右脑），高度对齐后中间留黑缝。"""
    body = np.asarray(body)[:, :, :3]
    brain = np.asarray(brain)[:, :, :3]
    height = max(body.shape[0], brain.shape[0])
    body = _pad_to_height(body, height)
    brain = _pad_to_height(brain, height)
    gap = np.zeros((height, max(0, gap_px), 3), dtype=body.dtype)
    return np.concatenate([body, gap, brain], axis=1)


def write_video(frames: Sequence[np.ndarray], path: Path, *, fps: int = 30) -> bool:
    """用 imageio + libx264 写 mp4；成功返回 True。"""
    if not frames:
        return False
    import imageio.v3 as iio

    even = [_to_even(np.asarray(f)[:, :, :3]) for f in frames]
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    iio.imwrite(path, even, fps=fps, codec="libx264", quality=8)
    return True


def write_gif(frames: Sequence[np.ndarray], path: Path, *, fps: int = 15) -> bool:
    """写 GIF 兜底（无 libx264 时）。"""
    if not frames:
        return False
    import imageio.v3 as iio

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    iio.imwrite(path, [np.asarray(f)[:, :, :3] for f in frames], duration=1.0 / fps, loop=0)
    return True
