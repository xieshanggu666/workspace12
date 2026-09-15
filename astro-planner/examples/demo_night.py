"""整夜演示: 打印计划并导出可在前端直接加载的 demo.json。

    python examples/demo_night.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

from astro_planner.planner import generate_plan
from astro_planner.cli import _print_plan


def main():
    plan = generate_plan(
        "兴隆观测站", "2025-10-15", 8.0,
        settings={"step_seconds": 120},
        horizon_key="mountain",
    )
    _print_plan(plan)

    out = Path(__file__).resolve().parent.parent / "demo_plan.json"
    out.write_text(json.dumps(
        plan, ensure_ascii=False, indent=2,
        default=lambda o: o.item() if isinstance(o, (np.floating, np.integer)) else o))
    print(f"\n完整 JSON 已写入 {out} ({out.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
