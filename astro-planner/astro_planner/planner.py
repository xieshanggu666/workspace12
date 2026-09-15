"""高层门面: 观测地点预设 + 一站式生成计划。"""
from __future__ import annotations

from .coordinates import Observer
from .ephemeris import compute_ephemeris
from .horizon import HorizonProfile, FLAT_HORIZON, mountain_preset
from .scheduler import build_schedule
from .targets import DEFAULT_CATALOG, Target, target_from_dict

__all__ = ["SITES", "generate_plan", "HorizonProfile", "FLAT_HORIZON",
           "mountain_preset", "DEFAULT_CATALOG", "Target"]

# 常用观测点 (经度东正, 纬度北正)
SITES = {
    "兴隆观测站": Observer("国家天文台兴隆观测站", 40.3958, 117.5764, 900),
    "德令哈观测站": Observer("紫金山天文台德令哈站", 37.3739, 97.5633, 3200),
    "冷湖观测基地": Observer("冷湖天文观测基地", 38.6066, 93.8847, 4200),
    "丽江高美古": Observer("丽江高美古观测站", 26.6958, 100.0306, 3200),
    "怀柔观测站": Observer("国家天文台怀柔基地", 40.3139, 116.6169, 60),
    "智利阿塔卡马": Observer("Atacama (示例南半球点)", -23.0232, -67.7535, 2400),
}

_HORIZONS = {
    "flat": FLAT_HORIZON,
    "mountain": mountain_preset(),
}


def generate_plan(site_key_or_observer, date_str: str, utc_offset_hours: float,
                  targets: list[Target | dict] | None = None,
                  settings: dict | None = None,
                  horizon_key: str = "mountain",
                  horizon_points=None,
                  order: list[str] | None = None):
    """生成完整观测计划(星历 + 排程)。

    :param site_key_or_observer: :data:`SITES` 的键或自定义 Observer
    :param date_str: ``YYYY-MM-DD``
    :param utc_offset_hours: 时区(东八区传 8)
    :param targets: 目标列表; None 用内置星表
    :param settings: 覆盖 :func:`~astro_planner.ephemeris.default_settings`
    :param horizon_key: ``"flat"`` / ``"mountain"``
    :param horizon_points: 自定义山头折线 ``[(az, alt), ...]``, 优先于 key
    :param order: 手工指定的目标顺序(名字列表); None 为自动
    """
    if isinstance(site_key_or_observer, Observer):
        obs = site_key_or_observer
    else:
        obs = SITES[str(site_key_or_observer)]

    if horizon_points is not None:
        horizon = HorizonProfile(horizon_points)
    else:
        horizon = _HORIZONS.get(horizon_key, mountain_preset())

    if targets is None:
        tgts = DEFAULT_CATALOG
    else:
        tgts = [t if isinstance(t, Target) else target_from_dict(t)
                for t in targets]

    eph = compute_ephemeris(obs, date_str, utc_offset_hours, tgts,
                            settings, horizon)
    plan = build_schedule(eph, order)
    eph["plan"] = plan
    return eph
