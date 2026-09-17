# XK One Pro SDK

Lensmoo-free, reverse-engineered Bluetooth SPP support and SDK for the Shenju XK One Pro / XK-W202 smart glasses family. This repository documents the observed wire protocol, frame layout, and two-layer JPEG reassembly engine, with reference Python and Kotlin/Android implementations that have been validated against real hardware (see [docs/VALIDATION.md](docs/VALIDATION.md)).

> **Status**: experimental reverse-engineering SDK. Several behaviours are validated live (connect, user bind, capture, download, battery, buttons); others are inferred and marked as such. Do not treat the documentation as a vendor specification.

---

## 🔒 On-Device Operation & Zero Runtime Cloud Dependencies

* **Direct Peer-to-Peer Bluetooth**: The SDK connects directly to the glasses over local Bluetooth Classic (RFCOMM SPP Channel 8).
* **No Account or Login at Runtime**: No user registration, vendor account, or cloud login is needed to connect, capture, or download photos. The glasses validate the session locally and never contact a server during normal operation.
* **Session bind (`0001`/`0002`) content is not validated**: The token and blob in the session bind frames may be random in-memory values. They are not credentials. (Confirmed empirically — see [docs/VALIDATION.md](docs/VALIDATION.md).)
* **One fixed, family-wide identifier is required**: The `102E` bind command must carry a valid `userId` (32 hex characters). The firmware validates it **offline**; arbitrary values are rejected, including on a factory-reset unit. This is not a cloud token and no account lookup happens at runtime, but it *is* a fixed value that must be provisioned. See [docs/BONDED_ENROLLMENT.md](docs/BONDED_ENROLLMENT.md).
* **Offline Operation**: Photo downloads, camera triggers, battery monitoring, and button events occur strictly on-device without internet access.

> The earlier claim of "zero proprietary keys" was incorrect: there is a required fixed identifier in the `102E` frame. The bind payload itself, however, is not validated.

---

## Capabilities & Validation Status

| Capability | Status | Notes |
|---|:---:|---|
| **RFCOMM Channel 8 & Envelope Layout** | **VALIDATED LIVE** | 16-byte envelope (`0x30`, `0x4A`, `0x2B` headers) |
| **CRC-16/CCITT Validation** | **VALIDATED LIVE** | Poly `0x1021`, init `0xFFFF`, calculated over payload only |
| **Session Bind (0001 / 0002)** | **VALIDATED LIVE** | Random in-memory token/blob — payload content is *not* validated by the device |
| **User Bind (`102E` `userId`)** | **VALIDATED LIVE** | Fixed, family-wide 32-hex `userId` required; firmware-validated offline |
| **Setup & Subsystem Arming Sequence** | **VALIDATED LIVE** | Only `102E` (user bind) is required; the remaining queries are optional telemetry |
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
   [14..15] Reserved (2 bytes, encoded as 0x0000)
   [16...]  Payload
   ```

   The control payload (`0x30`) then follows:
   ```
   [pk_id: 2B LE] [FF FF FF FF] [action: 2B LE] [00 01] [node: 4B ASCII] [len: 2B LE] [rest]
   ```
   where `len = len(rest) - 1` (the first byte of `rest` is a format/type byte and is not
   counted). Getting this length wrong makes the firmware answer with a generic 18-byte
   response and then drop the link.

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
* [docs/VALIDATION.md](docs/VALIDATION.md) — Physical test harness, experiments and raw results (what is proven, what is not).
* [docs/NODES.md](docs/NODES.md) — Command/node inventory with an explicit confidence level per entry.

---

## License

MIT License. See [LICENSE](LICENSE). This is an independent reverse-engineering project, not affiliated with Shenju or Lensmoo.
