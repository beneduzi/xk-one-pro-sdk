# Reverse Engineering Journey & Protocol Discovery

This document chronicles the step-by-step reverse engineering of the Shenju XK One Pro / LensMoo smart glasses protocol, detailing key breakthroughs, dead ends, and solutions.

---

## 1. Initial Reconnaissance & Bluetooth Enumeration

The investigation began by probing the glasses from Linux:
* **GATT Enumeration (`gatttool`)**: Discovered GATT services `0x1812` (HID), `aaa0`, and `fff0`. While GATT is used during initial pairing, it does not carry high-bandwidth photo data or command streams.
* **Classic Bluetooth (`sdptool` / `bluetoothctl`)**: Revealed multiple RFCOMM channels:
  * Channel 1: Responded with `AT+BRSF=157\r` (standard Hands-Free Profile AT command interface).
  * Channel 8: Carried proprietary binary framing starting with `0x30`, `0x4A`, and `0x2B`.
* **Vendor Logcat Analysis**: Decompiling the vendor application and inspecting logcat logs tagged with `SJ_SDK>>>>>` and `BtEngine` exposed raw hexadecimal packet traces between the phone and glasses.

---

## 2. Framing & CRC Identification

Analyzing smali code in `MsgBean.smali` and `PayloadPackage.smali` established the 16-byte envelope header. 

Key finding:
* **CRC-16/CCITT**: The 2-byte checksum at offset `12..13` is computed **strictly over the payload bytes** (excluding the 16-byte envelope). All 21 captured frames in the initial dataset matched the CRC algorithm with polynomial `0x1021`, initial value `0xFFFF`, and no final XOR.

---

## 3. The `0401` Arming Sequence Discovery

Initial attempts to send standalone photo requests resulted in immediate rejection with status code `0x0401`. 

By comparing traffic traces before and after camera activation, we discovered that the firmware enforces a strict subsystem arming sequence:
1. Two-phase session bind (`0001` with a 61-character alphanumeric token, followed by `0002` with binary payload).
2. A required setup sequence consisting of status queries (`7100`, `7110`), user ID registration (`102E`), custom subsystem initializers (`2B0004` `FGS` and `FND`), and preview capabilities (`2410`, `2420`, `C10A`, `C104`, `57A0`, `5770`, `5713`, `57B0`).
3. Interleaving `300004` ACK/poll frames during setup.

Once this sequence was replayed, all subsequent command responses returned success status `0x0001` / `0x0000`.

---

## 4. Cracking the Two-Layer JPEG Reassembly

The most complex phase was reconstructing valid JPEG photos from the `0x4A` image stream. Initial attempts resulted in corrupt, scrambled images with invalid Huffman tables.

Careful binary differential analysis revealed that the protocol uses **two distinct layers of framing**:

1. **Transport Layer (`0x4A` Frames)**:
   * Frames with `divide_type` 1, 2, or 3 (fragmented packets) prepend a **4-byte little-endian sequence counter (`cmd_idx`)** at the start of each payload.
   * This 4-byte counter was corrupting the raw stream and had to be stripped from every fragment.
   * Frame with `divide_type` 3 marks the final fragment of an element and requires a `4A0009` ACK.

2. **Logical Layer (Elements 1..N)**:
   * Photos are segmented by the camera into $N$ logical elements (queried via `7320`, fetched via `7300`).
   * Each assembled element begins with a **5-byte metadata header** `[length: 4B LE, media_type: 1B]`.
   * Stripping this 5-byte prefix from each assembled element before concatenating slices $1..N$ produced a 100% bit-perfect JPEG starting with `FF D8` and ending with `FF D9`.

---

## 5. Audio Routing & Background Buttons

* **SCO Audio Routing**: The microphone stream was isolated to RFCOMM Channel 1 using Android `AudioManager.startBluetoothSco()`.
* **Hardware Button Interception**: When running in the background, physical button presses trigger standard OS `KeyEvent.KEYCODE_CAMERA` / media hook events, which are intercepted via Android's `MediaSession` API without needing direct SPP polling.

---

## 6. Summary of Deliverables

* **Python SDK (`xkglasses`)**: Clean, standalone, cross-platform client with two-layer `XkImageReassembler`, `XkGlassesClient`, CLI, and unit test suite.
* **Production Kotlin Architecture**: Integrated into the on-device AI vision assistant with real-time YOLO object detection, face recognition, and TTS feedback.
