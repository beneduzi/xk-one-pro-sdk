class CRC16CCITT:
    """Non-reflected CRC-16/CCITT, polynomial 1021, initial FFFF."""
    @staticmethod
    def compute(data: bytes) -> int:
        crc = 0xffff
        for byte in data:
            crc ^= byte << 8
            for _ in range(8):
                crc = ((crc << 1) ^ 0x1021) & 0xffff if crc & 0x8000 else (crc << 1) & 0xffff
        return crc
