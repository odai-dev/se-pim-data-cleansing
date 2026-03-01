#!/usr/bin/env python3

import argparse

from simple_plot import BLUE, GREEN, ORANGE, Canvas, as_float, as_int, draw_axes, linmap, read_csv_rows


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

    rows.sort(key=lambda r: as_int(r, "block_kb"))

    canvas = Canvas(900, 520)
    panel = (70, 30, 860, 480)
    draw_axes(canvas, *panel)

    x_vals = [as_int(r, "block_kb") for r in rows]
    y_normal = [as_float(r, "normal_mbps") for r in rows]
    y_ctrl = [as_float(r, "controlled_mbps") for r in rows]
    y_oram = [as_float(r, "path_oram_mbps") for r in rows if "path_oram_mbps" in r]

    x_min, x_max = min(x_vals), max(x_vals)
    y_min = 0.0
    y_max = max(max(y_normal), max(y_ctrl), max(y_oram) if y_oram else 0.0) * 1.1

    normal_pts = []
    ctrl_pts = []
    oram_pts = []
    for r in rows:
        x_raw = as_int(r, "block_kb")
        x = linmap(x_raw, x_min, x_max, panel[0] + 10, panel[2] - 10)
        y1 = linmap(as_float(r, "normal_mbps"), y_min, y_max, panel[3] - 10, panel[1] + 10)
        y2 = linmap(as_float(r, "controlled_mbps"), y_min, y_max, panel[3] - 10, panel[1] + 10)
        normal_pts.append((x, y1))
        ctrl_pts.append((x, y2))
        if "path_oram_mbps" in r:
            y3 = linmap(as_float(r, "path_oram_mbps"), y_min, y_max, panel[3] - 10, panel[1] + 10)
            oram_pts.append((x, y3))

    draw_polyline(canvas, normal_pts, BLUE)
    draw_polyline(canvas, ctrl_pts, ORANGE)
    if oram_pts:
        draw_polyline(canvas, oram_pts, GREEN)

    canvas.save_png(args.out)


if __name__ == "__main__":
    main()
