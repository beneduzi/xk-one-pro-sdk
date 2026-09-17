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

## 3. The `0401` Error and What Actually Arms the Camera

Initial attempts to send standalone photo requests were rejected with status code `0x0401`.

Early analysis attributed this to the session bind (a "random blob gets rejected") and described a
long mandatory "arming sequence". **Controlled hardware testing later disproved both:**

* The session bind (`0001`/`0002`) payload content is **not** validated — fully random tokens and
  blobs are accepted repeatedly.
* The long setup sequence is **not** mandatory. A minimal session of `0001` + `0002` + `102E` is
  sufficient to arm the camera and capture a photo; every other setup frame can be omitted.
* The real requirement is the **`102E` user bind**, which carries a fixed 32-hex `userId` that the
  firmware validates offline. An invalid `userId`, or a wrong payload length field
  (`len != len(rest) - 1`), is what produces `0x0401` or a dropped link.

See [BONDED_ENROLLMENT.md](BONDED_ENROLLMENT.md) and [VALIDATION.md](VALIDATION.md).

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

* **Python SDK (`xkglasses`)**: standalone client with the two-layer `XkImageReassembler`,
  `XkGlassesClient`, CLI, and a unit test suite.
* **Kotlin/Android SPP stack**: reference implementation of the envelope codec, session templates,
  two-layer reassembly and controller, exercised against real hardware.
* **Protocol documentation** distinguishing observed behaviour from inference
  ([PROTOCOL.md](PROTOCOL.md)) and the raw physical evidence ([VALIDATION.md](VALIDATION.md)).

> Note: an earlier revision of this document referenced a separate "production" application
> (YOLO detection, face recognition, TTS) that is **not** part of this repository.
