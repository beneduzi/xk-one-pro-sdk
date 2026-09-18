"""Image reassembler for XK One Pro smart glasses JPEG downloads.

The protocol operates on two layers:
1. Logical layer: The JPEG is divided into N elements (announced by 7320,
   requested sequentially via 7300). Each assembled element contains a
   5-byte metadata prefix ``[media_type: 1B][length: 4B LE]`` that must be
   stripped to obtain the raw JPEG slice. ``length`` is the total element
   size **including** the 5-byte header, so the slice is ``length - 5`` bytes.
   Verified against 6/6 elements of a live capture (lengths 617, 16389 x4,
   14414 all matched the assembled element size exactly).
2. Transport layer: Elements are transported via channel 0x4A frames (4A0001).
   Fragmented frames (divide_type 1, 2, 3) prepend a 4-byte little-endian
   cmd_idx which must be stripped from each fragment.
   Non-fragmented frames (divide_type 0) contain no cmd_idx and require no ACK.
   The final fragment (divide_type 3) requires sending a 4A0009 ACK.
"""

from io import BytesIO
from typing import Dict, List, Optional, Tuple
from .frames import Frame

ELEMENT_METADATA_SIZE = 5
PACKED_LENGTH_MASK = 0x1FFF
JPEG_START = b"\xff\xd8"
JPEG_END = b"\xff\xd9"

# Media type byte in the element header. Only 0x00 (photo/JPEG) was observed.
MEDIA_TYPE_PHOTO = 0x00


class XkImageReassembler:
    """Reassembles a full JPEG from 0x4A transport frames."""

    def __init__(self, expected_elements: Optional[int] = None):
        self.expected_elements = expected_elements
        self.completed_elements: Dict[int, bytes] = {}
        # index -> (media_type, declared_length) from the 5-byte element header
        self.element_meta: Dict[int, Tuple[int, int]] = {}
        self.active_element_index: Optional[int] = None
        self.active_logical_length_mod: Optional[int] = None
        self.active_next_cmd_idx: int = 0
        self.active_fragments: List[bytes] = []

    @property
    def is_complete(self) -> bool:
        if not self.expected_elements or self.expected_elements <= 0:
            return False
        return all(i in self.completed_elements for i in range(1, self.expected_elements + 1))

    def set_element_count(self, count: int) -> None:
        if count <= 0:
            raise ValueError(f"Element count must be > 0, got {count}")
        self.expected_elements = count

    def start_element(self, index: int) -> None:
        if self.expected_elements and (index < 1 or index > self.expected_elements):
            raise ValueError(f"Element index {index} outside expected 1..{self.expected_elements}")
        self.active_element_index = index
        self.active_logical_length_mod = None
        self.active_next_cmd_idx = 0
        self.active_fragments.clear()

    def feed_image_frame(self, frame: Frame) -> bool:
        """Feed a 0x4A image frame.

        Returns:
            True if this frame completed a fragmented element (requires sending 4A0009 ACK),
            False otherwise (e.g. intermediate fragment or unfragmented single frame).
        """
        if frame.head != 0x4A:
            raise ValueError(f"Expected channel 0x4A, got 0x{frame.head:02X}")

        index = self.active_element_index
        if index is None:
            raise RuntimeError("No active element requested for image frame")

        divide_type = frame.divide_type & 0x07
        logical_length_mod = ((frame.divide_type & 0xF8) << 5) | ((frame.divide_type >> 8) & 0xFF)

        if divide_type == 0:
            # Single unfragmented packet
            raw_element = frame.payload
            self._store_element(index, raw_element)
            self.active_element_index = None
            return False

        elif divide_type == 1:
            # First fragment
            self.active_logical_length_mod = logical_length_mod
            self.active_next_cmd_idx = 0
            self.active_fragments.clear()
            self._append_fragment(frame.payload)
            return False

        elif divide_type == 2:
            # Middle fragment
            self._append_fragment(frame.payload)
            return False

        elif divide_type == 3:
            # Last fragment
            self._append_fragment(frame.payload)
            raw_element = b"".join(self.active_fragments)
            self._store_element(index, raw_element)
            self.active_element_index = None
            self.active_fragments.clear()
            return True

        else:
            raise ValueError(f"Unknown divide_type: {divide_type}")

    def _append_fragment(self, payload: bytes) -> None:
        if len(payload) < 4:
            raise ValueError("Fragmented 4A frame payload too short (< 4 bytes for cmd_idx)")
        cmd_idx = int.from_bytes(payload[:4], "little")
        if cmd_idx != self.active_next_cmd_idx:
            raise ValueError(
                f"Unexpected cmd_idx in element {self.active_element_index}: "
                f"expected {self.active_next_cmd_idx}, got {cmd_idx}"
            )
        self.active_fragments.append(payload[4:])
        self.active_next_cmd_idx += 1

    def _store_element(self, index: int, raw_element: bytes) -> None:
        if len(raw_element) < ELEMENT_METADATA_SIZE:
            raise ValueError(f"Element {index} too small (< {ELEMENT_METADATA_SIZE} bytes)")
        # Element header: [media_type: 1B][length: 4B LE], where `length` is the total
        # element size *including* this 5-byte header.
        media_type = raw_element[0]
        declared_length = int.from_bytes(raw_element[1:5], "little")
        self.element_meta[index] = (media_type, declared_length)
        jpeg_slice = raw_element[ELEMENT_METADATA_SIZE:]
        self.completed_elements[index] = jpeg_slice

    def build_jpeg(self) -> bytes:
        """Assembles and validates the full JPEG bytes."""
        if not self.expected_elements:
            raise RuntimeError("Element count not set")
        if not self.is_complete:
            missing = [i for i in range(1, self.expected_elements + 1) if i not in self.completed_elements]
            raise RuntimeError(f"Cannot build JPEG, missing elements: {missing}")

        out = BytesIO()
        for i in range(1, self.expected_elements + 1):
            out.write(self.completed_elements[i])

        image = out.getvalue()
        if len(image) < 4:
            raise ValueError(f"Reassembled JPEG too short ({len(image)} bytes)")
        if not image.startswith(JPEG_START):
            raise ValueError(f"Reassembled JPEG does not start with FFD8 (starts with {image[:2].hex()})")
        if not image.endswith(JPEG_END):
            raise ValueError(f"Reassembled JPEG does not end with FFD9 (ends with {image[-2:].hex()})")

        return image
