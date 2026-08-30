# Hardware & Bluetooth Profile Specifications

Detailed hardware observations and Bluetooth profile configuration for the Shenju XK One Pro / XK-W202 smart glasses family.

---

## 1. Device Specifications

* **Product Family**: Shenju XK One Pro / LensMoo W202 / W20
* **Device Name Pattern**: `xk one Pro_XXXX` (where `XXXX` matches the last 4 characters of the Bluetooth MAC address, e.g. `xk one Pro_F773` $\rightarrow$ `FA:00:11:12:F7:73`).
* **Manufacturer**: `shenju`
* **Hardware Model**: `w20`
* **Firmware Version**: `1.0.1` / `1.0.2`
* **Camera Module**: Embedded CMOS camera with on-board JPEG encoder (output resolution ~1920x1080 / ~2.2 MB JPEG).
* **Audio**: Dual stereo temple speakers + embedded microphone array.
* **Physical Controls**:
  * Physical camera trigger button (top right temple).
  * Capacitive touch sensor strip (side temple).

---

## 2. Bluetooth Profiles & Channel Mapping

The smart glasses utilize Bluetooth Classic (BR/EDR) and Bluetooth Low Energy (BLE):

| Profile | Channel / UUID | Usage | Status |
|---|:---:|---|:---:|
| **SPP (Serial Port Profile)** | **RFCOMM Channel 8** | Primary binary command channel, control packages (`0x30`), image burst data (`0x4A`), JSON custom payloads (`0x2B`). | **VALIDATED** |
| **HFP (Hands-Free Profile)** | **RFCOMM Channel 1** | Standard AT command interface (`AT+BRSF=157\r`) and SCO audio link for microphone input. | **VALIDATED** |
| **A2DP (Advanced Audio)** | Standard A2DP | High-quality media and TTS audio playback to glasses speakers. | **VALIDATED** |
| **AVRCP (Audio/Video Remote)** | Standard AVRCP | Media control and hardware key relay (`MediaSession` / `KeyEvent`). | **VALIDATED** |
| **GATT (Low Energy)** | `0x1812` (HID), `aaa0`, `fff0` | Auxiliary discovery and pairing triggers. | **VALIDATED** |

---

## 3. Power & Battery Management

* **Battery Querying**:
  * Active query via `1001` returns battery percentage in JSON (`"battery_main"`).
  * Unsolicited events via `57A0` report charging state (0/1) and battery percentage.
* **Charging Interface**: Magnetic pogo-pin connector on inner temple.

---

## 4. Hardware Button & Touch Behavior

1. **Standalone Operation**:
   * If physical capture button is pressed when glasses are not connected to an active SPP session, glasses play local audio prompt: *"Please connect to the app"*.
2. **Active SPP Session**:
   * Glasses emit an unsolicited `C101` (voice/touch) control frame over Channel 8 upon touch gesture.
   * Background physical button presses trigger standard Android `KeyEvent.KEYCODE_CAMERA` / media hook events, captured seamlessly via `MediaSession`.
