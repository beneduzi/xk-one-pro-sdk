# XK One Pro SDK

Lensmoo-free, reverse-engineered Bluetooth SPP support and SDK for the Shenju XK One Pro / XK-W202 smart glasses family. This repository documents the complete wire protocol, frame layout, and two-layer JPEG reassembly engine, providing both Python and Kotlin/Android production implementations.

---

## 🔒 100% On-Device & Zero Cloud Dependencies

* **Direct Peer-to-Peer Bluetooth**: The SDK and drivers connect directly to the glasses over local Bluetooth Classic (RFCOMM SPP Channel 8).
* **No Account or Login Required**: No user registration, vendor accounts, or cloud logins with Lensmoo or Shenju.
* **Zero Cloud Tokens or Proprietary Keys**: All session tokens and bind parameters are generated randomly in-memory at connection time. No user credentials, API keys, or cloud tokens are ever used or transmitted.
* **Full Privacy & Offline Operation**: Photo downloads, camera triggers, battery monitoring, and button events occur strictly on-device without internet access.

---

## Capabilities & Validation Status

| Capability | Status | Notes |
|---|:---:|---|
| **RFCOMM Channel 8 & Envelope Layout** | **VALIDATED LIVE** | 16-byte envelope (`0x30`, `0x4A`, `0x2B` headers) |
| **CRC-16/CCITT Validation** | **VALIDATED LIVE** | Poly `0x1021`, init `0xFFFF`, calculated over payload only |
| **Session Bind (0001 / 0002)** | **VALIDATED LIVE** | In-memory random token generation (unbonded & bonded clients) |
| **Setup & Subsystem Arming Sequence** | **VALIDATED LIVE** | Enables camera pipeline and clears `0x0401` error codes |
| **Photo Capture Trigger (`57B0` $\rightarrow$ `57B1`)** | **VALIDATED LIVE** | Triggers camera shutter; receives `57B1` + `7320` count |
| **Photo Download (`7300` $\rightarrow$ `4A0001` burst)** | **VALIDATED LIVE** | Two-layer reassembly: strips 4B transport `cmd_idx` & 5B element metadata prefix |
| **Photo Transfer Conclusion (`7500`)** | **VALIDATED LIVE** | Closes image session and yields valid `FFD8..FFD9` JPEG |
| **Battery Monitoring (`1001` / `57A0`)** | **VALIDATED LIVE** | Active query via `1001` + unsolicited pushes via `57A0` |
| **Hardware & Touch Button Events (`C101` / `C107`)** | **VALIDATED LIVE** | `C101` push in foreground SPP + `MediaSession` in background |
| **Audio Routing (HFP/SCO & A2DP)** | **VALIDATED LIVE** | Bluetooth SCO microphone + A2DP speaker with clean TTS/STT transitions |

---

## Quickstart (Python / Linux / BlueZ)

```python
from xkglasses import XkGlassesClient

client = XkGlassesClient(channel=8)
client.connect("FA:00:11:12:F7:73")    # Replace with your glasses' MAC address

# 1. Bind and arm camera pipeline (100% local, no cloud needed)
client.bind()
client.setup()

# 2. Query battery percentage
battery = client.get_battery()
print(f"Battery: {battery}%")

# 3. Trigger capture and download full JPEG
jpeg_data = client.capture_photo(out_path="captured_photo.jpg")
print(f"Captured photo: {len(jpeg_data)} bytes saved to captured_photo.jpg")

# 4. Or download existing photo elements without capturing
count = client.photo_count()
print(f"Photo elements stored: {count}")
if count > 0:
    client.download_photo(count=count, out_path="downloaded_photo.jpg")

client.close()
```

### Command-Line Interface (CLI)

```bash
# Check connection & arming
python3 -m xkglasses.cli --mac FA:00:11:12:F7:73 ping

# Query battery level
python3 -m xkglasses.cli --mac FA:00:11:12:F7:73 battery

# Trigger capture & save JPEG
python3 -m xkglasses.cli --mac FA:00:11:12:F7:73 capture --out glasses_photo.jpg

# Listen for real-time events (battery, button presses, photo pushes)
python3 -m xkglasses.cli --mac FA:00:11:12:F7:73 watch
```

---

## Standalone Android / Flutter Example App

A minimal, fully functional Android example application (Flutter + Kotlin) is available in the [`flutter_example/`](flutter_example/) directory:

* Connects to glasses over Bluetooth SPP.
* Displays real-time connection status and battery percentage.
* Captures and downloads photos on demand or automatically via the glasses' hardware/touch button.
* Automatically saves captured photos to the Android Gallery (`Pictures/XKGlasses`).

---

## Architecture & Protocol Overview

The XK One Pro wire protocol uses a two-tier framing structure:

1. **Envelope Header (16 bytes)**:
   ```
   [0]      Head byte (0x30 Control, 0x4A Image/Media, 0x2B Custom JSON)
   [1]      cmd_order (1-byte rolling sequence counter)
   [2..3]   Command / Operation flags (LE): 0x0001 App data, 0x8001 Dev data, 0x0004 ACK, 0x0009 4A-ACK
   [4..5]   divide_type (low 3 bits: 0..3 fragmentation index; high bits: length mod)
   [6..7]   payload_len (2-byte LE payload size)
   [8..11]  Offset / Reserved (4 bytes LE)
   [12..13] CRC-16/CCITT (2 bytes LE over payload bytes only)
   [14..15] Request ID / Reserved (2 bytes BE)
   [16...]  Payload
   ```

2. **Two-Layer Image Reassembly**:
   * **Logical Layer**: Photos are split into $N$ elements (announced by `7320`, requested sequentially via `7300`). Each assembled element begins with a **5-byte metadata prefix** `[length: 4B LE, media_type: 1B]` that must be stripped.
   * **Transport Layer**: Elements are transmitted over channel `0x4A` (`4A0001`). Fragmented packets (`divide_type` 1, 2, 3) begin with a **4-byte little-endian `cmd_idx`** that must be stripped from every fragment.
   * The final fragment of each element (`divide_type` 3) receives a `4A0009` ACK from the app.
   * Concatenating stripped slices $1..N$ yields a bit-perfect JPEG image starting with `0xFF, 0xD8` and ending with `0xFF, 0xD9`.

---

## Documentation Index

* [docs/PROTOCOL.md](docs/PROTOCOL.md) — Comprehensive wire protocol specification: envelopes, CRC algorithm, bind handshake, setup sequence, two-layer image reassembly, battery queries, and touch button events.
* [docs/ANDROID_INTEGRATION.md](docs/ANDROID_INTEGRATION.md) — Production Android / Kotlin integration: high-throughput SPP photo pipeline, background hardware button service (`MediaSession`), and SCO audio routing.
* [docs/HARDWARE.md](docs/HARDWARE.md) — Hardware profile: physical buttons, touch sensor, battery characteristics, Bluetooth Classic profiles (SPP, HFP/SCO, A2DP, AVRCP).
* [docs/BONDED_ENROLLMENT.md](docs/BONDED_ENROLLMENT.md) — Technical specification for socket security, bond states, session initialization, and 100% offline operation.
* [docs/REVERSE_ENGINEERING.md](docs/REVERSE_ENGINEERING.md) — Chronological investigation, breakthrough milestones, and disassembly findings.

---

## License

MIT License. See [LICENSE](LICENSE). This is an independent reverse-engineering project, not affiliated with Shenju or Lensmoo.
