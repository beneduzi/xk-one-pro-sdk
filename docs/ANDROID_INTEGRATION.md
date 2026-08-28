# Android integration

The reference Flutter app uses `android/.../glasses/spp/`:

- `XkCrc16` computes CCITT CRC over payload.
- `XkFrame` encodes/parses headers, validates CRC, and accepts `30`, `4a`, `2b` heads.
- `XkSppClient` owns one RFCOMM socket/reader and sends frames on channel 8.
- `XkSessionTemplates` creates random bind frames, setup frames, keepalive, and photo queries.
- `XkGlassesController` manages states, bind/setup, photo transfer, JPEG checks, reconnect-facing APIs.

`MainActivity` discovers the bonded device by name, constructs the controller, and exposes Flutter methods `glassesConnect`, `glassesDisconnect`, `glassesTakePhoto`, `glassesAudioRouting`, and `glassesState`. It emits `glassesImageDetected` with the saved image path and recognized people; the existing YOLO/face-recognition pipeline is reused. A coroutine reconnect loop retries and otherwise sends keepalive/photo-count queries every three seconds.

Audio routing calls Android `AudioManager.startBluetoothSco()`/`stopBluetoothSco()` and toggles `isBluetoothScoOn`; this is an integration path, not hardware validation.

The camera flow connects, runs bind/setup, requests the photo dialog, validates SOI/EOI, saves a JPEG, then sends it through the same image-detection pipeline. Audio-only flows use connection plus SCO routing without camera processing. This replaces the old Lensmoo `FileObserver` hack: images now arrive through SPP rather than watching a vendor-managed filesystem.

Integration contract: provide a bonded `xk one Pro_F773` device, call connect before capture, keep the session alive, handle reconnect/state errors, accept asynchronous `glassesImageDetected`, and treat capture/audio/button behavior as capability-dependent. The current controller's fixed six-image loop is capture-derived and should be generalized when additional hardware evidence is available.
