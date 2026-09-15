"""观测目标数据模型与内置星表 (J2000 历元)。

星表选择覆盖不同赤经/赤纬的常用深空目标, 便于任何季节都有可排目标。
坐标取自 SIMBAD/常用星图, 精度到 0.1° 完全满足排程需要。
"""
from __future__ import annotations

from dataclasses import dataclass, asdict, field

__all__ = ["Target", "DEFAULT_CATALOG", "target_from_dict"]


@dataclass
class Target:
    name: str
    ra_deg: float          # J2000 赤经(度)
    dec_deg: float         # J2000 赤纬(度)
    priority: int = 3      # 1=最高, 5=最低
    exposure_s: float = 600.0   # 单张曝光时长(秒)
    n_frames: int = 12     # 计划张数
    min_alt: float = 30.0  # 该目标最低拍摄高度(度)
    avoid_moon: bool = True     # 是否受月光影响 (窄带目标可关)
    moon_sep: float = 60.0      # 要求的最小月心角距(度, 满月时)
    magnitude: float | None = None
    note: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _hms(h, m, s=0.0):
    return (h + m / 60.0 + s / 3600.0) * 15.0


def _dms(sign, d, m, s=0.0):
    return sign * (d + m / 60.0 + s / 3600.0)


DEFAULT_CATALOG = [
    Target("M31 仙女座大星系", _hms(0, 42, 44.3), _dms(+1, 41, 16),
           1, 300, 20, 35, True, 55, 3.4, "秋季天区, 需避月光"),
    Target("M42 猎户座大星云", _hms(5, 35, 17.3), _dms(-1, 5, 23),
           1, 120, 30, 30, True, 60, 4.0, "冬季明珠, Hα 丰富"),
    Target("M45 昴星团", _hms(3, 47, 24.0), _dms(+1, 24, 2),
           2, 180, 20, 35, True, 70, 1.6, "反射星云, 极怕月光"),
    Target("M81 波德星系", _hms(9, 55, 33.2), _dms(+1, 69, 4),
           2, 300, 16, 35, True, 55, 6.9, "高赤纬, 拱极目标"),
    Target("M51 涡状星系", _hms(13, 29, 52.4), _dms(+1, 47, 12),
           2, 300, 18, 40, True, 55, 8.4, "春季星系"),
    Target("M13 武仙座大星团", _hms(16, 41, 41.4), _dms(+1, 36, 28),
           2, 60, 40, 30, False, 30, 5.8, "球状星团, 较耐月光"),
    Target("M57 指环星云", _hms(18, 53, 35.1), _dms(+1, 33, 2),
           3, 180, 30, 35, True, 50, 8.8, "行星状星云"),
    Target("M27 哑铃星云", _hms(19, 59, 36.4), _dms(+1, 22, 43),
           2, 240, 20, 35, False, 40, 7.5, "夏季, 可窄带"),
    Target("M16 鹰状星云(创生之柱)", _hms(18, 18, 48.0), _dms(-1, 13, 49),
           2, 600, 12, 30, False, 30, 6.0, "Hα/SHO 窄带首选"),
    Target("M17 欧米茄星云", _hms(18, 20, 26.0), _dms(-1, 16, 11),
           3, 300, 16, 30, False, 30, 6.0, "与 M16 同片天区"),
    Target("M20 三叶星云", _hms(18, 2, 23.0), _dms(-1, 23, 2),
           3, 180, 24, 30, True, 50, 6.3, "发射+反射混合, 怕光"),
    Target("NGC7000 北美星云", _hms(20, 59, 18.0), _dms(+1, 44, 32),
           2, 300, 20, 30, False, 25, 4.0, "大面积 Hα, 窄带不怕满月"),
    Target("IC1396 象鼻星云", _hms(21, 39, 6.0), _dms(+1, 57, 30),
           3, 600, 10, 30, False, 25, 3.5, "窄带目标"),
    Target("M33 三角座星系", _hms(1, 33, 50.9), _dms(+1, 30, 39),
           2, 300, 18, 40, True, 70, 5.7, "表面亮度极低, 必须暗夜"),
    Target("NGC869/884 双星团", _hms(2, 20, 0.0), _dms(+1, 57, 8),
           3, 90, 30, 25, True, 50, 4.3, "疏散星团, 秋季"),
    Target("M3 球状星团", _hms(13, 42, 11.6), _dms(+1, 28, 23),
           4, 120, 30, 30, False, 30, 6.2, "北天春季球状星团"),
]


def target_from_dict(d: dict) -> Target:
    known = Target.__dataclass_fields__
    return Target(**{k: v for k, v in d.items() if k in known})
