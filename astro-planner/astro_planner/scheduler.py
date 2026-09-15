"""拍摄顺序排程。

核心思路 —— 围绕过中天预留整块:
1. 自动模式按"过中天时刻(无中天窗口则取首选窗口中心), 再按优先级"排序;
   手工调序直接采用给定顺序。
2. 对包含中天的窗口, 以过中天为锚点预留 [前置曝光 + 翻转 + 后置曝光]
   整块, 尽量把曝光平分在中天两侧; 整块左边界不能早于当前游标
   (游标 = 已占用时刻, 含换目标 slew)。排不下的张数再向西(中天后)延伸。
3. 单侧窗口从窗口起点(或游标)顺序摆放, 无翻转。
4. 翻转占用 ``mount_flip_hours``; 换目标叠加 slew + 导星稳定时间。
"""
from __future__ import annotations

import numpy as np

__all__ = ["build_schedule", "fmt_h", "auto_order"]


def fmt_h(h):
    """地方小数小时 (可 >24) -> ``HH:MM``。"""
    if h is None:
        return "--:--"
    total = int(round(float(h) * 60.0))
    return f"{total // 60:02d}:{total % 60:02d}"


def auto_order(eph):
    """返回自动模式的目标名字顺序(过中天时刻升序, 同级按优先级)。

    transit_h 以地方 12:00 为 12 计; 白天过中天(落在当晚暗夜之前)的目标,
    其夜间可观测窗口实际在次日凌晨(中天后西落), 需把它的排序锚点
    平移到次日(+24h), 否则会被误排到夜晚开头。
    """
    dusk = eph["sun"]["dusk_astro"]

    def key(item):
        th = item["transit_h"]
        if item["windows"]:
            wins = sorted(item["windows"], key=lambda w: w["start"])
            anchor = wins[0]["start"]
            # 含中天且中天在窗口内 -> 用中天时刻; 否则用首个窗口起点
            if any(w["contains_transit"] and w["start"] <= th <= w["end"]
                   for w in wins):
                anchor = th
        else:
            anchor = item["preferred_center"]
        if anchor < dusk - 1.0:
            anchor += 24.0
        return (anchor, item["target"]["priority"], item["target"]["name"])

    return [x["target"]["name"]
            for x in sorted(eph["targets"], key=key)]


def _earliest_window(tres, cursor, slew_h):
    """cursor(含 slew)之后第一个还能进入的窗口。"""
    earliest = cursor + slew_h
    for w in sorted(tres["windows"], key=lambda w: w["start"]):
        if w["end"] > earliest:
            return w
    return None


def _exposure_entry(name, start, n, exp_h, side):
    return {
        "kind": "exposure", "target": name,
        "start": round(start, 3), "end": round(start + n * exp_h, 3),
        "frames": n, "exposure_s": round(exp_h * 3600),
        "side": side, "start_h": fmt_h(start),
        "end_h": fmt_h(start + n * exp_h),
    }


def _flip_entry(name, start, flip_h, transit_alt):
    return {
        "kind": "flip", "target": name,
        "start": round(start, 3), "end": round(start + flip_h, 3),
        "start_h": fmt_h(start), "end_h": fmt_h(start + flip_h),
        "transit_alt": transit_alt,
        "label": f"{name} 过中天翻转 (中天高度 {transit_alt:.0f}°)",
    }


def _slew_entry(name, cursor, until):
    return {
        "kind": "slew", "target": name,
        "start": round(cursor, 3), "end": round(until, 3),
        "start_h": fmt_h(cursor), "end_h": fmt_h(until),
        "label": f"转向 {name} + 导星校准",
    }


def _plan_crossing(tres, win, cursor, slew_h, flip_h):
    """中天窗口: 构建 [中天前曝光…] [翻转] [中天后曝光…] 连续时间线。

    中天前曝光在 ``tc-flip/2`` 收工(右对齐), 翻转对称跨过中天,
    中天后曝光自 ``tc+flip/2`` 起。中天前连一张都放不下时不做翻转,
    直接中天后纯西侧安排。
    """
    tgt = tres["target"]
    name = tgt["name"]
    exp_h = tgt["exposure_s"] / 3600.0
    needed = tgt["n_frames"]
    tc = tres["transit_h"]

    pre_end = tc - flip_h / 2.0
    post_start = tc + flip_h / 2.0
    enter = max(cursor + slew_h, win["start"])

    # 已越过翻转结束 -> 纯西侧
    if enter >= post_start:
        sub = dict(win)
        sub["start"] = max(win["start"], post_start)
        return _plan_oneside(tres, sub, cursor, slew_h, "west")

    pre_cap = int(max(0.0, pre_end - enter) // exp_h)
    post_cap = int(max(0.0, win["end"] - post_start) // exp_h)

    # 尽量在中天前后平分: 前置先取半数与容量的小值, 其余给后置,
    # 后置塞满后的余量再回填前置
    n_pre = min(pre_cap, (needed + 1) // 2)
    n_post = min(post_cap, needed - n_pre)
    n_pre = min(pre_cap, n_pre + max(0, needed - n_pre - n_post))
    n_pre = min(n_pre, needed)
    n_post = min(n_post, needed - n_pre)
    n_done = n_pre + n_post

    if n_pre == 0:
        sub = dict(win)
        sub["start"] = max(win["start"], post_start)
        return _plan_oneside(tres, sub, cursor, slew_h, "west")

    # 中天前曝光: 理想右对齐到 pre_end, 但不能早于进入时刻;
    # 若进入更晚则按进入时刻重算前置张数, 溢出部分尽量补到中天后
    pre_start = max(enter, pre_end - n_pre * exp_h)
    if pre_start > enter:
        n_pre = min(n_pre, int((pre_end - pre_start) // exp_h))
        n_post = min(post_cap, needed - n_pre)
        n_done = n_pre + n_post
        if n_pre == 0:
            sub = dict(win)
            sub["start"] = max(win["start"], post_start)
            return _plan_oneside(tres, sub, cursor, slew_h, "west")
        pre_start = max(enter, pre_end - n_pre * exp_h)

    entries = []
    entries.append(_exposure_entry(name, pre_start, n_pre, exp_h, "east"))
    entries.append(_flip_entry(name, pre_end, flip_h, tres["transit_alt"]))
    t = post_start
    if n_post > 0:
        entries.append(_exposure_entry(name, t, n_post, exp_h, "west"))
        t += n_post * exp_h

    note = f"时间不足: 完成 {n_done}/{needed} 张" if n_done < needed else None
    return entries, max(cursor, t), n_done, note


def _plan_oneside(tres, win, cursor, slew_h, side=None, deadline=None):
    """单侧窗口(无翻转)顺序摆放。

    deadline 给出必须收尾的时刻(用于给后续中天目标让路)。
    """
    tgt = tres["target"]
    name = tgt["name"]
    exp_h = tgt["exposure_s"] / 3600.0
    enter = max(cursor + slew_h, win["start"])
    if side is None:
        side = "east" if win.get("side") == "east" else "west"
    end_limit = win["end"] if deadline is None else min(win["end"], deadline)
    n = min(int(max(0.0, end_limit - enter) // exp_h), tgt["n_frames"])
    entries = [_exposure_entry(name, enter, n, exp_h, side)] if n > 0 else []
    end = enter + n * exp_h if n > 0 else enter
    note = None
    if n < tgt["n_frames"]:
        if n > 0:
            note = f"时间不足: 完成 {n}/{tgt['n_frames']} 张"
        elif end_limit <= enter:
            note = "为后续中天目标让路, 本目标未获得曝光时间"
        else:
            note = (f"窗口剩余 {60 * max(0.0, end_limit - enter):.0f} 分钟, "
                    f"容不下单张 {tgt['exposure_s']}s 曝光")
    return entries, end, n, note


def build_schedule(eph, order=None):
    """根据 :func:`compute_ephemeris` 的结果排出时间表。

    :param order: 目标名列表; None 自动排序。手工调序时未列入的目标
        按自动顺序追加; 无法安排的目标进入 ``unscheduled``。
    """
    st = eph["settings"]
    slew_h = st["slew_minutes"] / 60.0
    flip_h = st["mount_flip_hours"]

    by_name = {x["target"]["name"]: x for x in eph["targets"]}
    auto = auto_order(eph)
    seq_names = list(order) + [n for n in auto if n not in (order or [])] \
        if order is not None else auto

    cursor = eph["sun"]["dusk_astro"]
    entries = []
    unscheduled = []
    total_frames = {}
    notes = []

    # 预扫: 每个位置之后"下一个含中天目标"的中天时刻。
    # 排在前面的西落单侧目标必须在此之前收工, 给中天前曝光 + 翻转让路。
    next_transit = [None] * len(seq_names)
    nxt = None
    for i in range(len(seq_names) - 1, -1, -1):
        next_transit[i] = nxt
        tres_i = by_name.get(seq_names[i])
        if tres_i and any(w["contains_transit"] for w in tres_i["windows"]):
            nxt = tres_i["transit_h"]

    for pos, name in enumerate(seq_names):
        tres = by_name[name]
        if not tres["windows"]:
            unscheduled.append({"target": name,
                                "reason": _failure_reason(tres, eph)})
            continue
        win = _earliest_window(tres, cursor, slew_h)
        if win is None:
            unscheduled.append({
                "target": name,
                "reason": f"{fmt_h(cursor)} 之后已无可容纳该目标的窗口",
            })
            continue

        if win["contains_transit"] and win["start"] <= tres["transit_h"] <= win["end"]:
            plan_entries, end, n_done, note = _plan_crossing(
                tres, win, cursor, slew_h, flip_h)
        else:
            # 为下一个中天目标保留至少 1 张中天前曝光 + 翻转的裕量
            deadline = None
            if next_transit[pos] is not None and win.get("side") != "east":
                tgt0 = tres["target"]
                reserve = tgt0["exposure_s"] / 3600.0 + 1.5 * flip_h + slew_h
                deadline = next_transit[pos] - reserve
            plan_entries, end, n_done, note = _plan_oneside(
                tres, win, cursor, slew_h, deadline=deadline)

        if n_done == 0:
            # 有窗口但挤不出曝光: 不推进时间, 直接记入未安排
            unscheduled.append({
                "target": name,
                "reason": note or "窗口内无可容纳单张曝光的连续时间",
            })
            continue

        # slew 只占真正换架的 slew_h; 若进入时刻早于首个曝光, 中间是等待
        first_start = plan_entries[0]["start"]
        slew_start = max(cursor, first_start - slew_h)
        entries.append(_slew_entry(name, slew_start, first_start))
        entries.extend(plan_entries)
        total_frames[name] = n_done
        if note:
            notes.append({"target": name, "note": note})
        cursor = max(cursor, end)

    night_end = eph["sun"]["dawn_astro"]
    night_start = eph["sun"]["dusk_astro"]
    used = sum(max(0.0, e["end"] - e["start"]) for e in entries
               if e["kind"] == "exposure")
    night_len = max(0.0, night_end - night_start)

    summary = []
    for name in seq_names:
        t = by_name[name]
        done = total_frames.get(name, 0)
        summary.append({
            "target": name,
            "frames_done": done,
            "frames_wanted": t["target"]["n_frames"],
            "transit_h": t["transit_h"],
            "transit_hhmm": fmt_h(t["transit_h"]),
            "transit_alt": t["transit_alt"],
            "windows_min": t["total_observable_min"],
            "priority": t["target"]["priority"],
            "scheduled": done > 0,
        })

    entries.sort(key=lambda e: (e["start"], 0 if e["kind"] != "slew" else -1))
    return {
        "entries": entries,
        "unscheduled": unscheduled,
        "notes": notes,
        "summary": summary,
        "order": seq_names,
        "auto_order": auto,
        "exposure_hours": round(used, 2),
        "night_hours": round(night_len, 2),
        "utilization": round(used / night_len, 3) if night_len else 0.0,
    }


def _failure_reason(tres, eph):
    tgt = tres["target"]
    alts = np.array(tres["alt_app"]) if tres["alt_app"] else np.array([0.0])
    if alts.max() < max(tgt["min_alt"], eph["settings"]["min_alt_global"]):
        return f"整夜最高仅 {alts.max():.0f}°, 达不到最低拍摄高度"
    seps = np.array(tres["moon_sep"]) if tres["moon_sep"] else np.array([180.0])
    if seps.max() < 30:
        return "整夜与月球角距过小, 月光否决"
    return "受天文暗夜 / 山头遮挡 / 赤道仪时角极限联合限制, 无连续窗口"
