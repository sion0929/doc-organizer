#!/usr/bin/env python3
"""PX4 ulog → PlotJuggler 레이아웃 만들기 + 문제 구간 찾기.

시험일지에 붙은 ulog에서 문제(진동·추종 불량 등)가 가장 심한 구간을 찾아,
그 구간을 확대한 PlotJuggler 레이아웃(XML)을 만들고 필요하면 바로 연다.

사용법:
    python3 pj_layout.py 로그.ulg --out 레이아웃.xml [--axis roll|pitch|yaw|all] [--open]
    python3 pj_layout.py --check          # 필요한 도구가 있는지 확인만

표준출력: JSON 요약 (비행 구간, 문제 구간, 수치). 시험일지 "분석"에 쓴다.
필요: pyulog, numpy. --open 에는 PlotJuggler.
"""
import argparse
import glob
import json
import os
import shutil
import subprocess
import sys
from xml.sax.saxutils import escape

COLORS = ["#1f77b4", "#d62728", "#1ac938", "#ff7f0e", "#f14cc1", "#9467bd", "#17becf", "#bcbd22"]
AXES = {"roll": 0, "pitch": 1, "yaw": 2}
AXIS_KO = {"roll": "롤", "pitch": "피치", "yaw": "요"}
RAD2DEG = 57.29577951308232


def find_plotjuggler():
    p = shutil.which("plotjuggler")
    if p:
        return p
    hits = sorted(glob.glob("/opt/ros/*/lib/plotjuggler/plotjuggler"))
    return hits[-1] if hits else None


def check_tools():
    missing = []
    try:
        import pyulog  # noqa: F401
    except ImportError:
        missing.append("pyulog")
    try:
        import numpy  # noqa: F401
    except ImportError:
        missing.append("numpy")
    if not find_plotjuggler():
        missing.append("plotjuggler")
    return missing


def pj_field(name):
    """pyulog 필드 이름 → PlotJuggler 이름. control[0] → control.00"""
    out, i = "", 0
    while i < len(name):
        if name[i] == "[":
            j = name.index("]", i)
            out += ".%02d" % int(name[i + 1:j])
            i = j + 1
        else:
            out += name[i]
            i += 1
    return out


class Log:
    def __init__(self, path):
        from pyulog import ULog
        import numpy as np
        self.np = np
        self.u = ULog(path)
        counts = {}
        for d in self.u.data_list:
            counts[d.name] = counts.get(d.name, 0) + 1
        self.multi = {k for k, v in counts.items() if v > 1}
        firsts = [d.data["timestamp"][d.data["timestamp"] > 0][0] for d in self.u.data_list
                  if len(d.data["timestamp"]) and (d.data["timestamp"] > 0).any()]
        self.t0 = min(firsts) if firsts else self.u.start_timestamp  # PlotJuggler 상대 시간 기준
        self.duration = (self.u.last_timestamp - self.t0) / 1e6

    def topic(self, name, multi_id=0):
        for d in self.u.data_list:
            if d.name == name and d.multi_id == multi_id:
                return d
        return None

    def series_name(self, d, field):
        topic = d.name + (".%02d" % d.multi_id if d.name in self.multi else "")
        return "%s/%s" % (topic, pj_field(field))

    def t(self, d):
        return (d.data["timestamp"] - self.t0) / 1e6


def flight_window(log):
    np = log.np
    d = log.topic("vehicle_land_detected")
    if d is not None and "landed" in d.data:
        t, landed = log.t(d), d.data["landed"]
        air = t[landed == 0]
        if len(air):
            return float(air[0]), float(min(air[-1] + 0.5, log.duration))
    d = log.topic("vehicle_status")
    if d is not None and "arming_state" in d.data:
        t, st = log.t(d), d.data["arming_state"]
        arm = t[st == 2]
        if len(arm):
            return float(arm[0]), float(arm[-1])
    return 0.0, float(log.duration)


def rate_error(log, axis):
    np = log.np
    sp, av = log.topic("vehicle_rates_setpoint"), log.topic("vehicle_angular_velocity")
    if sp is None or av is None or axis not in sp.data:
        return None
    ts, ys = log.t(sp), sp.data[axis]
    ta, ya = log.t(av), av.data["xyz[%d]" % AXES[axis]]
    return ts, (ys - np.interp(ts, ta, ya)) * RAD2DEG


def worst_window(log, ts, err, f0, f1, width=2.0):
    np = log.np
    m = (ts >= f0) & (ts <= f1)
    ts, err = ts[m], err[m]
    if len(ts) < 5:
        return None, None, None
    best_c, best_rms = None, -1.0
    step = max(width / 8, 0.05)
    c = ts[0] + width / 2
    while c <= ts[-1] - width / 2 + 1e-9:
        w = (ts >= c - width / 2) & (ts <= c + width / 2)
        if w.sum() >= 3:
            r = float(np.sqrt(np.mean(err[w] ** 2)))
            if r > best_rms:
                best_c, best_rms = c, r
        c += step
    overall = float(np.sqrt(np.mean(err ** 2)))
    return best_c, best_rms, overall


def osc_freq(log, axis, a, b):
    np = log.np
    av = log.topic("vehicle_angular_velocity")
    if av is None:
        return None, None
    t, y = log.t(av), av.data["xyz[%d]" % AXES[axis]]
    m = (t >= a) & (t <= b)
    t, y = t[m], y[m]
    if len(t) < 16:
        return None, None
    fs = (len(t) - 1) / (t[-1] - t[0])
    y = y - y.mean()
    spec = np.abs(np.fft.rfft(y * np.hanning(len(y))))
    freqs = np.fft.rfftfreq(len(y), 1 / fs)
    band = freqs >= 2.0  # 기동(느린 움직임)을 빼고 진동만
    if not band.any():
        return None, round(fs, 1)
    k = np.argmax(spec[band])
    if k == 0:  # 2 Hz 경계에 붙은 봉우리는 느린 움직임이 새어 들어온 것 — 진동으로 보지 않는다
        return None, round(fs, 1)
    return round(float(freqs[band][k]), 1), round(fs, 1)


def motor_info(log, a, b):
    np = log.np
    d = log.topic("actuator_motors")
    if d is None:
        return [], None
    t = log.t(d)
    m = (t >= a) & (t <= b)
    names, stats = [], []
    for i in range(16):
        f = "control[%d]" % i
        if f not in d.data:
            break
        y = d.data[f]
        if np.all(np.isnan(y)) or np.nanmax(np.abs(y)) == 0:
            continue
        names.append(log.series_name(d, f))
        yw = y[m]
        yw = yw[~np.isnan(yw)]
        if len(yw):
            stats.append({"motor": i, "mean": round(float(yw.mean()), 3), "std": round(float(yw.std()), 3),
                          "min": round(float(yw.min()), 3), "max": round(float(yw.max()), 3)})
    return names, stats


def y_range(log, d, fields, a, b, scale=1.0, pad=0.1):
    np = log.np
    t = log.t(d)
    m = (t >= a) & (t <= b)
    vals = np.concatenate([d.data[f][m] * scale for f in fields if f in d.data] or [np.zeros(1)])
    vals = vals[~np.isnan(vals)]
    if not len(vals):
        return -1.0, 1.0
    lo, hi = float(vals.min()), float(vals.max())
    span = (hi - lo) or 1.0
    return lo - span * pad, hi + span * pad


def build_layout(log, axes, problem, flight):
    np = log.np
    plots_by_tab = []
    snippets = []
    att, att_sp = log.topic("vehicle_attitude"), log.topic("vehicle_attitude_setpoint")
    for axis in axes:
        if att is not None:
            snippets.append(angle_snippet(log, att, "q", "%s_deg" % axis, axis))
        if att_sp is not None:
            snippets.append(angle_snippet(log, att_sp, "q_d", "%s_sp_deg" % axis, axis))

    for tab_name, (a, b) in (("문제 구간", problem), ("전체 비행", flight)):
        plots = []
        motors = log.topic("actuator_motors")
        mnames, _ = motor_info(log, a, b)
        if motors is not None and mnames:
            lo, hi = y_range(log, motors, ["control[%d]" % int(n.split(".")[-1]) for n in mnames], a, b)
            plots.append(("모터 출력", a, b, lo, hi, mnames))
        sp, av = log.topic("vehicle_rates_setpoint"), log.topic("vehicle_angular_velocity")
        for axis in axes:
            if sp is not None and av is not None:
                i = AXES[axis]
                lo1, hi1 = y_range(log, sp, [axis], a, b)
                lo2, hi2 = y_range(log, av, ["xyz[%d]" % i], a, b)
                plots.append(("%s 각속도 [rad/s] 목표·실제" % AXIS_KO[axis], a, b, min(lo1, lo2), max(hi1, hi2),
                              [log.series_name(sp, axis), log.series_name(av, "xyz[%d]" % i)]))
            if att is not None and att_sp is not None:
                lo1, hi1 = angle_range(log, att, "q", axis, a, b)
                lo2, hi2 = angle_range(log, att_sp, "q_d", axis, a, b)
                plots.append(("%s 자세 [deg] 목표·실제" % AXIS_KO[axis], a, b, min(lo1, lo2), max(hi1, hi2),
                              ["%s_sp_deg" % axis, "%s_deg" % axis]))
        plots_by_tab.append((tab_name, plots))
    return layout_xml(plots_by_tab, snippets)


def angle_deg(log, d, field, axis):
    np = log.np
    w, x, y, z = (d.data["%s[%d]" % (field, i)] for i in range(4))
    if axis == "roll":
        v = np.arctan2(2 * (w * x + y * z), 1 - 2 * (x * x + y * y))
    elif axis == "pitch":
        v = np.arcsin(np.clip(2 * (w * y - z * x), -1, 1))
    else:
        v = np.arctan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))
    return v * RAD2DEG


def angle_range(log, d, field, axis, a, b, pad=0.1):
    np = log.np
    t = log.t(d)
    m = (t >= a) & (t <= b)
    v = angle_deg(log, d, field, axis)[m]
    v = v[~np.isnan(v)]
    if not len(v):
        return -5.0, 5.0
    lo, hi = float(v.min()), float(v.max())
    span = max(hi - lo, 1.0)
    return lo - span * pad, hi + span * pad


def angle_snippet(log, d, field, name, axis):
    srcs = [log.series_name(d, "%s[%d]" % (field, i)) for i in range(4)]
    body = {
        "roll": "return math.atan(2*(value*v1 + v2*v3), 1 - 2*(v1*v1 + v2*v2)) * 57.29578",
        "pitch": "local s = 2*(value*v2 - v3*v1)\nif s > 1 then s = 1 elseif s < -1 then s = -1 end\nreturn math.asin(s) * 57.29578",
        "yaw": "return math.atan(2*(value*v3 + v1*v2), 1 - 2*(v2*v2 + v3*v3)) * 57.29578",
    }[axis]
    return name, srcs, body


def layout_xml(plots_by_tab, snippets):
    out = ["<?xml version='1.0' encoding='UTF-8'?>", "<root>",
           ' <tabbed_widget name="Main Window" parent="main_window">']
    for tab_name, plots in plots_by_tab:
        n = max(len(plots), 1)
        sizes = ";".join(["%.6f" % (1.0 / n)] * n)
        out += ['  <Tab tab_name="%s" containers="1">' % escape(tab_name), "   <Container>",
                '    <DockSplitter orientation="-" sizes="%s" count="%d">' % (sizes, n)]
        for title, a, b, lo, hi, curves in plots:
            out += ['     <DockArea name="%s">' % escape(title),
                    '      <plot style="Lines" mode="TimeSeries" flip_x="false" flip_y="false">']
            if lo is None:
                out.append('       <range left="%.6f" right="%.6f" top="1" bottom="-1"/>' % (a, b))
                out.append("       <limitY/>")
            else:
                out.append('       <range left="%.6f" right="%.6f" top="%.6f" bottom="%.6f"/>' % (a, b, hi, lo))
                out.append("       <limitY/>")
            for k, c in enumerate(curves):
                out.append('       <curve name="%s" color="%s"/>' % (escape(c), COLORS[k % len(COLORS)]))
            out += ["      </plot>", "     </DockArea>"]
        out += ["    </DockSplitter>", "   </Container>", "  </Tab>"]
    out += ['  <currentTabIndex index="0"/>', " </tabbed_widget>",
            ' <use_relative_time_offset enabled="1"/>',
            " <Plugins>", '  <plugin ID="DataLoad ULog"/>', " </Plugins>",
            " <previouslyLoaded_Datafiles/>", " <customMathEquations>"]
    for name, srcs, body in snippets:
        out += ['  <snippet name="%s">' % escape(name), "   <global></global>",
                "   <function>%s</function>" % escape(body),
                "   <linked_source>%s</linked_source>" % escape(srcs[0]), "   <additional_sources>"]
        out += ["    <v%d>%s</v%d>" % (i, escape(s), i) for i, s in enumerate(srcs[1:], 1)]
        out += ["   </additional_sources>", "  </snippet>"]
    out += [" </customMathEquations>", " <snippets/>", "</root>", ""]
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ulog", nargs="?")
    ap.add_argument("--out")
    ap.add_argument("--axis", default="all", choices=["roll", "pitch", "yaw", "all"])
    ap.add_argument("--window", type=float, default=2.0, help="문제 구간을 찾는 창 길이(초)")
    ap.add_argument("--trim", type=float, default=3.0, help="문제 구간 찾을 때 이륙 후·착륙 전 제외할 시간(초)")
    ap.add_argument("--open", action="store_true", help="PlotJuggler로 바로 열기")
    ap.add_argument("--check", action="store_true", help="필요한 도구 확인만")
    args = ap.parse_args()

    missing = check_tools()
    if args.check:
        print(json.dumps({"missing": missing, "plotjuggler": find_plotjuggler()}, ensure_ascii=False))
        return 0 if not missing else 3
    if "pyulog" in missing or "numpy" in missing:
        print(json.dumps({"error": "missing", "missing": missing}, ensure_ascii=False))
        return 3
    if not args.ulog or not args.out:
        ap.error("ulog 경로와 --out 이 필요합니다")

    log = Log(args.ulog)
    f0, f1 = flight_window(log)
    trim = args.trim if (f1 - f0) > 4 * args.trim else 0.0
    s0, s1 = f0 + trim, f1 - trim  # 문제 구간은 이착륙 직후·직전을 빼고 찾는다
    axes = list(AXES) if args.axis == "all" else [args.axis]

    results = []
    for axis in axes:
        r = rate_error(log, axis)
        if r is None:
            continue
        c, w_rms, all_rms = worst_window(log, r[0], r[1], s0, s1, args.window)
        if c is not None:
            results.append({"axis": axis, "center": c, "window_rms": w_rms, "flight_rms": all_rms})
    worst = max(results, key=lambda x: x["window_rms"]) if results else None
    if worst:
        half = max(args.window, 2.0) * 1.25
        p0, p1 = max(s0, worst["center"] - half), min(s1, worst["center"] + half)
    else:
        p0, p1 = f0, f1
    plot_axes = [worst["axis"]] if (worst and args.axis == "all") else axes

    with open(args.out, "w", encoding="utf-8") as f:
        f.write(build_layout(log, plot_axes, (p0, p1), (f0, f1)))

    freq, fs = osc_freq(log, plot_axes[0], p0, p1)
    _, motors = motor_info(log, p0, p1)
    summary = {
        "log": os.path.basename(args.ulog),
        "duration_s": round(log.duration, 1),
        "flight_s": [round(f0, 1), round(f1, 1)],
        "problem_axis": plot_axes[0],
        "problem_window_s": [round(p0, 1), round(p1, 1)],
        "rate_error_rms_deg_s": {r["axis"]: {"flight": round(r["flight_rms"], 1), "worst_window": round(r["window_rms"], 1)}
                                 for r in results},
        "osc_peak_hz_above_2hz": freq,
        "gyro_log_rate_hz": fs,
        "motors_in_window": motors,
        "layout": os.path.abspath(args.out),
    }

    if args.open:
        pj = find_plotjuggler()
        if not pj:
            summary["opened"] = False
            summary["error"] = "plotjuggler 없음"
        else:
            logf = open(os.path.splitext(args.out)[0] + ".pj.log", "w")
            subprocess.Popen([pj, "-n", "-d", os.path.abspath(args.ulog), "-l", os.path.abspath(args.out)],
                             stdout=logf, stderr=subprocess.STDOUT, start_new_session=True)
            summary["opened"] = True
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
