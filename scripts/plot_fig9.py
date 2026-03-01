#!/usr/bin/env python3

import argparse
from collections import defaultdict

from simple_plot import (
    BLUE,
    ORANGE,
    PURPLE,
    RED,
    Canvas,
    as_float,
    as_int,
    draw_axes,
    linmap,
    read_csv_rows,
)


def draw_polyline(canvas, points, color):
    if not points:
        return
    for i in range(1, len(points)):
        x0, y0 = points[i - 1]
        x1, y1 = points[i]
        canvas.line(x0, y0, x1, y1, color)
    for x, y in points:
        canvas.point(x, y, color, radius=2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    rows = read_csv_rows(args.input)
    if not rows:
        raise SystemExit("empty CSV")

    width, height = 1200, 500
    canvas = Canvas(width, height)

    # Left panel: latency curves by mode.
    left = (50, 30, 560, 460)
    draw_axes(canvas, *left)

    by_mode = defaultdict(list)
    for r in rows:
        m = r.get("access_mode", r.get("mode", "unknown"))
        by_mode[m].append((as_int(r, "block_size"), as_float(r, "baseline_latency_ns"), as_float(r, "sepim_latency_ns")))
    for k in by_mode:
        by_mode[k].sort(key=lambda t: t[0])

    x_min = min(v[0] for vals in by_mode.values() for v in vals)
    x_max = max(v[0] for vals in by_mode.values() for v in vals)
    y_min = 0.0
    y_max = max(max(v[1], v[2]) for vals in by_mode.values() for v in vals) * 1.1

    colors = [BLUE, ORANGE, PURPLE, RED]
    for idx, mode in enumerate(sorted(by_mode.keys())):
        c = colors[idx % len(colors)]
        vals = by_mode[mode]
        base_pts = []
        se_pts = []
        for x_raw, yb, ys in vals:
            x = linmap(x_raw, x_min, x_max, left[0] + 10, left[2] - 10)
            y1 = linmap(yb, y_min, y_max, left[3] - 10, left[1] + 10)
            y2 = linmap(ys, y_min, y_max, left[3] - 10, left[1] + 10)
            base_pts.append((x, y1))
            se_pts.append((x, y2))
        draw_polyline(canvas, base_pts, c)
        draw_polyline(canvas, se_pts, (min(c[0] + 40, 255), min(c[1] + 40, 255), min(c[2] + 40, 255)))

    # Right panel: peak throughput by block size.
    right = (640, 30, 1150, 460)
    draw_axes(canvas, *right)

    peak = {}
    for r in rows:
        size = as_int(r, "block_size")
        b = as_float(r, "baseline_gbps")
        s = as_float(r, "sepim_gbps")
        if size not in peak:
            peak[size] = [b, s]
        else:
            peak[size][0] = max(peak[size][0], b)
            peak[size][1] = max(peak[size][1], s)

    sizes = sorted(peak.keys())
    x_min = min(sizes)
    x_max = max(sizes)
    y_min = 0.0
    y_max = max(max(v[0], v[1]) for v in peak.values()) * 1.1

    base_pts = []
    se_pts = []
    for s in sizes:
        x = linmap(s, x_min, x_max, right[0] + 10, right[2] - 10)
        yb = linmap(peak[s][0], y_min, y_max, right[3] - 10, right[1] + 10)
        ys = linmap(peak[s][1], y_min, y_max, right[3] - 10, right[1] + 10)
        base_pts.append((x, yb))
        se_pts.append((x, ys))
    draw_polyline(canvas, base_pts, BLUE)
    draw_polyline(canvas, se_pts, RED)

    canvas.save_png(args.out)


if __name__ == "__main__":
    main()
