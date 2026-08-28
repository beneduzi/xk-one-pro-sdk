import socket, threading, time, logging
from pathlib import Path
from .frames import FrameParser, Frame
from .protocol import *
log=logging.getLogger('xkglasses')
class XkGlassesClient:
    def __init__(self, channel=8, auto_reconnect=False):
        self.channel=channel; self.auto_reconnect=auto_reconnect; self.sock=None; self.parser=FrameParser(); self.frames=[]; self._stop=threading.Event(); self._lock=threading.Lock()
    def connect(self, mac, channel=None):
        self.channel=channel or self.channel; self.sock=socket.socket(socket.AF_BLUETOOTH,socket.SOCK_STREAM,socket.BTPROTO_RFCOMM); self.sock.connect((mac,self.channel)); threading.Thread(target=self._reader,daemon=True).start()
    def _reader(self):
        while not self._stop.is_set():
            try:
                data=self.sock.recv(65536)
                if not data: break
                with self._lock: self.frames.extend(self.parser.feed(data))
            except (OSError,ValueError) as e: log.debug('reader: %s',e); break
    def send(self, frame): self.sock.sendall(frame.encode() if isinstance(frame,Frame) else frame)
    def _wait(self, seconds=.5): time.sleep(seconds); return self.frames
    def bind(self):
        for i, frame in enumerate(build_bind_frames()):
            self.send(frame); self._wait(1)
            self.send(build_poll(0x02 + i * 2)); self._wait(0.5)
        return True
    def setup(self):
        # the verbatim setup sequence already interleaves the 0004 polls
        for frame in setup_sequence(): self.send(frame); self._wait(0.3)
    def photo_count(self):
        self.send(build_7320()); self._wait(1)
        for f in reversed(self.frames):
            if f.head==0x30 and f.cmd==1 and b'7320' in f.payload: return f.payload[-1]
        return 0
    def download_photo(self,index,out_path):
        self.send(build_7300(index)); self._wait(1); self.frames=[]; end=time.time()+30; data=bytearray(); ack=0
        while time.time()<end:
            with self._lock: fs=self.frames[:]; self.frames.clear()
            for f in fs:
                if f.head==0x4a and f.cmd==1 and len(f.payload)>=20:
                    data.extend(f.payload[20:]); ack += 2; self.send(build_4a0009(0x90 + ack))
            if data.endswith(b'\xff\xd9'): break
            time.sleep(.05)
        self.send(build_7500()); ok=data.startswith(b'\xff\xd8') and data.endswith(b'\xff\xd9')
        if ok: Path(out_path).write_bytes(data)
        return ok
    def close(self):
        self._stop.set()
        if self.sock:
            try: self.sock.close()
            except OSError: pass
