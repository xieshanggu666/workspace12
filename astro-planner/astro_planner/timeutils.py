"""时间系统:儒略日 / 格林尼治与本地平恒星时。

所有公式参考 Meeus《Astronomical Algorithms》第 7、12 章,
角度统一在 :func:`deg`/:func:`rad` 中换算, 其余模块只使用角度。
"""
from __future__ import annotations

import numpy as np

__all__ = [
    "date_to_jd",
    "datetime_to_jd",
    "jd_to_datetime",
    "gmst_deg",
    "lst_deg",
    "make_night_grid",
    "wrap180",
    "wrap360",
    "day_of_year",
]


def wrap180(x):
    """把角度折叠到 (-180, 180]。"""
    return (np.asarray(x) + 180.0) % 360.0 - 180.0


def wrap360(x):
    """把角度折叠到 [0, 360)。"""
    return np.asarray(x) % 360.0


def date_to_jd(year: int, month: int, day: float, day_fraction: float = 0.0) -> float:
    """公历日期 -> 儒略日, Meeus 公式 7.1。

    ``day`` 可直接含小数(如 1.5 表示 1 日 12h), 也可另传 ``day_fraction``。
    """
    y, m = year, month
    if m <= 2:
        y -= 1
        m += 12
    a = y // 100
    b = 2 - a + a // 4
    d = day + day_fraction
    return int(365.25 * (y + 4716)) + int(30.6001 * (m + 1)) + d + b - 1524.5


def datetime_to_jd(dt) -> np.ndarray | float:
    """接受 datetime / numpy.datetime64, 返回儒略日(可为数组)。"""
    dt64 = np.asarray(dt, dtype="datetime64[s]")
    seconds = (dt64 - np.datetime64("1970-01-01T00:00:00")) / np.timedelta64(1, "s")
    return np.asarray(seconds) / 86400.0 + 2440587.5


def jd_to_datetime(jd):
    """儒略日 -> numpy datetime64(秒)。"""
    seconds = (np.asarray(jd, dtype=float) - 2440587.5) * 86400.0
    return (np.datetime64("1970-01-01T00:00:00")
            + np.round(seconds).astype("timedelta64[s]"))


def day_of_year(year: int, month: int, day: int) -> int:
    """年内序号 (1 月 1 日 = 1), 用于闰日判断。"""
    days = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    leap = (year % 4 == 0 and year % 100 != 0) or year % 400 == 0
    return days[month - 1] + day + (1 if leap and month > 2 else 0)


def _julian_centuries(jd) -> np.ndarray:
    return (np.asarray(jd, dtype=float) - 2451545.0) / 36525.0


def gmst_deg(jd) -> np.ndarray:
    """格林尼治平恒星时 (度), Meeus 公式 12.4(忽略 0.093104*T^3 以下小项)。

    精度在数世纪内约 0.01 角秒, 对观测排程绰绰有余。
    """
    d = np.asarray(jd, dtype=float) - 2451545.0  # 距 J2000 的 UT 天数
    T = d / 36525.0
    # Meeus 12.4 的角度制等价写法 (USNO 常用形式), 无整圈歧义:
    # J2000.0 0h UT 时 GMST=280.46061837°, 每 UT 日增 360.98564737°
    g = (280.46061837 + 360.98564736629 * d
         + 0.000387933 * T**2 - T**3 / 38710000.0)
    return wrap360(g)


def lst_deg(jd, lon_deg) -> np.ndarray:
    """本地恒星时 (度); 东经为正、西经为负。"""
    return wrap360(gmst_deg(jd) + np.asarray(lon_deg))


def make_night_grid(date_str: str, utc_offset_hours: float,
                    step_seconds: int = 60):
    """构造覆盖给定地方日期“那一夜”的时间网格。

    网格从当地中午 12:00 到次日中午 12:00 (共 24h), 保证
    黄昏与黎明都落在同一条连续时间轴上, 便于过中天判定。

    :param date_str: ``YYYY-MM-DD`` (观测夜开始的地方日期)
    :param utc_offset_hours: 地方时区, 如北京 +8
    :param step_seconds: 采样步长(秒)
    :returns: (jd 数组, datetime64 数组, 地方时小数小时数组)
    """
    start_local = np.datetime64(f"{date_str}T12:00:00")
    # 地方 12:00 对应的 UTC
    start_utc = start_local - np.timedelta64(
        int(round(utc_offset_hours * 3600)), "s")
    n = 24 * 3600 // step_seconds + 1
    dt_utc = start_utc + np.arange(n) * np.timedelta64(step_seconds, "s")
    jd = datetime_to_jd(dt_utc)
    local_hours = 12.0 + np.arange(n) * step_seconds / 3600.0
    return jd, dt_utc, local_hours
