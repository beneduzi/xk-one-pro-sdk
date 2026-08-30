# Android & Kotlin Integration Guide

This guide documents the native Android / Kotlin architecture implemented in the production `vision-assistant-ondevice` application.

---

## 1. Native SPP Module Architecture

The Bluetooth SPP stack is located under `android/.../glasses/spp/`:

| Component | Class | Responsibility |
|---|---|---|
| **Envelope Codec** | `XkFrame.kt` | 16-byte binary envelope encoding/decoding, channel matching, `divideType` unpacking. |
| **Checksum Engine** | `XkCrc16.kt` | Hardware-accurate CRC-16/CCITT-FALSE implementation over payload. |
| **Transport Client** | `XkSppClient.kt` | RFCOMM socket management on Channel 8, background reader thread, frame dispatching. |
| **Session Templates** | `XkSessionTemplates.kt` | Factory for bind sequences, subsystem setup frames, capture triggers (`57B0`), element downloads (`7300`), ACKs (`300004`, `4A0009`), and keepalives. |
| **Two-Layer Reassembler** | `XkImageReassembler.kt` | Handles fragmented 0x4A bursts, strips 4B transport `cmd_idx` and 5B logical metadata prefixes, and validates final `FFD8..FFD9` JPEG bytes. |
| **High-Level Controller** | `XkGlassesController.kt` | Manages connection states (`IDLE`, `CONNECTING`, `BOUND`, `PHOTO`, `ERROR`), battery queries, capture flows, and event listeners. |

---

## 2. Background Hardware Button Service

To capture physical camera button presses when the screen is locked or the app is in the background, Android's `MediaSession` API is utilized:

* **Service**: `BackgroundHardwareButtonService.kt` (Foreground Service with `FOREGROUND_SERVICE_TYPE_CONNECTED_DEVICE` or `DATA_SYNC`).
* **Mechanism**: Creates an active `MediaSession` handling transport keys (`KeyEvent.KEYCODE_CAMERA`, `KEYCODE_HEADSETHOOK`, `KEYCODE_MEDIA_PLAY_PAUSE`).
* **Notification**: Displays a polished, ongoing status notification (`"Assistente Visual · Óculos Conectado"`) with deep-link quick actions.
* **Dispatch**: Relays button events through `AppHardwareButtonRelay` directly into the Flutter layer via `EventChannel("vision_assistant/hardware_button_events")`.

---

## 3. Audio Routing & Clean TTS/STT Transitions

The glasses support Bluetooth Hands-Free Profile (HFP/SCO) for the microphone and A2DP for the speakers:

* **Microphone Capture**:
  * Enable SCO via `AudioManager.startBluetoothSco()`.
  * Set `AudioManager.isBluetoothScoOn = true`.
  * Listen for `AudioManager.ACTION_SCO_AUDIO_STATE_UPDATED` broadcast until state reaches `SCO_AUDIO_STATE_CONNECTED`.
* **Speaker Playback**:
  * Audio outputs naturally over Bluetooth A2DP when paired.
* **Smooth Transition Loop**:
  * When TTS completes speaking a prompt or response, the app delays briefly (150ms) before opening the SCO recording stream to avoid recording the tail end of the assistant's own voice.

---

## 4. Flutter MethodChannel API Contract

The native Android layer communicates with Flutter through `vision_assistant/native`:

| Method | Parameters | Return | Description |
|---|---|---|---|
| `glassesConnect` | `mac`: String | Boolean | Connects SPP, performs bind, and executes setup sequence. |
| `glassesDisconnect` | None | Boolean | Gracefully tears down SPP session. |
| `glassesTakePhoto` | `timeoutMs`: Long (optional) | `imagePath`: String? | Triggers capture (`57B0`), reassembles JPEG, and saves to cache. |
| `glassesGetBattery` | None | `{"level": Int, "charging": Boolean}` | Queries current battery percentage and charging state. |
| `glassesSetAudioRouting` | `enabled`: Boolean | Boolean | Toggles SCO microphone routing. |
| `glassesState` | None | `{"state": String, "battery": Int}` | Returns current connection and battery state. |

### Real-Time Event Streams

* `vision_assistant/glasses_events`:
  * `{"type": "connected", "mac": "..."}`
  * `{"type": "disconnected"}`
  * `{"type": "battery", "level": 85, "charging": false}`
  * `{"type": "voice_button_pressed"}`
  * `{"type": "photo_captured", "path": "/path/to/cache/xk-123.jpg"}`
