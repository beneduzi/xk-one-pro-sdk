# Reverse engineering

The work began by enumerating GATT from Linux with `gatttool`, then inspecting Classic Bluetooth with `bluetoothctl` and `sdptool`. Vendor logcat was captured with `adb logcat`; `SJ_SDK>>>>>` and `BtEngine` hex dumps exposed complete request/response traffic.

APK analysis used `apktool` and smali inspection of `MsgBean`, `PayloadPackage`, and `SJUniWatch`. Native `getCrc` led to CRC identification. The `b9`/`bs1` AES paths were dead ends: their presence did not prove that bind bytes were encrypted, and live tests later showed random bind content is accepted.

The decisive breakthrough was scanning all RFCOMM channels. Channel 8 carried `30`/`4a`/`2b` frames; channel 1 only exposed AT/HFP behavior (`AT+BRSF=157`). This corrected an earlier false “bind validation” conclusion caused by testing the wrong channel. A random-token node `0001` and random-binary node `0002` were accepted live.

Comparing pre- and post-reset captures revealed the required setup sequence and constant user ID. Decoding the download dialog established `7320` count, indexed `7300`, `4A0001` bursts, `4A0009` polls, and `7500`. Tooling included `bluetoothctl`, `gatttool`, `sdptool`, `adb logcat`, apktool, and small CRC/frame scripts.

Lessons: scan every RFCOMM channel before inferring validation or cryptography; preserve untruncated hex and timestamps; label hardware evidence separately from capture-derived implementation. Complete JPEG reassembly, audio, and button media-key behavior remain areas requiring dedicated captures/validation.

---

## See also

The bonded-phone enrollment investigation (the `0401` wall), the Lensmoo
instrumentation pipeline and the extracted bind inputs are documented in
**[BONDED_ENROLLMENT.md](BONDED_ENROLLMENT.md)**.
