"""命令行: 直接生成并打印夜间观测计划。

用法::

    python -m astro_planner.cli --site 兴隆观测站 --date 2025-10-15 --tz 8
    python -m astro_planner.cli --lat 30 --lon 120 --date 2025-12-01 --json
"""
from __future__ import annotations

import argparse
import json
import sys

import numpy as np

from .planner import SITES, generate_plan, DEFAULT_CATALOG
from .scheduler import fmt_h


def _print_plan(plan):
    s, m = plan["site"], plan["moon"]
    print("=" * 72)
    print(f"观测点: {s['name']}  ({s['lat']:+.4f}°, {s['lon']:+.4f}°, "
          f"海拔 {s['elev']:.0f} m)")
    print(f"日期  : {plan['date']} 夜 (UTC{plan['utc_offset']:+.0f})")
    print(f"暗夜  : 天文暮光 {fmt_h(plan['sun']['dusk_astro'])} → "
          f"{fmt_h(plan['sun']['dawn_astro'])}  "
          f"(民用 {fmt_h(plan['sun']['dusk_civil'])} / "
          f"{fmt_h(plan['sun']['dawn_civil'])})")
    phase = {0.9: "满月附近", 0.6: "凸月", 0.4: "弦月", 0.1: "新月附近"}
    tag = next((v for k, v in phase.items() if m["illumination"] >= k), "极细月牙")
    print(f"月球  : 照亮 {m['illumination']:.0%} ({tag}), 月龄 {m['age_days']:.1f} 天, "
          f"半夜{'在地平线上' if m['up_at_midnight'] else '已落下'}")
    print("-" * 72)
    for e in plan["plan"]["entries"]:
        if e["kind"] == "slew":
            print(f"  {e['start_h']}–{e['end_h']}  ◇ {e['label']}")
        elif e["kind"] == "flip":
            print(f"  {e['start_h']}–{e['end_h']}  ⟲ 中天翻转 "
                  f"[{e['target']}] 中天高度 {e['transit_alt']:.0f}°")
        else:
            side = {"east": "中天前·东侧", "west": "中天后·西侧"}.get(e["side"], "")
            print(f"  {e['start_h']}–{e['end_h']}  ● {e['target']:<22} "
                  f"{e['frames']:>2}×{e['exposure_s']}s ({side})")
    print("-" * 72)
    if plan["plan"]["notes"]:
        for n in plan["plan"]["notes"]:
            print(f"  ⚠ {n['target']}: {n['note']}")
    if plan["plan"]["unscheduled"]:
        print("  未能安排:")
        for u in plan["plan"]["unscheduled"]:
            print(f"    - {u['target']}: {u['reason']}")
    for w in plan.get("warnings", []):
        print(f"  ☾ {w}")
    p = plan["plan"]
    print(f"曝光总时长 {p['exposure_hours']:.2f} h / 暗夜 {p['night_hours']:.2f} h, "
          f"利用率 {p['utilization']:.0%}")
    print("=" * 72)


def main(argv=None):
    ap = argparse.ArgumentParser(description="天文观测计划生成器")
    ap.add_argument("--site", choices=list(SITES), help="预设观测点")
    ap.add_argument("--lat", type=float, help="自定义纬度(度, 北正)")
    ap.add_argument("--lon", type=float, help="自定义经度(度, 东正)")
    ap.add_argument("--elev", type=float, default=0.0, help="海拔(米)")
    ap.add_argument("--date", required=True, help="观测夜日期 YYYY-MM-DD")
    ap.add_argument("--tz", type=float, default=8.0, help="时区(小时)")
    ap.add_argument("--horizon", choices=["flat", "mountain"], default="mountain")
    ap.add_argument("--min-alt", type=float, help="全局最低拍摄高度(度)")
    ap.add_argument("--step", type=int, default=60, help="时间网格步长(秒)")
    ap.add_argument("--json", action="store_true", help="输出完整 JSON")
    args = ap.parse_args(argv)

    if args.lat is not None and args.lon is not None:
        from .coordinates import Observer
        site = Observer("自定义观测点", args.lat, args.lon, args.elev)
    elif args.site:
        site = args.site
    else:
        ap.error("请用 --site 选择预设, 或用 --lat/--lon 指定自定义位置")

    settings = {"step_seconds": args.step}
    if args.min_alt is not None:
        settings["min_alt_global"] = args.min_alt

    plan = generate_plan(site, args.date, args.tz, DEFAULT_CATALOG,
                         settings=settings, horizon_key=args.horizon)
    if args.json:
        json.dump(plan, sys.stdout, ensure_ascii=False, indent=2,
                  default=lambda o: o.item() if isinstance(o, (np.floating, np.integer)) else o)
        print()
    else:
        _print_plan(plan)


if __name__ == "__main__":
    main()
