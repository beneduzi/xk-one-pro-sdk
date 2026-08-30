# XK Glasses Flutter & Kotlin Example App

A minimal, standalone Android application (Flutter + native Kotlin SPP) demonstrating how to:
1. **Discover and connect** to Shenju XK One Pro / LensMoo smart glasses via Bluetooth SPP (Channel 8).
2. **Display real-time connection state and battery percentage**.
3. **Capture photos on demand** via in-app button or **automatically** when the glasses' hardware/touch button is pressed.
4. **Reassemble the JPEG stream** using the two-layer reassembler and **save it directly to the Android Gallery (`Pictures/XKGlasses`)**.

---

## Prerequisites
* Android device running Android 8.0+ (API 26+).
* XK One Pro smart glasses paired in Android Bluetooth settings (`xk one Pro_XXXX`).

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
