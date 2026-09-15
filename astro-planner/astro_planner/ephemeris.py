"""整夜星历与可观测性计算。

输入观测地点、日期与目标表, 沿"地方 12:00 → 次日 12:00"的等间隔
时间网格逐点推算:

1. 本地恒星时 (LST) 与每个目标的时角、方位/高度;
2. 太阳高度 -> 民用/航海/天文暮光界限;
3. 月球站心位置、月相照亮比例、与目标角距;
4. 四类可观测掩码: 天文暗夜、最低高度、山头遮挡、月光回避、赤道仪时角极限;
5. 从合并掩码提取连续可观测窗口, 标记窗口相对过中天的位置(东/西侧)。
"""
from __future__ import annotations

import numpy as np

from .coordinates import (Observer, angular_separation,
                          angle_refraction_b, eq_to_altaz,
                          hour_angle_deg, precess_j2000_to_date)
from .sunmoon import sun_position, moon_position, moon_illuminated_fraction
from .horizon import FLAT_HORIZON, HorizonProfile
from .timeutils import lst_deg, make_night_grid, wrap180
from .targets import Target

__all__ = ["compute_ephemeris", "TWILIGHT_ALT", "default_settings"]

TWILIGHT_ALT = {"civil": -6.0, "nautical": -12.0, "astronomical": -18.0}


def default_settings():
    return {
        "step_seconds": 60,
        "min_alt_global": 20.0,      # 全局最低拍摄高度
        "max_hour_angle": 120.0,     # 赤道仪安全时角极限(度), 双侧
        "mount_flip_hours": 0.05,    # 中天翻转耗时(小时)
        "slew_minutes": 3.0,         # 换目标 slew + 导星稳定时间
        "min_window_minutes": 5.0,   # 窗口最短长度
        "moon_sep_new": 15.0,        # 新月时最低角距(度)
        "moon_sep_full": 60.0,       # 满月时最低角距(度)
        "use_refraction": True,
        "horizon_margin": 1.0,       # 山头安全裕量(度)
    }


# ------------------------------------------------------------- 工具

def _crossing_time(local_hours, y, level, rising):
    """y 曲线穿过 level 的第一个(下降)或最后一个(上升)交叉点, 线性插值。

    :param rising: False=自上而下(黄昏), True=自下而上(黎明)
    """
    above = y > level
    if rising:
        # 黎明: 太阳从低于阈值上升穿过
        cross = np.where(~above[:-1] & above[1:])[0]
    else:
        cross = np.where(above[:-1] & ~above[1:])[0]
    if len(cross) == 0:
        return None
    i = cross[0] if not rising else cross[-1]
    y0, y1 = y[i] - level, y[i + 1] - level
    frac = y0 / (y0 - y1)
    return float(local_hours[i] + frac * (local_hours[i + 1] - local_hours[i]))


def _runs(mask, dt_hours):
    """布尔掩码 -> 连续 True 段 [(i0, i1_inclusive), ...]。"""
    idx = np.flatnonzero(mask)
    if idx.size == 0:
        return []
    breaks = np.flatnonzero(np.diff(idx) > 1)
    starts = np.concatenate([[idx[0]], idx[breaks + 1]])
    ends = np.concatenate([idx[breaks], [idx[-1]]])
    return [(int(a), int(b)) for a, b in zip(starts, ends)
            if (b - a + 1) * dt_hours * 60.0 >= 1]  # 长度过滤交给上层


def _round_list(a, n=2):
    return [round(float(v), n) for v in np.asarray(a)]


# ------------------------------------------------------------- 主计算

def compute_ephemeris(observer: Observer, date_str: str, utc_offset_hours: float,
                      targets: list[Target], settings: dict | None = None,
                      horizon: HorizonProfile | None = None):
    """计算整夜星历与各目标窗口。返回可直接 JSON 序列化的 dict。"""
    st = default_settings()
    if settings:
        st.update(settings)
    horizon = horizon or FLAT_HORIZON
    step = int(st["step_seconds"])
    dt_h = step / 3600.0

    jd, dt_utc, local_h = make_night_grid(date_str, utc_offset_hours, step)

    # ---------------- 太阳 / 暮光
    sun_ra, sun_dec, sun_dist, sun_lon = sun_position(jd)
    sun_lst = lst_deg(jd, observer.lon)
    sun_ha = hour_angle_deg(sun_lst, sun_ra)
    sun_az, sun_alt_geo = eq_to_altaz(sun_ha, sun_dec, observer.lat)
    sun_alt = sun_alt_geo + (angle_refraction_b(sun_alt_geo)
                             if st["use_refraction"] else 0.0)

    dusk = _crossing_time(local_h, sun_alt, TWILIGHT_ALT["astronomical"], False)
    dawn = _crossing_time(local_h, sun_alt, TWILIGHT_ALT["astronomical"], True)
    civil_dusk = _crossing_time(local_h, sun_alt, TWILIGHT_ALT["civil"], False)
    civil_dawn = _crossing_time(local_h, sun_alt, TWILIGHT_ALT["civil"], True)
    # 极昼/极夜退化处理
    full_dark = sun_alt < TWILIGHT_ALT["astronomical"]
    if dusk is None:
        # 极夜: 整夜黑暗 -> 取整段; 极昼: 无暗夜, dusk=dawn(零长度)
        dusk = float(local_h[0]) if full_dark.any() else float(local_h[0])
    if dawn is None:
        dawn = float(local_h[-1]) if full_dark.any() else dusk
    if dawn < dusk:
        dawn = dusk

    # 绘图区间: 民用暮光开始前 20 分钟 ~ 民用暮光结束后 20 分钟
    plot_start = (civil_dusk if civil_dusk is not None else dusk) - 20 / 60.0
    plot_end = (civil_dawn if civil_dawn is not None else dawn) + 20 / 60.0
    plot_start = max(plot_start, float(local_h[0]))
    plot_end = min(plot_end, float(local_h[-1]))
    if plot_end <= plot_start:
        # 极昼等退化情形: 暮光界限不存在, 直接用整段 24h
        plot_start, plot_end = float(local_h[0]), float(local_h[-1])
    i0 = int(np.searchsorted(local_h, plot_start))
    i1 = min(len(local_h) - 1, int(np.searchsorted(local_h, plot_end)))
    sl = slice(i0, i1 + 1)
    chart_hours = _round_list(local_h[sl])

    # ---------------- 月球
    moon = moon_position(jd, observer)
    cos_i, k_moon, age = moon_illuminated_fraction(jd)
    moon_ill_mid = float(np.clip(k_moon[len(k_moon) // 2], 0, 1))

    # ---------------- 目标逐点可观测性
    lst = sun_lst
    t_results = []
    for tgt in targets:
        ra_d, dec_d = precess_j2000_to_date(tgt.ra_deg, tgt.dec_deg, jd)
        ha = hour_angle_deg(lst, ra_d)
        az, alt_geo = eq_to_altaz(ha, dec_d, observer.lat)
        alt_app = alt_geo + (angle_refraction_b(alt_geo)
                             if st["use_refraction"] else 0.0)

        # (a) 天文暗夜
        m_dark = full_dark
        # (b) 高度 (用视高度, 更保守地反映实际最低拍摄角)
        m_alt = alt_app >= max(tgt.min_alt, st["min_alt_global"])
        # (c) 山头遮挡: 几何高度须高于轮廓 + 裕量
        hprof = horizon.horizon_alt(az)
        m_hor = alt_geo > hprof + st["horizon_margin"]
        # (d) 赤道仪时角极限
        m_ha = np.abs(wrap180(ha)) <= st["max_hour_angle"]

        # (e) 月光: 角距需求随照亮比例在 new..full 间线性插值
        sep = angular_separation(ra_d, dec_d, moon["ra"], moon["dec"])
        if tgt.avoid_moon:
            req_sep = (st["moon_sep_new"]
                       + (st["moon_sep_full"] - st["moon_sep_new"])
                       * moon_ill_mid)
            req_sep = min(req_sep, tgt.moon_sep)
            m_moon = sep >= req_sep
        else:
            req_sep = 0.0
            m_moon = np.ones_like(ha, dtype=bool)

        good = m_dark & m_alt & m_hor & m_ha & m_moon

        # 过中天: |HA| 最小点(网格内), 仅在目标升过地平时有意义
        i_transit = int(np.argmin(np.abs(ha)))
        transit_h = float(local_h[i_transit])
        transit_alt = float(alt_app[i_transit])

        # 连续窗口
        wins = []
        min_pts = max(1, int(np.ceil(st["min_window_minutes"] / 60.0 / dt_h)))
        for a, b in _runs(good, dt_h):
            if b - a + 1 < min_pts:
                continue
            ha_win = ha[a:b + 1]
            side = ("east" if np.all(ha_win < 0) else
                    "west" if np.all(ha_win > 0) else "cross")
            # 窗口覆盖 HA=0 (时角由负变正) 才是真正包含过中天
            contains_flip = bool(np.any(ha_win[:-1] * ha_win[1:] <= 0)
                                 and np.any(ha_win[:-1] < 0)
                                 and np.any(ha_win[1:] > 0))
            contains_flip = contains_flip or side == "cross"
            wins.append({
                "start": round(float(local_h[a]), 3),
                "end": round(float(local_h[b]), 3),
                "duration_min": round((b - a + 1) * dt_h * 60.0, 1),
                "side": side,
                "contains_transit": side == "cross" or contains_flip,
                "alt_min": round(float(alt_app[a:b + 1].min()), 1),
                "alt_max": round(float(alt_app[a:b + 1].max()), 1),
                "i0": a - i0, "i1": b - i0,   # 对应裁剪后曲线的索引
            })

        # 首选窗口中心 (排程用): 包含中天的窗口中心, 否则第一个窗口
        if wins:
            cw = next((w for w in wins if w["contains_transit"]), wins[0])
            center_h = (cw["start"] + cw["end"]) / 2.0
        else:
            center_h = transit_h

        t_results.append({
            "target": tgt.to_dict(),
            "alt_geo": _round_list(alt_geo[sl], 2),
            "alt_app": _round_list(alt_app[sl], 2),
            "az": _round_list(az[sl], 2),
            "ha": _round_list(wrap180(ha[sl]), 2),
            "moon_sep": _round_list(sep[sl], 1),
            "mask": [bool(v) for v in good[sl]],
            "windows": wins,
            "transit_h": round(transit_h, 3),
            "transit_alt": round(transit_alt, 1),
            "preferred_center": round(center_h, 3),
            "total_observable_min": round(
                sum(w["duration_min"] for w in wins), 1),
        })

    # ---------------- 汇总
    result = {
        "site": {
            "name": observer.name, "lat": observer.lat,
            "lon": observer.lon, "elev": observer.elev,
        },
        "date": date_str,
        "utc_offset": utc_offset_hours,
        "step_seconds": step,
        "chart": {
            "hours": chart_hours,
            "i0": i0, "i1": i1,
        },
        "sun": {
            "alt": _round_list(sun_alt[sl], 2),
            "dusk_astro": round(dusk, 3),
            "dawn_astro": round(dawn, 3),
            "dusk_civil": round(civil_dusk, 3) if civil_dusk is not None else None,
            "dawn_civil": round(civil_dawn, 3) if civil_dawn is not None else None,
        },
        "moon": {
            "alt": _round_list(moon["alt_app"][sl], 2),
            "az": _round_list(moon["az"][sl], 2),
            "ra_mid": round(float(moon["ra"][len(jd) // 2]), 2),
            "dec_mid": round(float(moon["dec"][len(jd) // 2]), 2),
            "illumination": round(moon_ill_mid, 3),
            "age_days": round(float(age[len(jd) // 2]), 2),
            "up_at_midnight": bool(moon["alt_app"][len(jd) // 2] > 0),
        },
        "horizon": horizon.to_polyline(),
        "targets": t_results,
        "settings": st,
        "warnings": [],
    }
    if moon_ill_mid > 0.8 and result["moon"]["up_at_midnight"]:
        result["warnings"].append(
            f"满月夜(照亮 {moon_ill_mid:.0%}), 月光影响严重, 建议只排窄带目标")
    return result
