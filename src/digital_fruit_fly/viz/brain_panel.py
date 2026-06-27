"""右侧“脑活动面板”渲染：脑形神经元点云 + 逐神经元实时活动着色。

只依赖 numpy + matplotlib（flygym_env 中均有）。

边界声明：神经元的**空间坐标在 Shiu/FlyWire 公开数据中并不可得**（completeness 表只有
FlyWire ID 与 Completed 两列）。因此这里的点云布局是**确定性合成的、示意性的**——
按神经元索引摆成一个左右对称、带两侧视叶状团块 + 中央脑 + 下方 SEZ 的脑形。
而每个点的**亮度/颜色来自脑模型真实计算出的逐神经元脉冲计数**（``spk_mon.count`` 的采样子集）。
"""

from __future__ import annotations

import numpy as np


def build_brain_layout(n_points: int, seed: int = 0) -> dict[str, np.ndarray]:
    """构建确定性的脑形点云布局。

    返回 dict：``xy`` (N,2)、``region`` (N,)、``base`` (N,) 基线微光强度。
    左右对称：两侧视叶状团块、中央脑团、下方 SEZ 团。
    """
    n_points = max(1, int(n_points))
    rng = np.random.default_rng(seed)

    # 各区域点数占比
    n_optic = int(n_points * 0.46)          # 两侧视叶（左右各半）
    n_sez = int(n_points * 0.10)            # 下方 SEZ
    n_central = n_points - n_optic - n_sez  # 中央脑

    def blob(n, cx, cy, sx, sy, *, bend=0.0):
        # 各向异性高斯团 + 椭圆裁剪，得到有边界的团块
        xs, ys = [], []
        tries = 0
        while len(xs) < n and tries < n * 40:
            tries += 1
            x = rng.normal(0.0, 1.0, size=n)
            y = rng.normal(0.0, 1.0, size=n)
            keep = (x * x + y * y) <= 2.4  # 椭圆边界
            x, y = x[keep], y[keep]
            xs.extend(x.tolist())
            ys.extend(y.tolist())
        x = np.array(xs[:n]); y = np.array(ys[:n])
        if len(x) < n:  # 兜底补齐
            pad = n - len(x)
            x = np.concatenate([x, rng.normal(0, 1, pad)])
            y = np.concatenate([y, rng.normal(0, 1, pad)])
        px = cx + sx * x + bend * (y ** 2)
        py = cy + sy * y
        return np.stack([px, py], axis=1)

    # 视叶：左半生成后镜像到右，保证严格对称
    n_half = n_optic // 2
    left_optic = blob(n_half, -0.66, 0.02, 0.27, 0.40, bend=0.10)
    right_optic = left_optic.copy()
    right_optic[:, 0] *= -1.0
    optic = np.concatenate([left_optic, right_optic], axis=0)
    if optic.shape[0] < n_optic:  # 奇数补一个中点
        optic = np.concatenate([optic, np.array([[0.0, 0.0]])], axis=0)
    optic = optic[:n_optic]

    central = blob(n_central, 0.0, 0.06, 0.40, 0.30)
    central[:, 0] = np.where(  # 让中央团也左右对称
        rng.random(n_central) < 0.5, central[:, 0], -central[:, 0]
    )
    sez = blob(n_sez, 0.0, -0.40, 0.26, 0.13)
    sez[:, 0] = np.where(rng.random(n_sez) < 0.5, sez[:, 0], -sez[:, 0])

    xy = np.concatenate([optic, central, sez], axis=0)[:n_points]
    region = np.concatenate(
        [np.zeros(optic.shape[0]), np.ones(central.shape[0]), np.full(sez.shape[0], 2)]
    )[:n_points].astype(int)
    # 静息亮度：让脑形（含两侧视叶）常显可辨；真实脉冲再把点推向高亮
    base = np.where(region == 0, 0.22, 0.17)[:n_points].astype(float)
    return {"xy": xy.astype(float), "region": region, "base": base}


class BrainPanelRenderer:
    """把一个逐神经元活动向量渲染成一帧脑活动面板 RGB 图（H,W,3 uint8）。"""

    def __init__(
        self,
        *,
        width: int = 600,
        height: int = 480,
        n_points: int = 4000,
        seed: int = 0,
        activity_norm: float = 2.5,
        caption: str = "simultaneous brain emulation",
    ) -> None:
        import matplotlib
        from matplotlib.backends.backend_agg import FigureCanvasAgg
        from matplotlib.figure import Figure

        self.width = int(width)
        self.height = int(height)
        self.seed = int(seed)
        self.activity_norm = float(activity_norm)
        self.caption = caption
        try:
            self._cmap = matplotlib.colormaps["inferno"]
        except Exception:  # pragma: no cover - 老版本 matplotlib
            from matplotlib import cm

            self._cmap = cm.get_cmap("inferno")

        dpi = 100
        self.fig = Figure(figsize=(self.width / dpi, self.height / dpi), dpi=dpi)
        self.canvas = FigureCanvasAgg(self.fig)
        self.fig.patch.set_facecolor("black")
        self.ax = self.fig.add_axes([0.0, 0.0, 1.0, 1.0])
        self.ax.set_facecolor("black")
        self.ax.set_xlim(-1.12, 1.12)
        self.ax.set_ylim(-0.70, 0.62)
        self.ax.set_xticks([])
        self.ax.set_yticks([])
        for spine in self.ax.spines.values():
            spine.set_visible(False)

        self._layout: dict[str, np.ndarray] | None = None
        self._scatter = None
        self._build_layout(n_points)

        # 行为读出高亮标记（位置固定、大小随评分变化）
        self._feed_xy = np.array([[-0.10, -0.34], [0.10, -0.30]])
        self._groom_xy = np.array([[-0.24, -0.14], [0.24, -0.14]])
        self._feed_scatter = self.ax.scatter(
            self._feed_xy[:, 0], self._feed_xy[:, 1], s=1, c="#ff32c8",
            edgecolors="white", linewidths=0.3, zorder=5,
        )
        self._groom_scatter = self.ax.scatter(
            self._groom_xy[:, 0], self._groom_xy[:, 1], s=1, c="#7be0ff",
            edgecolors="white", linewidths=0.3, zorder=5,
        )
        self._hud = self.ax.text(
            -1.06, -0.64, "", color="white", fontsize=9, ha="left", va="bottom",
            family="monospace", zorder=6,
        )
        # 标题放在面板顶部，避免与底部 HUD 文字重叠
        self.ax.text(
            0.0, 0.595, self.caption, color="#e8e8e8", fontsize=11, ha="center",
            va="top", style="italic", zorder=6,
        )

    def _build_layout(self, n_points: int) -> None:
        self._layout = build_brain_layout(n_points, seed=self.seed)
        xy = self._layout["xy"]
        if self._scatter is not None:
            self._scatter.remove()
        self._scatter = self.ax.scatter(
            xy[:, 0], xy[:, 1], s=2.0, c="black", edgecolors="none", zorder=2,
        )

    @property
    def n_points(self) -> int:
        return 0 if self._layout is None else int(self._layout["xy"].shape[0])

    def render(
        self,
        activity,
        *,
        behavior: str = "foraging",
        feeding_score: float = 0.0,
        grooming_score: float = 0.0,
        grooming_hz: float = 0.0,
        active_neuron_count: int = 0,
        total_neuron_count: int = 0,
        window_ms: float = 0.0,
    ) -> np.ndarray:
        act = np.asarray(activity, dtype=float) if activity is not None else np.zeros(0)
        if act.size == 0:
            act = np.zeros(self.n_points)
        if act.size != self.n_points:
            self._build_layout(act.size)

        base = self._layout["base"]
        norm = np.clip(act / max(1e-6, self.activity_norm), 0.0, 1.0)
        # 让活动点更跳：非线性提亮
        glow = np.clip(norm ** 0.6, 0.0, 1.0)
        # 静息亮度（base）让脑形常显；真实脉冲把点推向 inferno 的橙黄高亮
        level = np.clip(base + (1.0 - base) * glow, 0.0, 1.0)
        colors = self._cmap(np.clip(level + 0.25 * glow, 0.0, 1.0))
        # 静息点也保留可见 alpha（脑形可辨），活动点接近不透明
        colors[:, 3] = np.clip(0.45 + 0.55 * glow, 0.0, 1.0)
        sizes = 3.0 + 22.0 * glow

        self._scatter.set_facecolors(colors)
        self._scatter.set_sizes(sizes)

        fs = float(np.clip(feeding_score, 0.0, 1.0))
        gs = float(np.clip(grooming_score, 0.0, 1.0))
        self._feed_scatter.set_sizes([40 + 320 * fs, 40 + 320 * fs])
        self._feed_scatter.set_alpha(0.25 + 0.75 * fs)
        self._groom_scatter.set_sizes([40 + 320 * gs, 40 + 320 * gs])
        self._groom_scatter.set_alpha(0.25 + 0.75 * gs)

        self._hud.set_text(
            f"behavior: {behavior}\n"
            f"active neurons: {active_neuron_count}/{total_neuron_count}\n"
            f"feeding {fs:.2f}  grooming {gs:.2f} ({grooming_hz:.0f}Hz)  win {window_ms:.0f}ms"
        )

        self.canvas.draw()
        buf = np.asarray(self.canvas.buffer_rgba())
        return buf[:, :, :3].copy()
