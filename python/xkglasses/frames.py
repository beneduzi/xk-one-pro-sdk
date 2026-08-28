from dataclasses import dataclass
from .crc import CRC16CCITT

@dataclass
class Frame:
    head: int = 0x30
    cmd_order: int = 0
    cmd: int = 1
    divide_type: int = 0
    offset: int = 0
    request_id: int = 0
    payload: bytes = b""

    def encode(self) -> bytes:
        h = bytes((self.head, self.cmd_order)) + self.cmd.to_bytes(2, 'little') + self.divide_type.to_bytes(2, 'little')
        h += len(self.payload).to_bytes(2, 'little') + self.offset.to_bytes(4, 'little')
        h += CRC16CCITT.compute(self.payload).to_bytes(2, 'little') + self.request_id.to_bytes(2, 'big')
        return h + self.payload

class FrameParser:
    def __init__(self): self._buffer = bytearray()
    def feed(self, data: bytes):
        self._buffer.extend(data)
        result = []
        while len(self._buffer) >= 16:
            if self._buffer[0] not in (0x30, 0x2b, 0x4a): del self._buffer[0]; continue
            n = 16 + int.from_bytes(self._buffer[6:8], 'little')
            if len(self._buffer) < n: break
            raw = bytes(self._buffer[:n]); del self._buffer[:n]
            if raw[0] in (0x30, 0x2b) and CRC16CCITT.compute(raw[16:]) != int.from_bytes(raw[12:14], 'little'):
                raise ValueError('frame CRC mismatch')
            result.append(Frame(raw[0], raw[1], int.from_bytes(raw[2:4], 'little'), int.from_bytes(raw[4:6], 'little'), int.from_bytes(raw[8:12], 'little'), int.from_bytes(raw[14:16], 'big'), raw[16:]))
        return result
