"""Client implementation for Shenju XK One Pro / XK-W202 Bluetooth SPP protocol."""

import json
import logging
import socket
import threading
import time
from pathlib import Path
from typing import Callable, List, Optional

from .frames import Frame, FrameParser
from .protocol import (
    build_57b0,
    build_4a0009,
    build_7300,
    build_7320,
    build_7500,
    build_ack,
    build_battery_info_query,
    build_battery_query,
    build_bind_frames,
    build_keepalive,
    build_poll,
    setup_sequence,
)
from .reassembler import XkImageReassembler

log = logging.getLogger("xkglasses")


def _reply_data_byte(payload: bytes) -> Optional[int]:
    """Returns the first data byte of a reply payload, or ``None``.

    Reply payload layout (after the 4-char node): ``[type:1][len:2 LE][data]``.
    Only ``type == 0x00`` carries raw data; other types are JSON (``0x02``) or a
    one-byte status/error code (``0x04``) and have no raw data byte.
    """
    if len(payload) < 18:
        return None
    if payload[14] != 0x00:
        return None
    length = payload[15] | (payload[16] << 8)
    if length < 1:
        return None
    return payload[17]


class XkGlassesClient:
    """Client for controlling XK One Pro smart glasses over Bluetooth Classic SPP."""

    def __init__(self, channel: int = 8, auto_reconnect: bool = False):
        self.channel = channel
        self.auto_reconnect = auto_reconnect
        self.sock: Optional[socket.socket] = None
        self.parser = FrameParser()
        self.frames: List[Frame] = []
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._frame_listeners: List[Callable[[Frame], None]] = []

        self.bound = False
        self.pk_counter = 0x8E
        self.battery_level: Optional[int] = None
        self.is_charging: bool = False
        self.last_photo_count: int = 0
        # Node 57A0 carries the *video-preview* state (0 = off, 1 = on), not the battery.
        # The SDK's WmVideoPreview handler reads data[0] for exactly this.
        self.preview_state: Optional[int] = None

        # Event callbacks
        self.on_battery: Optional[Callable[[int, bool], None]] = None
        self.on_voice_button: Optional[Callable[[], None]] = None
        self.on_photo_push: Optional[Callable[[int], None]] = None
        self.on_preview_state: Optional[Callable[[int], None]] = None

    def _next_order(self, step: int = 2) -> int:
        cur = self.pk_counter
        self.pk_counter = (self.pk_counter + step) & 0xFF
        return cur

    def connect(self, mac: str, channel: Optional[int] = None) -> None:
        """Connects to the glasses RFCOMM SPP socket on channel 8."""
        self.channel = channel or self.channel
        self.sock = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
        self.sock.connect((mac, self.channel))
        self._stop.clear()
        threading.Thread(target=self._reader, daemon=True, name="XkSppReader").start()

    def _reader(self) -> None:
        while not self._stop.is_set():
            try:
                data = self.sock.recv(65536)
                if not data:
                    break
                new_frames = self.parser.feed(data)
                for f in new_frames:
                    self._handle_frame(f)
                    with self._lock:
                        self.frames.append(f)
                        listeners = list(self._frame_listeners)
                    for listener in listeners:
                        try:
                            listener(f)
                        except Exception as e:
                            log.debug("Frame listener exception: %s", e)
            except (OSError, ValueError) as e:
                log.debug("Reader error: %s", e)
                break

    def _handle_frame(self, f: Frame) -> None:
        p = f.payload
        tag = p[10:14].decode("ascii", "ignore") if len(p) >= 14 else ""
        from_device = (f.cmd & 0x8000) != 0

        # Touch or Voice button event
        if tag in ("C101", "C107") and from_device:
            self.send(build_ack(self._next_order(), f.cmd_order))
            if tag == "C101" and self.on_voice_button:
                self.on_voice_button()
            return

        # Camera frame indication
        if tag == "57B1" and from_device:
            self.send(build_ack(0x26, f.cmd_order))
            return

        # Photo count notification
        if tag == "7320" and from_device:
            count = (
                ((p[16] << 8) | p[17])
                if len(p) >= 18
                else (p[-1] if len(p) > 0 else 6)
            )
            if 1 <= count <= 20:
                self.last_photo_count = count
                self.send(build_ack(0x27, f.cmd_order))
                if self.on_photo_push:
                    self.on_photo_push(count)
            return

        # Battery / device info (node 1001)
        if tag == "1001" and from_device:
            try:
                start = p.find(b"{")
                end = p.rfind(b"}")
                if start >= 0 and end > start:
                    data = json.loads(p[start : end + 1].decode("utf-8"))
                    batt = data.get("battery_main")
                    if batt is not None and str(batt).isdigit():
                        self.battery_level = int(batt)
                        if self.on_battery:
                            self.on_battery(self.battery_level, self.is_charging)
            except Exception as e:
                log.debug("Error parsing 1001 JSON: %s", e)
            return

        # Battery status (node 1003) — binary [is_charging:1][battery_main:1] + 8B padding.
        # This is the ONLY node that reports the charging flag. The vendor SDK parses it in
        # SJUniWatch.batteryBackBusiness() into BatteryBean.
        if tag == "1003" and from_device:
            data = p[17:]
            if len(data) >= 2:
                self.is_charging = data[0] == 1
                self.battery_level = data[1]
                if self.on_battery:
                    self.on_battery(self.battery_level, self.is_charging)
            return

        # Video-preview state (node 57A0). NOT the battery: the vendor SDK's video-preview
        # handler reads data[0] as the preview state (0 = off, 1 = on). Battery comes from
        # nodes 1001 (`battery_main`) and 1003.
        if tag == "57A0" and from_device:
            state = _reply_data_byte(p)
            if state is not None:
                self.preview_state = state
                if self.on_preview_state:
                    self.on_preview_state(state)

    def add_frame_listener(self, listener: Callable[[Frame], None]) -> None:
        with self._lock:
            self._frame_listeners.append(listener)

    def remove_frame_listener(self, listener: Callable[[Frame], None]) -> None:
        with self._lock:
            if listener in self._frame_listeners:
                self._frame_listeners.remove(listener)

    def send(self, frame: Frame) -> None:
        if self.sock is None:
            raise ConnectionError("not connected: call connect() first")
        self.sock.sendall(frame.encode())

    def bind(self) -> bool:
        """Sends the two-phase random session bind sequence.

        Note: this only confirms the frames were transmitted. The device does not
        expose an explicit bind-accepted reply, so a returned ``True`` is not proof
        of authorisation.
        """
        if self.sock is None:
            raise ConnectionError("not connected: call connect() first")
        for i, frame in enumerate(build_bind_frames()):
            self.send(frame)
            time.sleep(0.2)
            self.send(build_poll(0x02 + i * 2))
            time.sleep(0.1)
        time.sleep(1.5)
        return True

    def setup(self) -> bool:
        """Sends the setup sequence (the mandatory ``102E`` user bind plus queries).

        Note: ``self.bound`` records that the sequence was sent; it is not proof of
        authorisation. Capture will fail if the device rejects the session.
        """
        if self.sock is None:
            raise ConnectionError("not connected: call connect() first")
        for frame in setup_sequence():
            self.send(frame)
            time.sleep(0.15)
        time.sleep(0.3)
        self.bound = True
        return True

    def send_keepalive(self) -> None:
        """Sends keepalive packet to maintain the SPP connection."""
        self.send(build_keepalive(self._next_order()))

    def query_battery(self) -> None:
        """Sends the battery-status query (node 1003).

        Node 1003 returns the level **and** the charging flag, so it is preferred over the
        1001 device-info query for battery reads.
        """
        self.send(build_battery_info_query(self._next_order(), self._next_order(1)))

    def get_battery(self, timeout: float = 3.0) -> Optional[int]:
        """Queries and returns the battery level percentage (0..100)."""
        self.battery_level = None
        self.query_battery()
        end = time.time() + timeout
        while time.time() < end:
            if self.battery_level is not None:
                return self.battery_level
            time.sleep(0.1)
        return self.battery_level

    def get_battery_status(self, timeout: float = 3.0) -> tuple:
        """Queries and returns ``(level, is_charging)``; level may be ``None`` on timeout."""
        self.battery_level = None
        self.is_charging = False
        self.query_battery()
        end = time.time() + timeout
        while time.time() < end:
            if self.battery_level is not None:
                break
            time.sleep(0.1)
        return self.battery_level, self.is_charging

    def photo_count(self, timeout: float = 2.0) -> int:
        """Queries the current photo element count."""
        count_event = threading.Event()
        result = [self.last_photo_count]
        def listener(f: Frame) -> None:
            if f.payload[10:14] == b"7320" and (f.cmd & 0x8000) != 0:
                p = f.payload
                count = (
                    ((p[16] << 8) | p[17])
                    if len(p) >= 18
                    else (p[-1] if len(p) > 0 else 0)
                )
                if 1 <= count <= 20:
                    result[0] = count
                    count_event.set()

        self.add_frame_listener(listener)
        try:
            self.send(build_7320(self._next_order()))
            count_event.wait(timeout)
        finally:
            self.remove_frame_listener(listener)

        return result[0]

    def capture_photo(self, out_path: Optional[str] = None, timeout: float = 20.0) -> Optional[bytes]:
        """Triggers a new photo capture on the glasses and downloads the JPEG."""
        if not self.bound:
            self.bind()
            self.setup()

        ready_event = threading.Event()

        def arm_listener(f: Frame) -> None:
            tag = f.payload[10:14] if len(f.payload) >= 14 else b""
            # 7320 carries the element count. 57B1 alone does not, so waiting on it
            # would race ahead of the count.
            if tag == b"7320" and (f.cmd & 0x8000) != 0:
                ready_event.set()

        self.add_frame_listener(arm_listener)
        try:
            self.send(build_57b0(cmd_order=0x24))
            if not ready_event.wait(timeout=8.0):
                log.error("No 7320 element count received after capture trigger")
                return None
        finally:
            self.remove_frame_listener(arm_listener)

        # The element count is announced by the device (7320). Do not guess it: an
        # incorrect count produces a corrupt or incomplete image.
        count = self.last_photo_count
        if count <= 0:
            log.error("No 7320 element count received; cannot download")
            return None
        return self.download_photo(count=count, out_path=out_path, timeout=timeout)

    def download_photo(
        self, count: int = 0, out_path: Optional[str] = None, timeout: float = 20.0
    ) -> Optional[bytes]:
        """Downloads elements 1..N and reassembles the full JPEG image."""
        if count <= 0:
            raise ValueError("count must be > 0; query the element count first (7320)")
        if not self.bound:
            self.bind()
            self.setup()

        reassembler = XkImageReassembler(count)
        tx_order = 0x28
        last_reply_order = -1

        for i in range(1, count + 1):
            reassembler.start_element(i)
            reply_event = threading.Event()
            element_done_event = threading.Event()
            current_tx_order = tx_order

            def element_listener(f: Frame, idx: int = i, tx: int = current_tx_order) -> None:
                nonlocal last_reply_order
                if f.head == 0x30 and len(f.payload) >= 14:
                    tag = f.payload[10:14]
                    if tag == b"7300" and (f.cmd & 0x8000) != 0 and f.cmd_order > last_reply_order:
                        last_reply_order = f.cmd_order
                        self.send(build_ack(tx + 1, f.cmd_order))
                        reply_event.set()
                elif f.head == 0x4A:
                    try:
                        needs_ack = reassembler.feed_image_frame(f)
                        if needs_ack:
                            self.send(build_4a0009(tx + 2))
                        if (f.divide_type & 0x07) in (0, 3):
                            element_done_event.set()
                    except Exception as e:
                        log.error("Image frame processing error: %s", e)

            self.add_frame_listener(element_listener)
            try:
                req_id = 0x003D + 4 * (i - 1)
                self.send(build_7300(index=i, cmd_order=tx_order, request_id=req_id))

                if not reply_event.wait(timeout=timeout / count):
                    log.error("Timeout waiting for 7300 reply on element %d", i)
                    return None

                if not element_done_event.wait(timeout=timeout / count):
                    log.error("Timeout waiting for data on element %d", i)
                    return None

                tx_order += 2
            finally:
                self.remove_frame_listener(element_listener)

        # Send 7500 to conclude image transfer
        self.send(build_7500(cmd_order=tx_order))

        # Reassemble complete JPEG
        try:
            jpeg_bytes = reassembler.build_jpeg()
            if out_path:
                Path(out_path).write_bytes(jpeg_bytes)
            return jpeg_bytes
        except Exception as e:
            log.error("Failed to build JPEG: %s", e)
            return None

    def close(self) -> None:
        """Closes the SPP socket and stops the reader thread."""
        self._stop.set()
        self.bound = False
        if self.sock:
            try:
                self.sock.close()
            except OSError:
                pass
