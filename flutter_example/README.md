# XK Glasses Flutter & Kotlin Example App

A minimal Android application (Flutter + native Kotlin SPP) demonstrating how to:
1. **Discover and connect** to Shenju XK One Pro / LensMoo smart glasses via Bluetooth SPP (Channel 8).
2. **Display real-time connection state and battery percentage**.
3. **Capture photos on demand** from the app, and react to the glasses' hardware/touch events.
4. **Reassemble the JPEG stream** using the two-layer reassembler and save it to the Android Gallery.

> **Status**: reference/example code, validated against real hardware for connect → bind → capture
> → download. It is **not** a production app — see the caveats below.

---

## Prerequisites
* Android device running Android 8.0+ (API 26+). On API 31+ the `BLUETOOTH_CONNECT` **runtime**
  permission must be requested before scanning or connecting.
* XK One Pro smart glasses paired in Android Bluetooth settings (`xk one Pro_XXXX`).
* A valid `userId` for the `102E` bind command (see
  [../docs/BONDED_ENROLLMENT.md](../docs/BONDED_ENROLLMENT.md)). Without it the session is
  rejected by the firmware. The value used here is a provisioned family identifier, not a
  placeholder you can invent.
* Photos are written to the app cache and then copied to the gallery; on older Android versions
  this requires storage permission.

### Known limitations of the example
* The app does not request runtime Bluetooth permissions itself on API 31+.
* "Automatic" capture reacts to in-session `C101`/`57B1`/`7320` frames; true background capture
  (screen locked, app killed) would require a foreground service that owns the SPP session.
* Capture resolution is firmware-fixed (~640x480 on the validated unit); `C104` does not change it.

---

## How to Run

```bash
cd flutter_example
flutter pub get
flutter run
```

---

## Architecture

* `lib/main.dart` — Clean Flutter Material 3 UI with connection controls, battery indicator, and live photo preview.
* `android/app/src/main/kotlin/com/example/xkglasses/spp/` — Complete native SPP stack:
  * `XkSppClient.kt`: RFCOMM socket and frame parser on Channel 8.
  * `XkFrame.kt` & `XkCrc16.kt`: 16-byte protocol envelope codec with CRC-16/CCITT-FALSE.
  * `XkSessionTemplates.kt`: Session bind sequence and subsystem setup sequence.
  * `XkImageReassembler.kt`: Two-layer JPEG reassembly engine (strips 4B transport `cmd_idx` and 5B logical metadata prefixes).
  * `XkGlassesController.kt`: High-level controller.
* `MainActivity.kt` — MethodChannel / EventChannel bridge and Android `MediaStore` gallery saver.
