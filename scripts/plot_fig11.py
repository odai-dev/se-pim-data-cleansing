#!/usr/bin/env python3

import argparse
from collections import defaultdict

from simple_plot import BLACK, BLUE, GREEN, ORANGE, PURPLE, RED, Canvas, as_float, as_int, draw_axes, linmap, read_csv_rows


def draw_polyline(canvas, points, color):
    if not points:
        return
    for i in range(1, len(points)):
        canvas.line(points[i - 1][0], points[i - 1][1], points[i][0], points[i][1], color)
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

    canvas = Canvas(1200, 500)
    left = (50, 30, 560, 460)
    right = (640, 30, 1150, 460)
    draw_axes(canvas, *left)
    draw_axes(canvas, *right)

    by_core = defaultdict(list)
    cpu_by_ds = {}
    for r in rows:
        ds = as_int(r, "dataset_mb")
        core = as_int(r, "pim_cores")
        by_core[core].append((ds, as_float(r, "pim_baseline_sec"), as_float(r, "sepim_sec")))
        cpu_by_ds[ds] = as_float(r, "cpu_sec")

    for c in by_core:
        by_core[c].sort(key=lambda t: t[0])

    all_ds = sorted(cpu_by_ds.keys())
    x_min, x_max = min(all_ds), max(all_ds)
    y_max = 0.0
    for ds in all_ds:
        y_max = max(y_max, cpu_by_ds[ds])
    for vals in by_core.values():
        for _, p, s in vals:
            y_max = max(y_max, p, s)
    y_min = 0.0
    y_max *= 1.1

    colors = [BLUE, ORANGE, PURPLE, RED]
    for idx, core in enumerate(sorted(by_core.keys())):
        c = colors[idx % len(colors)]
        p_pts = []
        s_pts = []
        for ds, p, s in by_core[core]:
            x = linmap(ds, x_min, x_max, left[0] + 10, left[2] - 10)
            yp = linmap(p, y_min, y_max, left[3] - 10, left[1] + 10)
            ys = linmap(s, y_min, y_max, left[3] - 10, left[1] + 10)
            p_pts.append((x, yp))
            s_pts.append((x, ys))
        draw_polyline(canvas, p_pts, c)
        draw_polyline(canvas, s_pts, (min(c[0] + 30, 255), min(c[1] + 30, 255), min(c[2] + 30, 255)))

    cpu_pts = []
    for ds in all_ds:
        x = linmap(ds, x_min, x_max, left[0] + 10, left[2] - 10)
        y = linmap(cpu_by_ds[ds], y_min, y_max, left[3] - 10, left[1] + 10)
        cpu_pts.append((x, y))
    draw_polyline(canvas, cpu_pts, GREEN)

    # Overhead bars by core
    core_overheads = defaultdict(list)
    for r in rows:
        core_overheads[as_int(r, "pim_cores")].append(as_float(r, "overhead_pct"))
    cores = sorted(core_overheads.keys())
    max_over = max(sum(v) / len(v) for v in core_overheads.values()) * 1.2
    n = len(cores)
    for i, core in enumerate(cores):
        avg_over = sum(core_overheads[core]) / len(core_overheads[core])
        x0 = right[0] + 20 + (i * (right[2] - right[0] - 40) // max(1, n))
        x1 = x0 + (right[2] - right[0] - 80) // max(1, n)
        y = linmap(avg_over, 0.0, max_over, right[3] - 10, right[1] + 10)
        canvas.fill_rect(x0, y, x1, right[3] - 10, ORANGE)
        canvas.rect(x0, y, x1, right[3] - 10, BLACK)

    canvas.save_png(args.out)


if __name__ == "__main__":
    main()
