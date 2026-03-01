#!/usr/bin/env python3

import csv
import struct
import zlib


WHITE = (255, 255, 255)
BLACK = (20, 20, 20)
RED = (214, 39, 40)
BLUE = (31, 119, 180)
GREEN = (44, 160, 44)
ORANGE = (255, 127, 14)
PURPLE = (148, 103, 189)
GRAY = (160, 160, 160)


class Canvas:
    def __init__(self, width, height, bg=WHITE):
        self.width = width
        self.height = height
        self.pixels = [bytearray(bg * width) for _ in range(height)]

    def point(self, x, y, color, radius=1):
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                px = x + dx
                py = y + dy
                if 0 <= px < self.width and 0 <= py < self.height:
                    idx = px * 3
                    row = self.pixels[py]
                    row[idx:idx + 3] = bytes(color)

    def line(self, x0, y0, x1, y1, color):
        dx = abs(x1 - x0)
        sx = 1 if x0 < x1 else -1
        dy = -abs(y1 - y0)
        sy = 1 if y0 < y1 else -1
        err = dx + dy
        while True:
            self.point(x0, y0, color, radius=0)
            if x0 == x1 and y0 == y1:
                break
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x0 += sx
            if e2 <= dx:
                err += dx
                y0 += sy

    def rect(self, x0, y0, x1, y1, color):
        self.line(x0, y0, x1, y0, color)
        self.line(x1, y0, x1, y1, color)
        self.line(x1, y1, x0, y1, color)
        self.line(x0, y1, x0, y0, color)

    def fill_rect(self, x0, y0, x1, y1, color):
        xa, xb = sorted((x0, x1))
        ya, yb = sorted((y0, y1))
        xa = max(0, xa)
        ya = max(0, ya)
        xb = min(self.width - 1, xb)
        yb = min(self.height - 1, yb)
        for y in range(ya, yb + 1):
            row = self.pixels[y]
            for x in range(xa, xb + 1):
                idx = x * 3
                row[idx:idx + 3] = bytes(color)

    def save_png(self, path):
        def chunk(tag, data):
            return (
                struct.pack("!I", len(data))
                + tag
                + data
                + struct.pack("!I", zlib.crc32(tag + data) & 0xFFFFFFFF)
            )

        raw = b"".join(b"\x00" + bytes(row) for row in self.pixels)
        ihdr = struct.pack("!2I5B", self.width, self.height, 8, 2, 0, 0, 0)
        with open(path, "wb") as f:
            f.write(b"\x89PNG\r\n\x1a\n")
            f.write(chunk(b"IHDR", ihdr))
            f.write(chunk(b"IDAT", zlib.compress(raw, 9)))
            f.write(chunk(b"IEND", b""))


def read_csv_rows(path):
    with open(path, "r", newline="") as f:
        return list(csv.DictReader(f))


def as_float(row, key):
    return float(row[key])


def as_int(row, key):
    v = row[key].strip()
    if v.startswith("0x") or v.startswith("0X"):
        return int(v, 16)
    return int(float(v))


def linmap(v, lo, hi, out_lo, out_hi):
    if hi <= lo:
        return (out_lo + out_hi) // 2
    t = (v - lo) / (hi - lo)
    return int(out_lo + t * (out_hi - out_lo))


def draw_axes(canvas, x0, y0, x1, y1):
    canvas.rect(x0, y0, x1, y1, BLACK)
    # light grid lines
    for i in range(1, 5):
        x = x0 + (x1 - x0) * i // 5
        y = y0 + (y1 - y0) * i // 5
        canvas.line(x, y0, x, y1, GRAY)
        canvas.line(x0, y, x1, y, GRAY)

