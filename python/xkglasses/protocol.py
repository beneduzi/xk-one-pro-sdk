"""Protocol builders for the XK One Pro smartglasses (SJ/Lensmoo SPP protocol).

Frame layout (all values validated against 21 captured frames + live sessions):
    [0]   head 0x30 / 0x2b / 0x4a
    [1]   cmd_order u8
    [2:4] cmd u16 LE
    [4:6] divide_type u16 LE
    [6:8] payload_len u16 LE
    [8:12] offset u32 LE
    [12:14] crc16 u16 LE  (CRC-16/CCITT poly 0x1021 init 0xFFFF, over payload only)
    [14:16] request_id u16 BE
    [16:]  payload

Payload package: [pk_id:2][ff ff ff ff][format:1][00 00][01][node:4 ASCII][status/action:2][data...]

Validated live: RFCOMM channel 8 carries the binary protocol (channel 1 is an
AT/HFP interface). The bind token is NOT content-validated (any well-formed
61-char alphanumeric token works). The setup sequence below is the verbatim
frame list from a working Lensmoo session (2026-08-27, captured in
sj_sdk_fresh.log) — replayable as-is.
"""

from .frames import Frame, FrameParser
from .crc import CRC16CCITT

# ---------------------------------------------------------------------------
# Setup sequence — VERBATIM frames from a captured session (18:40:54.854..18:40:58.776).
# Order matters: queries and FGS/FND custom messages arm the camera pipeline;
# without them command responses carry error status 0x0401.
# ---------------------------------------------------------------------------
_SETUP_HEX = [
    # 18:40:54.904 — query 7100 (device status)
    "306C01000000110000000000388900009500FFFFFFFF0100000137313030000000",
    # 18:40:54.922 — poll 0004
    "306D04000000020000000000F84E00000106",
    # 18:40:54.926 — query 102E (registers userId "1f1823e0e2896cdb8012a3ac083a35e6")
    "306E01000000430000000000D0BE00009800FFFFFFFF03000001313032450032000200000000000000000000000000000000203166313832336530653238393663646238303132613361633038336133356536",
    # 18:40:54.962 — query 7110
    "306F01000000110000000000D7D600009A00FFFFFFFF0100000137313130000000",
    # 18:40:54.963 — poll
    "30700400000002000000000036AF00000108",
    # 18:40:54.990 — custom msg 2B0004 (F0600100)
    "2B7104000000070000000000B87E0000010000F0600100",
    # 18:40:54.994 — poll
    "307304000000020000000000559F0000010B",
    # 18:40:55.028 — poll
    "307404000000020000000000F0CF0000010E",
    # 18:40:55.030 — query 1001
    "307501000000110000000000465B0000A300FFFFFFFF0100000131303031000000",
    # 18:40:55.034 — custom msg (F0600300)
    "2B76040000000700000000008BB20000010001F0600300",
    # 18:40:55.061 — poll
    "3077040000000200000000000F3C00000110",
    # 18:40:55.075 — query 1003
    "30780100000011000000000044E50000A600FFFFFFFF0100000131303033000000",
    # 18:40:55.079 — custom msg FGS: {"sid":"FGS","data":"{\"msg_type\":\"FGS_MSG_TYPE_START_FGS_REQ\",\"sidver\":1}","ver":1}
    "2B79040000005E00000000005347000001000800417B22736964223A22464753222C2264617461223A227B5C226D73675F747970655C223A5C224647535F4D53475F545950455F53544152545F4647535F5245515C222C5C227369647665725C223A317D222C22766572223A317D",
    # 18:40:55.091 — poll
    "307A040000000200000000006C0C00000113",
    # 18:40:55.093 — query 2410
    "307B0100000011000000000054FF0000A900FFFFFFFF0100000132343130000000",
    # 18:40:55.129 — custom msg FND: {"sid":"FND","data":"AQ0AMTc4Nzg2NTM2NzA2Ng==","ver":1}
    "2B7C040000003C0000000000C867000001000900417B22736964223A22464E44222C2264617461223A22415130414D5463344E7A67324E6A67314E5445794E773D3D222C22766572223A317D",
    # 18:40:55.136 — poll
    "307D04000000020000000000C95C00000116",
    # 18:40:55.188 — custom msg FND (2nd)
    "2B7E040000002C00000000001BB2000001000A00417B22736964223A22464E44222C2264617461223A224177454141413D3D222C22766572223A317D",
    # 18:40:55.213 — query C10A
    "307F010000001100000000001CED0000AC00FFFFFFFF0300000143313041000000",
    # 18:40:55.216 — query 2420
    "308001000000170000000000E1E00000AE00FFFFFFFF0200000132343230000600656E00000000",
    # 18:40:55.227 — query C104
    "308101000000110000000000FC110000B000FFFFFFFF0200000143313034000000",
    # 18:40:55.235 — query 57A0
    "308201000000120000000000FFD20000B300FFFFFFFF030000013537413000010000",
    # 18:40:55.236 — query 5770
    "308301000000120000000000661A0000B500FFFFFFFF030000013537373000010000",
    # 18:40:55.250..56.286 — polls
    "308404000000020000000000459D0000011A",
    "30850400000002000000000083FD0000011C",
    "308604000000020000000000E0CD0000011F",
    "3087040000000200000000005C0A00000120",
    "3089040000000200000000007D1A00000121",
    # 18:40:56.287 — query 5713 (returns {"photo_num":"N"})
    "30880100000011000000000083DF0000BE00FFFFFFFF0100000135373133000000",
    # 18:40:56.310 — poll
    "308B040000000200000000003F3A00000123",
    # 18:40:57.748 — 57B0 (camera arm / preview picture request)
    "308C010000001100000000006BEB0000C400FFFFFFFF0300000135374230000000",
    # 18:40:58.776 — poll
    "308D04000000020000000000F95A00000125",
]

_PARSER = FrameParser()


def _from_hex(hexstr: str) -> Frame:
    """Parse a verbatim wire frame into a Frame (CRC-validated)."""
    frames = _PARSER.feed(bytes.fromhex(hexstr))
    assert len(frames) == 1, f"bad captured frame: {hexstr[:24]}"
    return frames[0]


def _payload(node: bytes, data: bytes = b"", pk: int = 0, fmt: int = 3, status: bytes = b"\x00\x00") -> bytes:
    return pk.to_bytes(2, "little") + b"\xff\xff\xff\xff" + bytes((fmt,)) + b"\x00\x00\x01" + node + status + data


def _cmd(node: str, data: bytes = b"", order: int = 0, cmd: int = 1, pk: int = 0, status: bytes = b"\x00\x00", fmt: int = 3) -> Frame:
    return Frame(cmd_order=order, cmd=cmd, payload=_payload(node.encode(), data, pk, fmt, status))


def build_bind_frames() -> list:
    """Build a session bind: two frames with RANDOM tokens.

    Validated live: the device does NOT validate the bind content — any
    well-formed 61-char alphanumeric token (bind1, node 0001) and random
    binary blob (bind2, node 0002) are accepted.
    """
    import random
    import string

    token = "".join(random.choices(string.ascii_letters + string.digits, k=61)).encode()
    blob = random.randbytes(40)
    return [
        _cmd("0001", b"\x00" + token, pk=1, status=b"\x00\x3d"),
        _cmd("0002", b"\x00" + blob, pk=4, status=b"\x00\x40"),
    ]


def build_poll(pk_id: int = 0x02) -> Frame:
    """0004 keepalive/ack poll. Payload is [0x01][pk_id] (captured pattern)."""
    return Frame(cmd=4, payload=bytes((0x01, pk_id & 0xFF)))


def setup_sequence() -> list:
    """The verbatim session setup (after bind): queries + FGS/FND custom msgs.

    Required before photo flows — without it command responses carry the
    error status 0x0401 instead of 0x0001/0x0000.
    """
    return [_from_hex(h) for h in _SETUP_HEX]


def build_7320() -> Frame:
    """Request photo element count. Response payload's last byte = count."""
    return _cmd("7320", pk=0x20)


def build_7300(index: int) -> Frame:
    """Request photo element by index (1-based). Format 02 + status 0001 per capture."""
    return _cmd("7300", bytes((0x00, index)), pk=0x40 + index, fmt=2, status=b"\x00\x01")


def build_4a0009(pk_id: int = 0x92) -> Frame:
    """Ack for a 4A0001 data burst. Head 0x4a, cmd 0x0009, payload b'\\x01';
    the burst counter lives in cmd_order (0x92, 0x94, ...)."""
    return Frame(head=0x4A, cmd_order=pk_id, cmd=0x0009, payload=b"\x01")


def build_7500() -> Frame:
    """End photo transfer."""
    return _cmd("7500", pk=0x56, fmt=3, status=b"\x00\x01")


def verify_crc(frame: Frame) -> bool:
    """Sanity: recompute the wire CRC of an encoded frame."""
    raw = frame.encode()
    return CRC16CCITT.compute(raw[16:]) == int.from_bytes(raw[12:14], "little")
