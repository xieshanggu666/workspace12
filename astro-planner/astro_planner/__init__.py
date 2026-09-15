"""天文观测计划生成器。

自包含坐标/星历实现, 仅依赖 numpy:
- :mod:`astro_planner.timeutils`    儒略日、恒星时、夜间网格
- :mod:`astro_planner.coordinates`  坐标换算、岁差章动、折射
- :mod:`astro_planner.sunmoon`      太阳/月球位置与月相
- :mod:`astro_planner.horizon`      山头遮挡轮廓
- :mod:`astro_planner.ephemeris`    整夜星历与可观测窗口
- :mod:`astro_planner.scheduler`    拍摄顺序、中天翻转、曝光分组
- :mod:`astro_planner.planner`      门面与地点预设
"""
from .coordinates import Observer, eq_to_altaz, altaz_to_eq, angular_separation
from .ephemeris import compute_ephemeris, default_settings, TWILIGHT_ALT
from .horizon import HorizonProfile, FLAT_HORIZON, mountain_preset
from .planner import generate_plan, SITES, DEFAULT_CATALOG
from .scheduler import build_schedule, fmt_h
from .sunmoon import sun_position, moon_position, moon_illuminated_fraction
from .targets import Target
from .timeutils import date_to_jd, gmst_deg, lst_deg, make_night_grid

__version__ = "0.1.0"
