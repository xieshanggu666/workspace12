"""球面天文坐标换算 (全部自行实现, 不依赖 ephem/astropy)。

约定:
- 所有外部角度参数一律使用 **度**;
- 方位角 ``az`` 自正北起顺时针量到东, 0=N, 90=E, 180=S, 270=W;
- 高度 ``alt`` 为地平纬度, +90 为天顶;
- 赤经 RA 单位为度 (0..360), 赤纬 Dec 单位为度 (-90..90);
- 纬度 ``lat`` 北正南负, 经度 ``lon`` 东正西负。
"""
from __future__ import annotations

from dataclasses import dataclass
import numpy as np

from .timeutils import lst_deg, wrap180, wrap360

__all__ = [
    "DEG", "RAD", "TWO_PI",
    "Observer",
    "eq_to_altaz",
    "altaz_to_eq",
    "angular_separation",
    "angle_refraction_b",
    "precess_j2000_to_date",
    "obliquity_deg",
    "ecl_to_eq",
    "hour_angle_deg",
]

DEG = np.pi / 180.0
RAD = 1.0 / DEG
TWO_PI = 2.0 * np.pi


@dataclass(frozen=True)
class Observer:
    """观测地点。"""
    name: str
    lat: float          # 地理纬度(度), 北正
    lon: float          # 地理经度(度), 东正
    elev: float = 0.0   # 海拔(米)


def hour_angle_deg(lst, ra):
    """时角 = LST - RA, 折叠到 (-180, 180], 负值在子午圈东侧。"""
    return wrap180(np.asarray(lst) - np.asarray(ra))


def eq_to_altaz(ha_deg, dec_deg, lat_deg):
    """赤道(时角, 赤纬) -> 地平(方位, 高度), 标准球面三角形公式。

    :returns: (az_deg[0..360), alt_deg), 均为 numpy 数组/标量
    """
    ha = np.asarray(ha_deg) * DEG
    dec = np.asarray(dec_deg) * DEG
    phi = np.asarray(lat_deg) * DEG

    sin_alt = np.sin(dec) * np.sin(phi) + np.cos(dec) * np.cos(phi) * np.cos(ha)
    sin_alt = np.clip(sin_alt, -1.0, 1.0)
    alt = np.arcsin(sin_alt)

    # 天顶附近 az 退化, 直接给 0 避免除以零
    cos_alt = np.cos(alt)
    with np.errstate(invalid="ignore", divide="ignore"):
        cos_az = (np.sin(dec) - np.sin(alt) * np.sin(phi)) / (cos_alt * np.cos(phi))
    cos_az = np.where(cos_alt < 1e-9, 1.0, np.clip(cos_az, -1.0, 1.0))
    az_n_from_east = np.arccos(cos_az)
    az = np.where(np.sin(ha) > 0, TWO_PI - az_n_from_east, az_n_from_east)
    return wrap360(az * RAD), alt * RAD


def altaz_to_eq(az_deg, alt_deg, lat_deg):
    """地平 -> 赤道 (ha, dec) 的逆变换, 主要用于测试与上山头坐标。"""
    az = np.asarray(az_deg) * DEG
    alt = np.asarray(alt_deg) * DEG
    phi = np.asarray(lat_deg) * DEG

    sin_dec = np.sin(alt) * np.sin(phi) + np.cos(alt) * np.cos(phi) * np.cos(az)
    sin_dec = np.clip(sin_dec, -1.0, 1.0)
    dec = np.arcsin(sin_dec)
    cos_dec = np.cos(dec)
    with np.errstate(invalid="ignore", divide="ignore"):
        cos_ha = (np.sin(alt) - np.sin(dec) * np.sin(phi)) / (cos_dec * np.cos(phi))
    cos_ha = np.where(cos_dec < 1e-9, 1.0, np.clip(cos_ha, -1.0, 1.0))
    ha = np.arccos(cos_ha)
    # sin(az)>0 为东侧 (az 0..180), 时角为负 (LST-RA < 0, 尚未上中天)
    ha = np.where(np.sin(az) > 0, TWO_PI - ha, ha)
    return wrap180(ha * RAD), dec * RAD


def angular_separation(ra1, dec1, ra2, dec2):
    """两点角距离(度), 适用于任意球面坐标 (ra,dec)/(az,alt)。"""
    a1, d1 = np.asarray(ra1) * DEG, np.asarray(dec1) * DEG
    a2, d2 = np.asarray(ra2) * DEG, np.asarray(dec2) * DEG
    cos_d = np.sin(d1) * np.sin(d2) + np.cos(d1) * np.cos(d2) * np.cos(a1 - a2)
    return np.arccos(np.clip(cos_d, -1.0, 1.0)) * RAD


def angle_refraction_b(alt_true_deg, pressure_mb=1013.0, temp_c=10.0):
    """Bennett 大气折射改正 R(角分): 输入几何高度(度), 返回折射量(度)。

    视高度 = 几何高度 + R。高度低于 -1° 时公式失效, 这里钳到 -1°,
    低高度的山头遮挡判定本身就应保留安全裕量。
    """
    alt = np.maximum(np.asarray(alt_true_deg), -1.0)
    r_arcmin = (1.0 / np.tan((alt + 7.31 / (alt + 4.4)) * DEG)
                * (pressure_mb / 1010.0) * 283.0 / (273.0 + temp_c))
    return r_arcmin / 60.0


def obliquity_deg(jd):
    """黄赤交角(度), Meeus 22.2/22.3, 含章动主项 (精度约 0.01")。"""
    T = (np.asarray(jd, dtype=float) - 2451545.0) / 36525.0
    eps0 = 23.0 + (26.0 + (21.448 - 46.8150 * T - 0.00059 * T**2
                           + 0.001813 * T**3) / 60.0) / 60.0
    # 章动 (Δψ, Δε), Meeus ch.22 简式
    omega = (125.04452 - 1934.136261 * T) * DEG
    Lp = (280.4665 + 36000.7698 * T) * DEG
    Lm = (218.3165 + 481267.8813 * T) * DEG
    d_psi_arcsec = (-17.20 * np.sin(omega) - 1.32 * np.sin(2 * Lp)
                    - 0.23 * np.sin(2 * Lm) + 0.21 * np.sin(2 * omega))
    d_eps_arcsec = (9.20 * np.cos(omega) + 0.57 * np.cos(2 * Lp)
                    + 0.10 * np.cos(2 * Lm) - 0.09 * np.cos(2 * omega))
    return eps0 + d_eps_arcsec / 3600.0, d_psi_arcsec / 3600.0


def ecl_to_eq(lon_deg, lat_deg, jd):
    """黄道坐标 -> 日期真赤道坐标 (ra, dec, 度), 含章动。"""
    eps, dpsi = obliquity_deg(jd)
    lam = (np.asarray(lon_deg) + dpsi) * DEG   # 视黄经
    beta = np.asarray(lat_deg) * DEG
    eps_r = eps * DEG
    ra = np.arctan2(np.sin(lam) * np.cos(eps_r) - np.tan(beta) * np.sin(eps_r),
                    np.cos(lam))
    dec = np.arcsin(np.sin(beta) * np.cos(eps_r)
                    + np.cos(beta) * np.sin(eps_r) * np.sin(lam))
    return wrap360(ra * RAD), dec * RAD


def precess_j2000_to_date(ra2000, dec2000, jd):
    """J2000.0 平赤道坐标岁差到 ``jd`` 日期的平赤道坐标 (度)。

    采用 Meeus 式 21.6 的三参数旋转 (Lieske 岁差), 世纪尺度内 <1"。
    """
    T = (np.asarray(jd, dtype=float) - 2451545.0) / 36525.0
    # Meeus 式 21.6 (IAU 1976), 角秒; T=0 时三个角均为 0
    zeta = (2306.2181 + 1.39656 * T - 0.000139 * T**2) * T / 3600.0
    z = (2306.2181 + 1.39656 * T + 0.000139 * T**2) * T / 3600.0
    theta = (2004.3109 - 0.85330 * T - 0.000217 * T**2) * T / 3600.0

    a = np.asarray(ra2000, dtype=float) * DEG
    d = np.asarray(dec2000, dtype=float) * DEG
    zr, zz, tr = zeta * DEG, z * DEG, theta * DEG

    cos_d = np.cos(d)
    # 旋转: R3(-z) R2(theta) R3(-zeta)
    A = np.sin(a + zr) * cos_d
    B = np.cos(a + zr) * np.cos(tr) * cos_d - np.sin(tr) * np.sin(d)
    C = np.cos(a + zr) * np.sin(tr) * cos_d + np.cos(tr) * np.sin(d)
    ra = np.arctan2(A, B) + zz
    dec = np.arcsin(np.clip(C, -1.0, 1.0))
    return wrap360(ra * RAD), dec * RAD
