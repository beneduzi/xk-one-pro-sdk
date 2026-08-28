"""Codec tests for xkglasses — includes validation against REAL captured frames.

Run:  python3 tests/test_codec.py   (or pytest)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from xkglasses.crc import CRC16CCITT
from xkglasses.frames import Frame, FrameParser
from xkglasses import protocol


# --- CRC known-answer tests (validated against captured device traffic) ----
def test_crc_known_answers():
    # payload -> stored little-endian CRC, both from real sessions
    cases = [
        ("0100ffffffff0300000130303031003d00674b723934596642576a41443165634e31626d774d75387464444865414b5448375255683962736c736759474a6c74347a394359433775335861304e43", 0xED95),
        ("0102", 0x0E7C),  # poll frame (stored LE bytes 7C 0E)
        ("0104", 0x6EBA),  # poll frame (stored LE bytes BA 6E)
        ("0106", 0x4EF8),  # poll frame (stored LE bytes F8 4E)
    ]
    for payload_hex, expected in cases:
        assert CRC16CCITT.compute(bytes.fromhex(payload_hex)) == expected, payload_hex[:16]


# --- real captured frames: every setup frame must parse + CRC-validate ----
def test_setup_frames_parse_from_capture():
    parser = FrameParser()
    total = 0
    for hexstr in protocol._SETUP_HEX:
        frames = parser.feed(bytes.fromhex(hexstr))  # raises ValueError on CRC mismatch
        assert len(frames) == 1, hexstr[:24]
        total += 1
    assert total == len(protocol._SETUP_HEX)


def test_setup_sequence_objects():
    seq = protocol.setup_sequence()
    assert len(seq) == len(protocol._SETUP_HEX)
    for f in seq:
        assert protocol.verify_crc(f)
    nodes = [f.payload[10:14] for f in seq if f.head == 0x30 and f.cmd == 1]
    assert b"102E" in nodes and b"57B0" in nodes and b"5713" in nodes


def test_bind_frames_structure():
    f1, f2 = protocol.build_bind_frames()
    # bind1: node 0001, 61-char alphanumeric token (after the 0x00 separator)
    assert f1.payload[10:14] == b"0001"
    token = f1.payload[17:]
    assert len(token) == 61
    assert all(c in b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789" for c in token)
    # bind2: node 0002, binary blob
    assert f2.payload[10:14] == b"0002"
    # both frames must encode and round-trip through the parser
    parser = FrameParser()
    assert parser.feed(f1.encode()) and parser.feed(f2.encode())


def test_bind_is_random():
    f1a, _ = protocol.build_bind_frames()
    f1b, _ = protocol.build_bind_frames()
    assert f1a.payload != f1b.payload


def test_roundtrip():
    f = Frame(payload=b"abc")
    raw = f.encode()
    p = FrameParser()
    assert p.feed(raw[:7]) == []          # partial header
    got = p.feed(raw[7:])                 # remainder (may span)
    assert got[-1].payload == b"abc"


def test_tamper():
    raw = bytearray(Frame(payload=b"abc").encode())
    raw[-1] ^= 1
    try:
        FrameParser().feed(raw)
        assert False, "CRC tamper not detected"
    except ValueError:
        pass


def test_photo_builders():
    # 7320
    f = protocol.build_7320()
    assert f.payload[10:14] == b"7320"
    assert protocol.verify_crc(f)
    # 7300 index 3: format 02, status 0001, index byte at payload[18]
    f = protocol.build_7300(3)
    assert f.payload[10:14] == b"7300"
    assert f.payload[6] == 2 and f.payload[14:16] == b"\x00\x01" and f.payload[17] == 3
    assert protocol.verify_crc(f)
    # 4A0009 ack: head 4a, cmd 9, payload 01, counter in cmd_order
    f = protocol.build_4a0009(0x92)
    assert f.head == 0x4A and f.cmd == 0x0009 and f.payload == b"\x01" and f.cmd_order == 0x92
    assert protocol.verify_crc(f)
    # 7500
    assert protocol.build_7500().payload[10:14] == b"7500"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("all tests passed")
