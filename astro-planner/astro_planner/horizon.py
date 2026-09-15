"""山头(地形)遮挡轮廓。

用一组 ``(方位角度, 遮蔽高度角度)`` 折线描述四周地平线,
方位角自北顺时针。:func:`horizon_alt` 对任意方位角做循环线性插值。

另提供几个常用预设:
- :data:`FLAT_HORIZON`        —— 理想平坦地平线;
- :func:`mountain_preset`     —— 模拟一个东、南方有山脊的观测点。
"""
from __future__ import annotations

import numpy as np

__all__ = ["FLAT_HORIZON", "HorizonProfile", "mountain_preset"]


class HorizonProfile:
    """方位角 -> 遮蔽高度角的循环分段线性函数。"""

    def __init__(self, points):
        """
        :param points: ``[(az, alt), ...]`` 按方位角升序, 角度单位为度。
                       不必包含 0/360, 会自动首尾相接。
        """
        pts = sorted((float(a) % 360.0, float(h)) for a, h in points)
        self.az = np.array([p[0] for p in pts], dtype=float)
        self.alt = np.array([p[1] for p in pts], dtype=float)
        # 闭合: 在 0 和 360 处用首末点的循环值
        first_alt = self.alt[0]
        az_ext = np.concatenate([[0.0], self.az, [360.0]])
        alt_ext = np.concatenate([[self.alt[-1]], self.alt, [first_alt]])
        self._az = az_ext
        self._alt = alt_ext

    def horizon_alt(self, az_deg):
        """返回给定方位角(可数组)处的遮蔽高度角(度)。"""
        az = np.asarray(az_deg, dtype=float) % 360.0
        # np.interp 要求 x 升序, _az 已是升序 (0, az..., 360)
        return np.interp(az, self._az, self._alt)

    def is_clear(self, az_deg, alt_deg, margin=0.0):
        """目标视线是否高过山头 (可加安全裕量, 度)。"""
        return np.asarray(alt_deg) > self.horizon_alt(az_deg) + margin

    def to_polyline(self, step=5.0):
        """供前端绘制: 每 ``step`` 度采样一圈。"""
        azs = np.arange(0.0, 360.0, step)
        return [{"az": float(a), "alt": float(h)}
                for a, h in zip(azs, self.horizon_alt(azs))]


FLAT_HORIZON = HorizonProfile([(0, 0), (360, 0)])


def mountain_preset():
    """示例山脊: 东侧有 8-15° 的山脊, 南向有 12° 山体, 西北开阔。

    大致对应国内常见的山谷观测点(东、南山遮挡, 西北方向开阔)。
    """
    pts = [
        (0, 3), (15, 4), (30, 6), (45, 8), (60, 12), (70, 15),
        (80, 14), (90, 11), (105, 9), (120, 10), (135, 12),
        (150, 13), (165, 12), (180, 10), (195, 8), (210, 6),
        (225, 4), (240, 3), (255, 2), (270, 2), (285, 1),
        (300, 1), (315, 2), (330, 2), (345, 3),
    ]
    return HorizonProfile(pts)
