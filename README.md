# XK One Pro SDK

Lensmoo-free, reverse-engineered Bluetooth SPP support for the Shenju XK One Pro / XK-W202 family. It documents the wire protocol and provides a Python implementation path for independent applications.

## Status

| Capability | Status |
|---|---|
| RFCOMM channel 8 and frame format | **VALIDATED live** |
| CRC-16/CCITT, 21/21 captured frames | **VALIDATED live** |
| Free-form bind and ordered setup | **VALIDATED live** |
| Queries, including `5713` photo_num and `7320` count | **VALIDATED live** |
| `7300` → `4A0001` JPEG download | **PENDING** end-to-end hardware confirmation; implemented from the captured dialog |
| Audio routing | **PENDING** |
| Hardware button media-key events | **PENDING** |

The protocol is reverse-engineered and not affiliated with Shenju. Use at your own risk; firmware behavior may differ across units.

## Quickstart (Linux / BlueZ)

```python
from xkglasses import XkGlassesClient

c = XkGlassesClient()                     # SPP on RFCOMM channel 8
c.connect("FA:00:11:12:F7:73")            # the glasses' MAC
c.bind()                                  # random token/blob — content not validated
c.setup()                                 # queries + FGS/FND custom messages (required)
print("photos:", c.photo_count())         # 7320 count query
if c.photo_count():
    c.download_photo(1, "photo.jpg")      # 7300 -> 4A0001 burst -> JPEG
c.close()

# CLI equivalent:
#   python -m xkglasses --mac FA:00:11:12:F7:73 count
#   python -m xkglasses --mac FA:00:11:12:F7:73 photo --out photo.jpg
```

Pair the glasses first. Channel 1 is an AT/HFP interface; binary protocol traffic belongs on channel 8.

## Repository layout

- `docs/PROTOCOL.md` — frames, CRC, commands, bind, setup, and photo transfer.
- `docs/HARDWARE.md` — observed hardware, Bluetooth services, profiles, and quirks.
- `docs/REVERSE_ENGINEERING.md` — evidence and investigation timeline.
- `docs/ANDROID_INTEGRATION.md` — Kotlin/Flutter integration notes.

See the [MIT license](LICENSE). This is independent reverse engineering, not vendor software.
