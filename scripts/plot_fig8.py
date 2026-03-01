#!/usr/bin/env python3

import argparse

from simple_plot import BLUE, ORANGE, Canvas, as_int, draw_axes, linmap, read_csv_rows


def draw_trace(canvas, panel, rows):
    if not rows:
        return
    x_vals = [as_int(r, "time") for r in rows]
    y_vals = [as_int(r, "addr") for r in rows]
    x_min, x_max = min(x_vals), max(x_vals)
    y_min, y_max = min(y_vals), max(y_vals)
    if y_min == y_max:
        y_min -= 1
        y_max += 1

    for r in rows:
        x = linmap(as_int(r, "time"), x_min, x_max, panel[0] + 10, panel[2] - 10)
        y = linmap(as_int(r, "addr"), y_min, y_max, panel[3] - 10, panel[1] + 10)
        rw = r.get("rw", "R").strip().upper()
        color = BLUE if rw in ("R", "READ") else ORANGE
        canvas.point(x, y, color, radius=1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cpu", required=True)
    ap.add_argument("--sepim", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    cpu = read_csv_rows(args.cpu)
    sepim = read_csv_rows(args.sepim)

    canvas = Canvas(1000, 620)
    top = (60, 30, 940, 290)
    bot = (60, 330, 940, 590)
    draw_axes(canvas, *top)
    draw_axes(canvas, *bot)
    draw_trace(canvas, top, cpu)
    draw_trace(canvas, bot, sepim)
    canvas.save_png(args.out)


if __name__ == "__main__":
    main()
