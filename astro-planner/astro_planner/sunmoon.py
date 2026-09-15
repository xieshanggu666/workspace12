"""太阳与月球视位置。

- 太阳: Meeus《Astronomical Algorithms》第 25 章低精度历表, 精度 ~0.01°;
- 月球: 第 47 章简表 (Table 47.A/B/C 截取主要周期项),
  黄经/黄纬误差约 0.01-0.03°, 月距误差约 100 km 量级,
  对"避开月光"这类排程需求完全足够。

输出均为 **日期真赤道/真黄道坐标**, 即已含岁差与章动主项。
"""
from __future__ import annotations

import numpy as np

from .coordinates import DEG, RAD, ecl_to_eq
from .timeutils import wrap360

__all__ = ["sun_position", "moon_position", "moon_illuminated_fraction"]


# ---------------------------------------------------------------- 太阳

def sun_position(jd):
    """太阳视位置。

    :returns: (ra_deg, dec_deg, dist_au, apparent_lon_deg)
    """
    T = (np.asarray(jd, dtype=float) - 2451545.0) / 36525.0
    L0 = wrap360(280.46646 + 36000.76983 * T + 0.0003032 * T**2)
    M = wrap360(357.52911 + 35999.05029 * T - 0.0001537 * T**2)
    e = 0.016708634 - 0.000042037 * T - 0.0000001267 * T**2

    Mr = M * DEG
    C = ((1.914602 - 0.004817 * T - 0.000014 * T**2) * np.sin(Mr)
         + (0.019993 - 0.000101 * T) * np.sin(2 * Mr)
         + 0.000289 * np.sin(3 * Mr))
    true_lon = (L0 + C) % 360.0
    omega = (125.04 - 1934.136 * T) * DEG
    app_lon = true_lon - 0.00569 - 0.00478 * np.sin(omega)
    v = M + C
    R = 1.000001018 * (1.0 - e**2) / (1.0 + e * np.cos(v * DEG))
    ra, dec = ecl_to_eq(app_lon, np.zeros_like(app_lon), jd)
    return ra, dec, R, app_lon


# ---------------------------------------------------------------- 月球

# Meeus Table 47.A: Σl 的周期项 (D, M, M', F, 系数单位 1e-6 度)
_L_TERMS = [
    (0, 0, 1, 0, 6288774),
    (2, 0, -1, 0, 1274027),
    (2, 0, 0, 0, 658314),
    (0, 0, 2, 0, 213618),
    (0, 1, 0, 0, -185116),
    (0, 0, 0, 2, -114332),
    (2, 0, -2, 0, 58793),
    (2, -1, -1, 0, 57066),
    (2, 0, 1, 0, 53322),
    (2, -1, 0, 0, 45758),
    (0, 1, -1, 0, -40923),
    (1, 0, 0, 0, -34720),
    (0, 1, 1, 0, -30383),
    (2, 0, 0, -2, 15327),
    (0, 0, 1, 2, -12528),
    (0, 0, 1, -2, 10980),
    (4, 0, -1, 0, 10675),
    (0, 0, 3, 0, 10034),
    (4, 0, -2, 0, 8548),
    (2, 1, -1, 0, -7888),
    (2, 1, 0, 0, -6766),
    (0, 2, -1, 0, -5163),
    (2, -1, 1, 0, 4987),
    (2, 0, 2, 0, 4036),
    (4, 0, 0, 0, 3994),
    (2, 0, -3, 0, 3861),
    (2, 0, -1, 2, 3665),
    (2, -1, -2, 0, 2695),
    (-2, 0, 1, 0, -2602),
    (1, 1, 0, 0, -2390),
    (1, 0, 1, 0, -2322),
    (2, -2, 0, 0, 2236),
    (0, 1, -2, 0, 2120),
    (2, 0, 1, -2, -2069),
    (0, 2, 0, 0, 2048),
    (0, 2, 1, 0, -1773),
    (2, -2, -1, 0, 1595),
    (4, -1, -1, 0, 1215),
    (0, 1, 2, 0, -1110),
]

# Meeus Table 47.B: Σb (D, M, M', F, 系数 1e-6 度)
_B_TERMS = [
    (0, 0, 0, 1, 5128122),
    (0, 0, 1, 1, 280602),
    (0, 0, 1, -1, 277693),
    (2, 0, 0, -1, 173237),
    (2, 0, -1, 1, 55413),
    (2, 0, -1, -1, 46271),
    (2, 0, 0, 1, 32573),
    (0, 0, 2, 1, 17198),
    (2, 0, 1, -1, 9266),
    (0, 0, 2, -1, 8822),
    (-2, 0, 0, 1, 8216),
    (2, 0, -2, -1, 4324),
    (2, 0, 1, 1, 4200),
    (2, 1, 0, -1, -3359),
    (2, -1, -1, 1, 2463),
    (2, -1, 0, 1, 2211),
    (2, -1, -1, -1, 2065),
    (0, 1, -1, -1, -1870),
    (4, 0, -1, -1, 1828),
    (0, 1, 0, 1, -1794),
]

# Meeus Table 47.C: Σr 距离项 (D, M, M', F, 系数单位 1e-3 km)
_R_TERMS = [
    (0, 0, 1, 0, -20905355),
    (2, 0, -1, 0, -3699111),
    (2, 0, 0, 0, -2955968),
    (0, 0, 2, 0, -569925),
    (0, 1, 0, 0, 48888),
    (0, 0, 0, 2, -31490),
    (2, 0, -2, 0, 246158),
    (2, -1, -1, 0, -152138),
    (2, 0, 1, 0, -170733),
    (2, -1, 0, 0, -204586),
    (0, 1, -1, 0, -129620),
    (1, 0, 0, 0, 108743),
    (0, 1, 1, 0, 104755),
    (2, 0, 0, -2, 79661),
    (0, 0, 1, 2, -34782),
    (0, 0, 1, -2, -23210),
    (4, 0, -1, 0, -21636),
    (2, 1, -1, 0, 24208),
    (2, 1, 0, 0, 30824),
    (0, 2, -1, 0, -8379),
    (4, 0, -2, 0, -16675),
    (4, 0, 0, 0, -12831),
    (0, 2, 0, 0, -10445),
    (2, 0, 2, 0, -11650),
    (2, 0, -3, 0, 14403),
]

# 地球扁率 (WGS84)
_FLAT = 1.0 / 298.257223563
_EARTH_R_KM = 6378.137  # 赤道半径(km)


def _moon_angles(jd):
    T = (np.asarray(jd, dtype=float) - 2451545.0) / 36525.0
    Lp = wrap360(218.3164477 + (481267.88123421 + (-0.0015786 + (1.0 / 538841.0
                    - T / 65194000.0) * T) * T) * T)
    D = wrap360(297.8501921 + (445267.1114034 + (-0.0018819 + (1.0 / 545868.0
                    - T / 113065000.0) * T) * T) * T)
    M = wrap360(357.5291092 + (35999.0502909 + (-0.0001536 + 1.0 / 24490000.0 * T) * T) * T)
    Mp = wrap360(134.9633964 + (477198.8675055 + (0.0087414 + (1.0 / 69699.0
                    - T / 14712000.0) * T) * T) * T)
    F = wrap360(93.2720950 + (483202.0175233 + (-0.0036539 + (-1.0 / 3526000.0
                    + T / 863310000.0) * T) * T) * T)
    return T, Lp, D, M, Mp, F


def moon_position(jd, observer=None):
    """月球(视)位置。

    :param observer: 提供 :class:`~astro_planner.coordinates.Observer` 时,
        额外按视差修正高度与方位 (站心坐标), 精度对排程足够;
        不提供则返回地心赤经赤纬。
    :returns: dict: ra, dec(度), dist_km, parallax_deg,
        以及站心 alt_geo/alt_app/az (若给出 observer)
    """
    T, Lp, D, M, Mp, F = _moon_angles(jd)

    # 金星 V (261.22 + 212.77*T) 等行星项省略 (幅度 < 0.004°)
    a1 = (119.75 + 131.849 * T) * DEG
    a2 = (53.09 + 479264.290 * T) * DEG
    a3 = (313.45 + 481266.484 * T) * DEG
    E = 1.0 - 0.002516 * T - 0.0000074 * T**2

    def sum_e(terms, trig):
        """周期项求和。黄经/黄纬表用 sin, 距离表用 cos (Meeus ch.47)。"""
        acc = np.zeros_like(D, dtype=float)
        Dr, Mr, Mpr, Fr = D * DEG, M * DEG, Mp * DEG, F * DEG
        for d, m, mp, f, coef in terms:
            val = coef * trig(d * Dr + m * Mr + mp * Mpr + f * Fr)
            # M (太阳平近点) 的幂次对应 E 因子
            acc += val * E ** abs(m)
        return acc

    sum_l = sum_e(_L_TERMS, np.sin) / 1.0e6
    sum_b = sum_e(_B_TERMS, np.sin) / 1.0e6
    dist_km = 385000.56 + sum_e(_R_TERMS, np.cos) / 1.0e3

    lon = Lp + sum_l + (3958.0 / 1.0e6) * np.sin(a1) \
        + (1962.0 / 1.0e6) * np.sin(Lp * DEG - F * DEG) \
        + (318.0 / 1.0e6) * np.sin(a2)
    lat = sum_b + (-2235.0 / 1.0e6) * np.sin(Lp * DEG) \
        + (382.0 / 1.0e6) * np.sin(a3) \
        + (175.0 / 1.0e6) * np.sin((a1 - F * DEG)) \
        + (175.0 / 1.0e6) * np.sin((a1 + F * DEG)) \
        + (127.0 / 1.0e6) * np.sin((Lp * DEG - Mp * DEG)) \
        - (115.0 / 1.0e6) * np.sin((Lp * DEG + Mp * DEG))

    from .timeutils import lst_deg
    from .coordinates import (eq_to_altaz, hour_angle_deg,
                              angle_refraction_b)
    ra_geo, dec_geo = ecl_to_eq(lon, lat, jd)

    out = {
        "ra": ra_geo, "dec": dec_geo, "lon": lon, "lat_ecl": lat,
        "dist_km": dist_km,
        "parallax_deg": np.degrees(np.arcsin(_EARTH_R_KM / dist_km)),
    }

    if observer is not None:
        phi = observer.lat * DEG
        u = np.arctan((1.0 - _FLAT) * np.tan(phi))
        rho_sin_phi = (1.0 - _FLAT) * np.sin(u) \
            + observer.elev / 6378137.0 * np.sin(phi)
        rho_cos_phi = np.cos(u) + observer.elev / 6378137.0 * np.cos(phi)

        lst = lst_deg(jd, observer.lon)
        ha = hour_angle_deg(lst, ra_geo) * DEG
        dec = dec_geo * DEG
        p = out["parallax_deg"] * DEG

        # Meeus 40.2 三角视差 (站心), 直接解算站心赤经赤纬
        d_ra = np.arctan2(-rho_cos_phi * np.sin(p) * np.sin(ha),
                          np.cos(dec) - rho_cos_phi * np.sin(p) * np.cos(ha))
        ra_topo = (ra_geo * DEG + d_ra) * RAD
        dec_topo_num = (np.sin(dec) - rho_sin_phi * np.sin(p))
        dec_topo_den = np.sqrt(
            (np.cos(dec) * np.sin(ha))**2
            + (np.cos(dec) * np.cos(ha) - rho_cos_phi * np.sin(p))**2)
        dec_topo = np.arctan2(dec_topo_num, dec_topo_den) * RAD

        ha_topo = hour_angle_deg(lst, ra_topo)
        az, alt_geo = eq_to_altaz(ha_topo, dec_topo, observer.lat)
        alt_app = alt_geo + angle_refraction_b(alt_geo)
        out.update(ra_topo=ra_topo, dec_topo=dec_topo,
                   alt_geo=alt_geo, alt_app=alt_app, az=az)
    return out


def moon_illuminated_fraction(jd):
    """月相: 返回 (相位角 i 的余弦, 照亮比例 k, 月龄近似天)。

    相位角 i 即日-月-地夹角; k=0 新月, k=1 满月。
    月龄由日月平黄经差除以平均会合运动 (12.190°/天) 估算, 误差 < 0.3 天。
    """
    from .coordinates import angular_separation
    sun_ra, sun_dec, sun_dist, sun_lon = sun_position(jd)
    m = moon_position(jd)
    moon_dist_au = m["dist_km"] / 149597870.7
    psi = angular_separation(sun_ra, sun_dec, m["ra"], m["dec"]) * DEG
    # 日(S)-地(T)-月(M) 三角形: ST=R(太阳距离), TM=Δ, ∠STM=ψ。
    # SM = d; 相位角 i 位于月球 (∠SMT), 由余弦定理:
    #   cos i = (d² + Δ² - R²) / (2·d·Δ),  k = (1+cos i)/2
    # 新月 ψ≈0  -> k≈0; 满月 ψ≈180 -> k≈1。
    d = np.hypot(moon_dist_au * np.sin(psi),
                 sun_dist - moon_dist_au * np.cos(psi))
    cos_i = np.clip((d**2 + moon_dist_au**2 - sun_dist**2)
                    / (2.0 * d * moon_dist_au), -1.0, 1.0)
    k = (1.0 + cos_i) / 2.0

    T = (np.asarray(jd, dtype=float) - 2451545.0) / 36525.0
    moon_lp = wrap360(218.316 + 481267.8813 * T)
    sun_l0 = wrap360(280.466 + 36000.77 * T)
    elong = (moon_lp - sun_l0) % 360.0
    age = elong / 12.190749
    return cos_i, k, age
