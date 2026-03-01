#!/usr/bin/env python3

import argparse
import csv
import gzip
import importlib.util
import os
import subprocess
import sys
import tempfile


def decode_varint(in_file):
    result = 0
    shift = 0
    while True:
        b = in_file.read(1)
        if not b:
            return None
        v = b[0]
        result |= (v & 0x7F) << shift
        if not (v & 0x80):
            return result
        shift += 7
        if shift >= 64:
            raise ValueError("varint too long")


def decode_message(in_file, message):
    size = decode_varint(in_file)
    if size is None:
        return False
    payload = in_file.read(size)
    if len(payload) != size:
        return False
    message.ParseFromString(payload)
    return True


def load_packet_pb2(gem5_root):
    util_dir = os.path.join(gem5_root, "util")
    packet_pb2 = os.path.join(util_dir, "packet_pb2.py")
    if not os.path.isfile(packet_pb2):
        tmp_out = tempfile.mkdtemp(prefix="sepim_packet_pb2_")
        proto_file = os.path.join(gem5_root, "src", "proto", "packet.proto")
        subprocess.check_call(
            ["protoc", "--python_out", tmp_out, "--proto_path", os.path.dirname(proto_file), proto_file]
        )
        packet_pb2 = os.path.join(tmp_out, "packet_pb2.py")

    spec = importlib.util.spec_from_file_location("packet_pb2", packet_pb2)
    if spec is None or spec.loader is None:
        raise RuntimeError("failed to load packet_pb2")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def open_trace(path):
    with open(path, "rb") as f:
        magic = f.read(2)
    if magic == b"\x1f\x8b":
        return gzip.open(path, "rb")
    return open(path, "rb")


def cmd_to_rw(cmd):
    if cmd == 1:
        return "R"
    if cmd == 4:
        return "W"
    return "U"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="CommMonitor protobuf trace (.out or .gz)")
    ap.add_argument("--output", required=True, help="CSV output path")
    ap.add_argument("--gem5-root", required=True, help="Path to gem5 root containing src/proto/packet.proto")
    ap.add_argument("--tail", type=int, default=0, help="Keep only last N decoded packets (0=all)")
    ap.add_argument("--rw-only", action="store_true", help="Keep only read/write commands")
    args = ap.parse_args()

    pb2 = load_packet_pb2(args.gem5_root)
    header = pb2.PacketHeader()
    packet = pb2.Packet()
    rows = []

    with open_trace(args.input) as proto_in:
        magic = proto_in.read(4)
        if magic != b"gem5":
            raise RuntimeError("invalid trace magic header")

        if not decode_message(proto_in, header):
            raise RuntimeError("failed to decode packet header")

        while decode_message(proto_in, packet):
            rw = cmd_to_rw(packet.cmd)
            if args.rw_only and rw == "U":
                continue
            rows.append(
                {
                    "time": str(packet.tick),
                    "addr": "0x%x" % packet.addr,
                    "rw": rw,
                    "size": str(packet.size),
                    "cmd": str(packet.cmd),
                    "flags": str(packet.flags if packet.HasField("flags") else 0),
                }
            )

    if args.tail > 0 and len(rows) > args.tail:
        rows = rows[-args.tail :]

    out_dir = os.path.dirname(args.output)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    with tempfile.NamedTemporaryFile("w", newline="", delete=False, dir=out_dir or ".") as tf:
        writer = csv.DictWriter(tf, fieldnames=["time", "addr", "rw", "size", "cmd", "flags"])
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
        tmp_name = tf.name

    os.chmod(tmp_name, 0o644)
    os.replace(tmp_name, args.output)
    os.chmod(args.output, 0o644)


if __name__ == "__main__":
    main()
