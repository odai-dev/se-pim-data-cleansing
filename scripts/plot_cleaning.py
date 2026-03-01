#!/usr/bin/env python3

import argparse
from collections import defaultdict

from simple_plot import BLACK, BLUE, GREEN, ORANGE, PURPLE, RED, Canvas, draw_axes, linmap, read_csv_rows, as_float, as_int


def draw_polyline(canvas, pts, color):
    if not pts:
        return
    for i in range(1, len(pts)):
        canvas.line(pts[i - 1][0], pts[i - 1][1], pts[i][0], pts[i][1], color)
    for x, y in pts:
        canvas.point(x, y, color, radius=2)


def pick_one_per_mode(rows):
    best = {}
    for r in rows:
        mode = r.get("cleaning_mode", "")
        block = as_int(r, "block_size_bytes") if r.get("block_size_bytes") else 0
        key = (mode, block)
        if mode not in best:
            best[mode] = r
        else:
            # Prefer canonical 4096 when available, else first seen
            cur_block = as_int(best[mode], "block_size_bytes")
            if cur_block != 4096 and block == 4096:
                best[mode] = r
    return [best[k] for k in sorted(best.keys())]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    rows = read_csv_rows(args.input)
    if not rows:
        raise SystemExit("empty CSV")

    canvas = Canvas(1500, 500)
    a = (40, 30, 470, 460)
    b = (535, 30, 965, 460)
    c = (1030, 30, 1460, 460)
    draw_axes(canvas, *a)
    draw_axes(canvas, *b)
    draw_axes(canvas, *c)

    # Panel A: runtime breakdown bars per mode (one representative row per mode).
    rep = pick_one_per_mode(rows)
    if rep:
        modes = [r.get("cleaning_mode", "") for r in rep]
        max_total = max(as_float(r, "total_sec") for r in rep) * 1.15
        n = len(rep)
        w = (a[2] - a[0] - 60) // max(1, n)
        for i, r in enumerate(rep):
            x0 = a[0] + 30 + i * w
            x1 = x0 + max(14, w - 10)
            total = as_float(r, "total_sec")
            scan = as_float(r, "scan_sec")
            clean = as_float(r, "clean_sec")
            km = as_float(r, "kmeans_sec")

            y_bot = a[3] - 10
            y_scan = linmap(scan, 0.0, max_total, y_bot, a[1] + 10)
            y_clean = linmap(scan + clean, 0.0, max_total, y_bot, a[1] + 10)
            y_total = linmap(total, 0.0, max_total, y_bot, a[1] + 10)

            canvas.fill_rect(x0, y_scan, x1, y_bot, BLUE)
            canvas.fill_rect(x0, y_clean, x1, y_scan, ORANGE)
            canvas.fill_rect(x0, y_total, x1, y_clean, GREEN)
            canvas.rect(x0, y_total, x1, y_bot, BLACK)

    # Panel B: total runtime vs block size (hybrid rows).
    hybrid = [r for r in rows if r.get("cleaning_mode") == "hybrid"]
    if hybrid:
        hybrid.sort(key=lambda r: as_int(r, "block_size_bytes"))
        xvals = [as_int(r, "block_size_bytes") for r in hybrid]
        yvals = [as_float(r, "total_sec") for r in hybrid]
        x0, x1 = min(xvals), max(xvals)
        y0, y1 = min(yvals), max(yvals) * 1.1
        pts = []
        for x, y in zip(xvals, yvals):
            px = linmap(x, x0, x1, b[0] + 10, b[2] - 10)
            py = linmap(y, y0, y1, b[3] - 10, b[1] + 10)
            pts.append((px, py))
        draw_polyline(canvas, pts, RED)

    # Panel C: controlled-access MB/s vs block size (hybrid rows).
    if hybrid:
        xvals = [as_int(r, "block_size_bytes") for r in hybrid]
        yvals = [as_float(r, "access_mbps") for r in hybrid]
        x0, x1 = min(xvals), max(xvals)
        y0, y1 = 0.0, max(yvals) * 1.1 if max(yvals) > 0 else 1.0
        pts = []
        for x, y in zip(xvals, yvals):
            px = linmap(x, x0, x1, c[0] + 10, c[2] - 10)
            py = linmap(y, y0, y1, c[3] - 10, c[1] + 10)
            pts.append((px, py))
        draw_polyline(canvas, pts, PURPLE)

    canvas.save_png(args.out)


if __name__ == "__main__":
    main()
