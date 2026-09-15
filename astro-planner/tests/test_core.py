"""核心数值校验: 用 Meeus 书例与已知天文事实做对照。

运行: python -m pytest tests/ -q  (无 pytest 时: python tests/test_core.py)
"""
import numpy as np

from astro_planner.timeutils import date_to_jd, gmst_deg, lst_deg, wrap180
from astro_planner.coordinates import (eq_to_altaz, altaz_to_eq,
                                        angular_separation, precess_j2000_to_date,
                                        Observer)
from astro_planner.sunmoon import sun_position, moon_position, moon_illuminated_fraction
from astro_planner.horizon import mountain_preset
from astro_planner.ephemeris import compute_ephemeris
from astro_planner.scheduler import build_schedule
from astro_planner.targets import DEFAULT_CATALOG


def approx(a, b, tol):
    return abs(float(a) - float(b)) <= tol


def test_julian_date_meeus():
    # Meeus 例 7.a: 1957-10-04 00:00 UT (JD 2436116.31 是 10月4.81日)
    # J2000.0 = 2000-01-01 12:00 UT, 即 Jan 1 日小数 0.5
    assert approx(date_to_jd(2000, 1, 1, 0.5), 2451545.0, 1e-9)
    assert approx(date_to_jd(1999, 1, 1, 0.0), 2451179.5, 1e-9)
    assert approx(date_to_jd(1987, 4, 10, 0.0), 2446895.5, 1e-9)


def test_gmst_j2000():
    # J2000.0 历元 GMST ≈ 280.4606° (18h41m50.5s)
    g = gmst_deg(2451545.0)
    assert approx(g, 280.4606, 0.001), g
    # 恒星时比太阳时每天快约 360.9856°/天
    g2 = gmst_deg(2451546.0)
    daily = (g2 - g + 360.0) % 360.0 + 360.0  # 还原被 wrap360 去掉的一整圈
    assert approx(daily, 360.9856, 0.002)


def test_eq_altaz_cardinal():
    # 赤道上, 春分点过中天时应在天顶; az 退化时不报错
    az, alt = eq_to_altaz(np.array([0.0]), np.array([0.0]), 0.0)
    assert approx(alt[0], 90.0, 1e-6)
    # 北极点, 赤道上的恒星沿地平线, HA=0 时在正南
    az, alt = eq_to_altaz(np.array([0.0]), np.array([0.0]), 90.0 - 1e-9)
    assert approx(alt[0], 1e-9, 1e-5)
    assert approx(az[0], 180.0, 1e-4)
    # 北纬45, 天赤道恒星 H=6h(90°) 在西点附近落下, 高度≈0
    az, alt = eq_to_altaz(np.array([90.0]), np.array([0.0]), 45.0)
    assert approx(alt[0], 0.0, 1e-6)
    assert approx(az[0], 270.0, 1e-6)
    # H=-90° 在东点升起
    az, alt = eq_to_altaz(np.array([-90.0]), np.array([0.0]), 45.0)
    assert approx(az[0], 90.0, 1e-6)


def test_altaz_roundtrip():
    ha = np.array([-37.5, 12.2, 95.0, -120.0])
    dec = np.array([28.0, -5.0, 60.0, 41.0])
    lat = 40.4
    az, alt = eq_to_altaz(ha, dec, lat)
    ha2, dec2 = altaz_to_eq(az, alt, lat)
    assert np.allclose(ha2, ha, atol=1e-8)
    assert np.allclose(dec2, dec, atol=1e-8)


def test_angular_separation():
    assert approx(angular_separation(0, 0, 0, 90), 90.0, 1e-9)
    # 天狼星 ~ (RA 101.287°, Dec -16.716°) 与参宿四 ~ (88.793°, 7.407°)
    d = angular_separation(101.287, -16.716, 88.793, 7.407)
    assert approx(d, 27.1, 0.2), d


def test_precession_polaris():
    # 岁差: J2000 时北天极在小熊座附近, 2000 年某恒星坐标前推 50 年应平滑
    ra, dec = precess_j2000_to_date(37.9545, 89.2641, 2451545.0)
    assert approx(ra, 37.9545, 1e-6) and approx(dec, 89.2641, 1e-6)
    # 岁差 100 年量级 ~1.4°, 单调检查
    ra2, dec2 = precess_j2000_to_date(0.0, 0.0, 2451545.0 + 36525.0)
    assert approx(angular_separation(0.0, 0.0, ra2, dec2), 1.3966, 0.01)


def test_sun_position_meeus():
    # Meeus 例 25.a: 1992-10-13 00:00 TD, 太阳视黄经 199.906°,
    # RA ≈ 198.38°, Dec ≈ -7.785°
    jd = date_to_jd(1992, 10, 13.0)
    ra, dec, dist, lon = sun_position(jd)
    assert approx(lon, 199.906, 0.02), lon
    assert approx(ra, 198.38, 0.03), ra
    assert approx(dec, -7.785, 0.02), dec
    assert approx(dist, 0.9976, 0.001), dist
    # 冬至太阳赤纬约 -23.44°
    jd_dec = date_to_jd(2025, 12, 21.5)
    _, dec2, _, _ = sun_position(jd_dec)
    assert approx(dec2, -23.44, 0.1), dec2


def test_moon_position_meeus():
    # Meeus 例 47.a: 1992-04-12 00:00 TD
    # 黄经 ≈ 133.17°, 黄纬 ≈ -3.23°, 距离 368409 km
    jd = date_to_jd(1992, 4, 12.0)
    m = moon_position(jd)
    assert approx(m["lon"], 133.17, 0.1), m["lon"]
    assert approx(m["lat_ecl"], -3.23, 0.05), m["lat_ecl"]
    assert approx(m["dist_km"], 368409, 200), m["dist_km"]


def test_moon_phase():
    # 2000-01-06 新月, 01-14 上弦, 01-21 满月
    jd = date_to_jd(2000, 1, 7.0)
    _, k, age = moon_illuminated_fraction(jd)
    assert k < 0.05, k
    jd2 = date_to_jd(2000, 1, 21.0)
    _, k2, age2 = moon_illuminated_fraction(jd2)
    assert k2 > 0.97, k2
    jd3 = date_to_jd(2000, 1, 14.0)
    _, k3, _ = moon_illuminated_fraction(jd3)
    assert 0.4 < k3 < 0.62, k3


def test_horizon_profile():
    hp = mountain_preset()
    # 东 70° 山脊高约 15°
    assert approx(hp.horizon_alt(70), 15, 0.01)
    # 插值单调: 300° 附近约 1°
    assert hp.horizon_alt(300) < 2
    # 循环闭合: az=359 与 az=-1 相同
    assert approx(hp.horizon_alt(359.5), hp.horizon_alt(-0.5), 1e-9)
    assert hp.is_clear(70, 20)
    assert not hp.is_clear(70, 5)


def test_ephemeris_and_schedule():
    obs = Observer("测试兴隆", 40.4, 117.6, 900)
    # 2025-10-15 夜: M31(RA~10.7°)秋季可见, M42 凌晨可见
    res = compute_ephemeris(obs, "2025-10-15", 8.0, DEFAULT_CATALOG,
                            horizon=mountain_preset())
    assert res["sun"]["dusk_astro"] is not None
    assert 17 < res["sun"]["dusk_astro"] < 20  # 天文暮光大致在地方 18-20 点
    assert res["sun"]["dawn_astro"] > res["sun"]["dusk_astro"]
    # 至少能找到 M31
    m31 = next(t for t in res["targets"] if t["target"]["name"].startswith("M31"))
    assert m31["total_observable_min"] > 60, m31["total_observable_min"]
    # 中天高度 ≈ 90 - |lat - dec| = 90 - |40.4 - 41.27| ≈ 89°
    assert approx(m31["transit_alt"], 89.1, 2.0), m31["transit_alt"]

    plan = build_schedule(res)
    assert plan["entries"], "应排出至少一个条目"
    kinds = [e["kind"] for e in plan["entries"]]
    assert "flip" in kinds, "秋季 M31 应包含中天翻转"
    # 时间单调
    starts = [e["start"] for e in plan["entries"]]
    assert starts == sorted(starts)
    # 曝光时长为声明值的整数倍
    for e in plan["entries"]:
        if e["kind"] == "exposure":
            dur = e["end"] - e["start"]
            assert abs(dur * 3600 - e["frames"] * e["exposure_s"]) <= 4.0

    # 手工调序: 把 M42 提到第一位后, 它仍应排在可排时间且不报错
    names = [t["target"]["name"] for t in res["targets"]]
    m42 = next(n for n in names if n.startswith("M42"))
    order = [m42] + [n for n in names if n != m42]
    plan2 = build_schedule(res, order=order)
    assert plan2["order"][0] == m42


def test_schedule_invariants():
    """跨多夜/多地点的时序不变量。"""
    from astro_planner.planner import generate_plan
    cases = [("兴隆观测站", "2025-02-28", 8), ("冷湖观测基地", "2025-10-15", 8),
             ("智利阿塔卡马", "2026-06-21", -4), ("兴隆观测站", "2026-09-15", 8)]
    for site, d, tz in cases:
        p = generate_plan(site, d, tz, settings={"step_seconds": 300})
        E = p["plan"]["entries"]
        # 全局时间单调, 无零/负时长
        for i, e in enumerate(E):
            assert e["end"] > e["start"], (site, d, e)
            if i:
                assert e["start"] >= E[i - 1]["start"] - 1e-9, (site, d, E[i - 1], e)
        by = {t["target"]["name"]: t for t in p["targets"]}
        # 翻转严格以过中天为中心, 且其前必须有中天前曝光
        for e in E:
            if e["kind"] == "flip":
                mid = (e["start"] + e["end"]) / 2
                assert abs(mid - by[e["target"]]["transit_h"]) < 1e-6
                assert any(x["kind"] == "exposure" and x["side"] == "east"
                           and x["end"] <= e["start"] + 1e-9
                           for x in E if x["target"] == e["target"])
        # 首个曝光不得早于其 slew 结束
        for name, tt in by.items():
            es = [e for e in E if e["target"] == name]
            ex0 = next((e for e in es if e["kind"] == "exposure"), None)
            sw = next((e for e in es if e["kind"] == "slew"), None)
            if ex0 and sw:
                assert ex0["start"] >= sw["end"] - 1e-6, (site, d, name)
        # 曝光不越暗夜
        for e in E:
            if e["kind"] == "exposure":
                assert p["sun"]["dusk_astro"] - 1e-9 <= e["start"]
                assert e["end"] <= p["sun"]["dawn_astro"] + 1e-9


def test_southern_hemisphere():
    # 阿塔卡马 (南纬 23°): M42 12 月应在天顶北侧过中天, 高度 ~ 90-|23-(-5)|≈72°
    obs = Observer("Atacama", -23.0232, -67.7535, 2400)
    res = compute_ephemeris(obs, "2025-12-20", -4.0,
                            [t for t in DEFAULT_CATALOG if t.name.startswith("M42")])
    m42 = res["targets"][0]
    assert 65 < m42["transit_alt"] < 78, m42["transit_alt"]
    assert m42["total_observable_min"] > 120
    # 方位角合法范围
    assert all(0 <= a < 360 for a in m42["az"])


def test_full_moon_narrowband():
    """满月夜同坐标目标: 避月光者被否决, 窄带(avoid_moon=False)仍可排。

    用 2026-07-29 满月夜, 在当时月球位置附近构造一对合成目标。
    """
    from astro_planner.targets import Target
    from astro_planner.sunmoon import moon_position
    from astro_planner.coordinates import Observer as O
    obs = O("x", 40.4, 117.6, 0)
    # 直接取夜中央月球的 RA/Dec 作为目标坐标(角距 0)
    from astro_planner.timeutils import make_night_grid
    jd, _, _ = make_night_grid("2026-07-29", 8.0, 600)
    mm = moon_position(jd)
    i = len(jd) // 2
    ra, dec = float(mm["ra"][i]), float(mm["dec"][i])
    broadband = Target("合成宽带", ra, dec, 1, 60, 5, 20, True, 30)
    narrow = Target("合成窄带", ra, dec, 1, 60, 5, 20, False, 0)
    res = compute_ephemeris(obs, "2026-07-29", 8.0, [broadband, narrow])
    assert res["moon"]["illumination"] > 0.95
    by = {t["target"]["name"]: t for t in res["targets"]}
    # 宽带目标在月亮上中天附近窗口应为 0(或月距否决); 窄带允许
    assert by["合成宽带"]["total_observable_min"] == 0
    assert by["合成窄带"]["total_observable_min"] > 0


def test_custom_horizon_blocks_target():
    """在目标升起方向堆一堵高墙, 应使其窗口消失; 平坦地平线则恢复。"""
    obs = Observer("x", 40.4, 117.6, 900)
    from astro_planner.horizon import HorizonProfile, FLAT_HORIZON
    # M31 升在东北/北方, 北-东方向 50° 高墙
    wall = HorizonProfile([(0, 50), (90, 50), (180, 50),
                           (270, 0), (360, 50)])
    tgts = [t for t in DEFAULT_CATALOG if t.name.startswith("M31")]
    res_wall = compute_ephemeris(obs, "2025-10-15", 8.0, tgts, horizon=wall)
    res_flat = compute_ephemeris(obs, "2025-10-15", 8.0, tgts, horizon=FLAT_HORIZON)
    assert res_wall["targets"][0]["total_observable_min"] < \
           res_flat["targets"][0]["total_observable_min"]


def test_server_payload():
    """走 server.build_payload 的完整请求路径(含自定义地点)。"""
    from astro_planner.server import build_payload
    out = build_payload({
        "site": {"name": "郊外", "lat": 30.0, "lon": 120.0, "elev": 50},
        "date": "2025-11-01", "utc_offset": 8,
        "settings": {"step_seconds": 300},
    })
    assert out["site"]["lat"] == 30.0
    assert out["plan"]["entries"]
    import json
    json.dumps(out)  # 必须可序列化


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"\n{len(fns)} 项数值校验全部通过")
