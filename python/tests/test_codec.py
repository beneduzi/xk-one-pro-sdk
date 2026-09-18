"""Codec tests for xkglasses — includes validation against REAL captured frames and reassembly."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from xkglasses.crc import CRC16CCITT
from xkglasses.frames import Frame, FrameParser
from xkglasses.reassembler import XkImageReassembler
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
    assert b"102E" in nodes and b"5713" in nodes
    # 57B0 must NOT be part of setup: it triggers the shutter.
    assert b"57B0" not in nodes


def test_bind_frames_structure():
    f1, f2 = protocol.build_bind_frames()
    assert f1.payload[10:14] == b"0001"
    token = f1.payload[17:]
    assert len(token) == 61
    assert all(c in b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789" for c in token)
    assert f2.payload[10:14] == b"0002"
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
        FrameParser().feed(bytes(raw))
        assert False, "CRC tamper not detected"
    except ValueError:
        pass


def test_photo_and_control_builders():
    # 57B0
    f = protocol.build_57b0(0x24)
    assert f.payload[10:14] == b"57B0"
    assert protocol.verify_crc(f)

    # 7320
    f = protocol.build_7320()
    assert f.payload[10:14] == b"7320"
    assert protocol.verify_crc(f)

    # 7300 index 3
    f = protocol.build_7300(3)
    assert f.payload[10:14] == b"7300"
    assert protocol.verify_crc(f)

    # 4A0009 ack
    f = protocol.build_4a0009(0x92)
    assert f.head == 0x4A and f.cmd == 0x0009 and f.payload == b"\x01" and f.cmd_order == 0x92
    assert protocol.verify_crc(f)

    # 7500
    assert protocol.build_7500().payload[10:14] == b"7500"

    # 1001 battery query
    f = protocol.build_battery_query(0x8E)
    assert f.payload[10:14] == b"1001"
    assert protocol.verify_crc(f)

    # 300004 ACK
    f = protocol.build_ack(0x26, 0x25)
    assert f.head == 0x30 and f.cmd == 0x0004 and f.payload == bytes((0x01, 0x25))
    assert protocol.verify_crc(f)


def test_image_reassembler():
    reassembler = XkImageReassembler(expected_elements=2)

    # Element 1: Fragmented in 2 parts (divideType 1 and 3)
    # Element header: [media_type: 1B][length: 4B LE], length = total element size
    # Slice 1: \xFF\xD8\x01\x02  -> element = 5 + 4 = 9 bytes
    elem1_meta = b"\x00" + (9).to_bytes(4, "little") + b"\xff\xd8\x01\x02"
    reassembler.start_element(1)

    # Fragment 1 (divideType 1): cmd_idx 0 (4B LE) + first 4 bytes of elem1
    frag1_payload = (0).to_bytes(4, "little") + elem1_meta[:4]
    frame1 = Frame(head=0x4A, divide_type=1, payload=frag1_payload)
    needs_ack = reassembler.feed_image_frame(frame1)
    assert not needs_ack

    # Fragment 2 (divideType 3): cmd_idx 1 (4B LE) + rest of elem1
    frag2_payload = (1).to_bytes(4, "little") + elem1_meta[4:]
    frame2 = Frame(head=0x4A, divide_type=3, payload=frag2_payload)
    needs_ack = reassembler.feed_image_frame(frame2)
    assert needs_ack  # Last fragment must request ACK

    # Element 2: Unfragmented (divideType 0)
    # Slice 2: \x03\x04\xFF\xD9
    elem2_meta = b"\x00" + (9).to_bytes(4, "little") + b"\x03\x04\xff\xd9"
    reassembler.start_element(2)
    frame3 = Frame(head=0x4A, divide_type=0, payload=elem2_meta)
    needs_ack = reassembler.feed_image_frame(frame3)
    assert not needs_ack

    assert reassembler.is_complete
    jpeg = reassembler.build_jpeg()
    assert jpeg == b"\xff\xd8\x01\x02\x03\x04\xff\xd9"
    # Header parsed as (media_type, total element length)
    assert reassembler.element_meta[1] == (0x00, 9)
    assert reassembler.element_meta[2] == (0x00, 9)


def test_element_header_layout_from_real_capture():
    """Element header is [media_type:1][length:4 LE] (length includes the header).

    Real capture: 6 elements, raw sizes 617 / 16389 x4 / 14414. The old docstring had the
    two fields the other way round, which the 5-byte strip happened to hide.
    """
    captured = [
        (617, "0069020000"),
        (16389, "0005400000"),
        (16389, "0005400000"),
        (16389, "0005400000"),
        (16389, "0005400000"),
        (14414, "004e380000"),
    ]
    r = XkImageReassembler(expected_elements=len(captured))
    for i, (raw_len, meta_hex) in enumerate(captured, start=1):
        r.start_element(i)
        raw = bytes.fromhex(meta_hex) + b"\xff\xd8" + b"\x00" * (raw_len - 7)
        assert len(raw) == raw_len
        r.feed_image_frame(Frame(head=0x4A, divide_type=0, payload=raw))
        media_type, declared = r.element_meta[i]
        assert media_type == 0x00
        assert declared == raw_len, f"element {i}: header says {declared}, raw is {raw_len}"
        # declared length must equal the element size including the 5-byte header
        assert declared == len(raw)


# --- byte-exact goldens against captured frames -----------------------------
# These lock in the control-payload framing validated on real hardware:
#   [pk_id:2 LE][FFFFFFFF][action:2 LE][0001][node:4][len:2 BE][format:1=0x00][data]
# A wrong length (off-by-one) or little-endian order makes the device reply with a
# generic 18-byte response and then drop the link.

def _captured_payload(hexstr: str) -> bytes:
    raw = bytes.fromhex(hexstr)
    plen = int.from_bytes(raw[6:8], "little")
    return raw[16:16 + plen]


def test_golden_7300_element_request():
    cap = _captured_payload(
        "303601000000120000000000119900003E00FFFFFFFF020000013733303000010001")
    gen = protocol.build_7300(index=1)
    assert len(gen.payload) == len(cap) == 18
    # pk_id is session-specific; everything else must match byte for byte
    assert gen.payload[2:] == cap[2:]


def test_golden_57b0_is_17_bytes_with_format_byte():
    cap = _captured_payload(
        "308C010000001100000000006BEB0000C400FFFFFFFF0300000135374230000000")
    gen = protocol.build_57b0()
    assert len(gen.payload) == 17 == len(cap)
    assert gen.payload[2:] == cap[2:]


def test_golden_1001_query():
    cap = _captured_payload(
        "307501000000110000000000465B0000A300FFFFFFFF0100000131303031000000")
    gen = protocol.build_battery_query(cmd_order=0x8E, request_id=0x8F)
    assert gen.payload[2:] == cap[2:]


def test_control_length_is_big_endian_and_excludes_format_byte():
    f = protocol.build_control(0, "0001", action_type=3, request_id=1, argument=b"Z" * 61)
    assert f.payload[14:16] == b"\x00\x3d"      # 61, big-endian
    assert f.payload[16] == 0x00                # format byte
    assert f.payload[17:] == b"Z" * 61
    assert len(f.payload) == 16 + 1 + 61


def test_control_without_data_has_zero_length_and_format_byte():
    f = protocol.build_control(0, "7100", action_type=1)
    assert f.payload[10:14] == b"7100"
    assert f.payload[14:16] == b"\x00\x00"
    assert f.payload[16:] == b"\x00"
    assert len(f.payload) == 17


def test_bind_frames_match_captured_structure():
    f1, f2 = protocol.build_bind_frames()
    assert f1.payload[10:14] == b"0001"
    assert f1.payload[14:16] == b"\x00\x3d"     # 61-byte token
    assert f1.payload[16] == 0x00
    assert len(f1.payload[17:]) == 61
    assert f2.payload[10:14] == b"0002"
    assert f2.payload[14:16] == b"\x00\x40"     # 64-byte blob
    assert len(f2.payload[17:]) == 64


def test_encoded_envelope_reserved_bytes_are_zero():
    raw = protocol.build_57b0().encode()
    assert raw[14:16] == b"\x00\x00"


def test_image_frame_crc_is_validated():
    raw = bytearray(Frame(head=0x4A, payload=b"\x01\x02\x03").encode())
    raw[-1] ^= 1
    try:
        FrameParser().feed(bytes(raw))
        assert False, "0x4A CRC tamper not detected"
    except ValueError:
        pass


# --- Reply data byte parsing (real captured frames) ------------------------
def test_reply_data_byte_matches_captured_frames():
    from xkglasses.client import _reply_data_byte

    # 57A0 reply in the setup sequence: type 0x00, len 1, data [0x00]
    # (video-preview state = off; captured live while battery_main was 100%)
    assert _reply_data_byte(bytes.fromhex(
        "1e00ffffffff048000013537413000010000")) == 0x00

    # 57A0 standalone query: type 0x04 (status/error) -> no raw data byte
    assert _reply_data_byte(bytes.fromhex(
        "0000ffffffff648000013537413004010003")) is None

    # 1017 settings: type 0x00, len 4, data [0x1f, 0x00, 0x00, 0x00]
    assert _reply_data_byte(bytes.fromhex(
        "0000ffffffff64800001313031370004001f000000")) == 0x1F

    # C101 camera control: type 0x04 (no-op status) -> no raw data byte
    assert _reply_data_byte(bytes.fromhex(
        "0000ffffffff648000014331303104010004")) is None

    # Short payload is rejected rather than raising
    assert _reply_data_byte(b"\x00" * 17) is None


def test_57a0_does_not_overwrite_battery():
    """Regression: 57A0 is the video-preview state, not a battery push.

    Parsing it as a battery level used to report 0% while the device was at 100%.
    """
    from xkglasses.client import XkGlassesClient

    c = XkGlassesClient()
    c.battery_level = 100
    c._handle_frame(Frame(
        head=0x30, cmd=0x8001, cmd_order=0x1E,
        payload=bytes.fromhex("1e00ffffffff048000013537413000010000"),
    ))
    assert c.battery_level == 100, "57A0 must not touch battery_level"
    assert c.preview_state == 0x00


# --- Battery status (node 1003) --------------------------------------------
# Real captured reply, binary [is_charging:1][battery_main:1] + 8B padding.
_CAP_1003_CHARGING = "a600ffffffff6480000131303033000a0001640000000000000000"
_CAP_1003_IDLE = "a600ffffffff6480000131303033000a0000640000000000000000"


def test_battery_info_query_targets_1003():
    f = protocol.build_battery_info_query(cmd_order=0x94, request_id=0x95)
    assert f.payload[10:14] == b"1003"
    assert protocol.verify_crc(f)


def test_1003_reports_level_and_charging():
    from xkglasses.client import XkGlassesClient

    c = XkGlassesClient()
    c._handle_frame(Frame(
        head=0x30, cmd=0x8002, cmd_order=0x0B,
        payload=bytes.fromhex(_CAP_1003_CHARGING),
    ))
    assert c.battery_level == 100
    assert c.is_charging is True

    c._handle_frame(Frame(
        head=0x30, cmd=0x8002, cmd_order=0x0B,
        payload=bytes.fromhex(_CAP_1003_IDLE),
    ))
    assert c.battery_level == 100
    assert c.is_charging is False


def test_battery_info_query_does_not_break_1001_golden():
    """`build_battery_query` must stay on 1001 (device info) — it has a byte-exact golden."""
    assert protocol.build_battery_query(0x8E).payload[10:14] == b"1001"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("all tests passed")
