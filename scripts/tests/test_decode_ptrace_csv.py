import importlib.util
import io
from pathlib import Path
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "decode_ptrace_csv.py"
SPEC = importlib.util.spec_from_file_location("decode_ptrace_csv", SCRIPT)
decoder = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(decoder)


def framed(payload):
    if len(payload) >= 128:
        raise AssertionError("test frame is too large")
    return bytes([len(payload)]) + payload


class Header:
    def ParseFromString(self, payload):
        self.payload = payload


class Packet:
    def ParseFromString(self, payload):
        tick, addr, command, size, flags = (
            int(value) for value in payload.decode("ascii").split(",")
        )
        self.tick = tick
        self.addr = addr
        self.cmd = command
        self.size = size
        self.flags = flags

    def HasField(self, name):
        return name == "flags"


class FakePb2:
    PacketHeader = Header
    Packet = Packet


class DecoderTests(unittest.TestCase):
    def test_positive_tail_is_bounded_and_keeps_last_rw_packets(self):
        payload = bytearray(b"gem5")
        payload.extend(framed(b"header"))
        kept = []
        for tick in range(5000):
            command = 7 if tick % 11 == 0 else (1 if tick % 2 else 4)
            packet = f"{tick},{0x80000000 + tick},{command},64,3".encode("ascii")
            payload.extend(framed(packet))
            if command in (1, 4):
                kept.append(tick)
        rows = decoder.decode_rows(
            io.BytesIO(bytes(payload)), FakePb2, tail=17, rw_only=True
        )
        self.assertEqual(17, len(rows))
        self.assertEqual([str(value) for value in kept[-17:]], [r["time"] for r in rows])
        self.assertEqual({"R", "W"}, {r["rw"] for r in rows})

    def test_invalid_magic_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "magic"):
            decoder.decode_rows(io.BytesIO(b"nope"), FakePb2, tail=1)

    def test_negative_tail_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "non-negative"):
            decoder.decode_rows(io.BytesIO(), FakePb2, tail=-1)

    def test_truncated_packet_is_rejected(self):
        payload = b"gem5" + framed(b"header") + bytes([10]) + b"short"
        with self.assertRaisesRegex(EOFError, "truncated protobuf message"):
            decoder.decode_rows(io.BytesIO(payload), FakePb2, tail=4)


if __name__ == "__main__":
    unittest.main()
