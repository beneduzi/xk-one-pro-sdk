# Physical Validation Report

Raw results from controlled testing against real hardware. This document records **what was
measured**, not what was inferred. Where something is not proven, it says so.

---

## 1. Method

A dedicated harness replays the working session **verbatim** and can mutate **one variable at a
time**, so an A/B/A run isolates the variable under test.

* Baseline frames are replayed byte-for-byte; an offline check verifies that all 35 baseline
  frames decode, pass CRC and re-encode identically.
* Success is defined strictly: a JPEG is downloaded and reassembled, must start with `FF D8` and
  end with `FF D9`, and is then verified with a real image decoder (Pillow).
* A/B/A: run the baseline, run the single mutation, run the baseline again. A mutation is only
  considered meaningful if the surrounding baselines succeed.
* No factory reset, unbind or destructive action is performed without explicit consent.

### Environment

| Item | Value |
|---|---|
| Host | Linux, BlueZ, RFCOMM channel 8 |
| Glasses | `xk one Pro_F773` (`FA:00:11:12:F7:73`), firmware `1.0.2` |
| Link | Bluetooth Classic bonded |
| Harness | private, single-file Python; verbatim replay + mutations |

### Baseline

`0001` + `0002` + setup + `57B0` → `57B1` → `7320(count)` → `7300` × N → `7500`.
Result: valid JPEG, **640x480**, ~74–84 KB, reproducible across many runs.

---

## 2. Session bind (`0001` / `0002`) is not validated

| Mutation (only this changed) | Result |
|---|:---:|
| Bind-1 token fully random | ✅ PASS |
| Bind-2 opaque 32-byte block random | ✅ PASS |
| Bind-2 all 64 data bytes random | ✅ PASS |
| Envelope reserved bytes `[14:16]` set to non-zero | ✅ PASS |
| **Remove the session bind entirely** | ❌ FAIL |
| **Bind-1 length field changed 0x3D → 0x3E** | ❌ FAIL |

**Conclusions:** the bind payload *content* is irrelevant, but the frames themselves and the
exact length field are required. `len = len(rest) - 1`.

---

## 3. The setup sequence is almost entirely optional

Ablation: remove one setup frame per run, keep everything else.

| Frame omitted | Result |
|---|:---:|
| `FGS`, `FND` (both), `C104`, `57A0`, `5713`, `2410`, `2420` | ✅ PASS |
| `7100`, `7110`, `1001`, `1003`, `5770`, `F0600100`, `F0600300` | ✅ PASS |
| **`102E`** | ❌ FAIL |
| **All setup except `102E`** (minimal session) | ✅ PASS |

**Conclusions:** `102E` is the only mandatory setup frame. Everything else is telemetry or
optional capability negotiation. `C104` has no effect on capture resolution.

---

## 4. The `102E` `userId` is validated offline and cannot be synthesised

| Mutation (only the `userId` changed) | Result |
|---|:---:|
| Single hex character changed | ❌ FAIL |
| Upper-case | ❌ FAIL |
| All zeros | ❌ FAIL |
| Random 128-bit value | ❌ FAIL |
| `bindType = SCAN_QR` (0) + random | ❌ FAIL |
| `bindType = DISCOVERY` (1) + random | ❌ FAIL |
| `bindType = CONNECT_BACK` (2) + random | ❌ FAIL |
| After `UNBIND` (4) | ❌ FAIL |
| After a fresh Bluetooth bond | ❌ FAIL |
| **After a factory reset (virgin unit)** | ❌ FAIL |
| Baseline (provisioned `userId`) after each of the above | ✅ PASS |

Additional analysis:

* No checksum/CRC/MAC structure was found inside the 16 bytes.
* The vendor app contains no local hashing of the value (only file MD5), so the validation secret
  is not extractable from the APK.
* The vendor app reads the value from
  `SharedPreferences["device_cache_login_user_id"]`, populated by its account service, and
  forwards it verbatim. That value is the **Lensmoo account id** (`UserInfoBean.id`), used for
  every bind type including first enrollment — see
  [BONDED_ENROLLMENT.md](BONDED_ENROLLMENT.md) §4 for the decompiled call path.

**Conclusion:** the firmware validates the value intrinsically (signature/MAC or whitelist).
Only values issued by the vendor's system are accepted. A virgin device rejecting arbitrary values
rules out "first bind wins" and per-bond registration.

---

## 5. Observed response semantics

* `action = 0x8002` — response to a query (`7100`, `1001`, `5713`, ...).
* `action = 0x8001` — unsolicited indication (`57B1`, `7320`, `C101`, ...).
* `action = 0x8004` — ACK.
* ACKs reference the **received** `cmd_order`; TX and RX counters are independent.
* `1001` returns a JSON blob with `battery_main`, `dev_id`, `dev_name`, `mac_addr`, `soft_ver`,
  `screen`, `preview_width/height`.
* `57A0` returns the **video-preview state**, not a battery level (see §10).

---

## 6. The reference Python client does not work (as of this report)

Running the repository's own Python client against the glasses produces generic 18-byte responses
for every setup frame and then a dropped link (`Transport endpoint is not connected`).

Because the setup frames it sends are verbatim captures, the break is in the **bind frames it
generates**: `build_control` writes `len == len(argument)` (off by one) and writes `request_id`
into the reserved envelope bytes `[14:16]`. Both are corrected in the SDK update plan.

---

## 7. Not verified

* Behaviour on other firmware versions or hardware revisions.
* Whether a `userId` issued for a *different* vendor account is accepted (no second valid sample).
* The exact cryptographic construction of the `userId`.
* Battery `57A0`/`57A1` semantics — `57A0` is the video-preview state, and the battery/charging
  node is `1003` (see §10). Battery **level** and **charging** are both verified; only the
  8 padding bytes of the `1003` payload remain unexplained.
* A resolution-selection command (none found).
* Long-run keepalive/timeout behaviour.

---

## 8. `flutter_example` builds and tests clean

The bundled Flutter example is the reference Android integration (Kotlin SPP stack + Dart UI).

| Check | Command | Result |
|---|---|---|
| Static analysis | `flutter analyze` | ✅ No issues found |
| Widget tests | `flutter test` | ✅ All tests passed |
| Android build | `flutter build apk --debug` | ✅ `build/app/outputs/flutter-apk/app-debug.apk` |
| Kotlin unit tests | `./gradlew test` | ✅ `BUILD SUCCESSFUL` (debug/profile/release variants) |
| Install on device | `adb install -r -t` | ✅ installed on the MI 9 |
| Launch on device | `monkey … LAUNCHER` | ✅ `MainActivity` focused, no errors in logcat |

Environment: Flutter 3.41.9 stable, Android SDK 35.0.0, Gradle 8.14. `ANDROID_HOME` must point at
the SDK (e.g. `$HOME/Android/Sdk`); the toolchain otherwise reports a missing `cmdline-tools`.

### Installing on MIUI

`adb install` on the MI 9 fails with `INSTALL_FAILED_USER_RESTRICTED: Install canceled by user`
(MIUI's "Install via USB" guard). Disabling the package verifier on the (isolated, test) device
works around it without any on-device toggle:

```
adb shell settings put global verifier_verify_adb_installs 0
adb shell settings put global package_verifier_enable 0
adb install -r -t <apk>
```

The package installs as `com.example.xkglasses.flutter_example` and launches with its
`MainActivity`; the UI renders the connection, capture and status cards as expected.

> **Still pending:** the full end-to-end capture **from the phone**. The example currently reports
> *"Nenhum dispositivo Bluetooth pareado encontrado"* because the glasses are bonded to the PC, not
> to the MI 9 — the Python CLI remains the validated control path (see §2–§5). Running the
> end-to-end flow on the phone requires re-pairing the glasses with the MI 9.

---

## 9. Video / audio extraction: negative result

Extracting recorded video or audio over the protocol was investigated and **not achieved**.

Evidence gathered:

* **Protocol**: the vendor SDK contains a video-preview subsystem (`AbVideoPreview`,
  `toggleVideoPreviewPicture` → node `102A`, `toggleVideoPreviewShoot`) and video frames are
  parsed as `MsgBean` with `divideType == 5` into `WmVideoFrameInfo`. The `5713` reply reports
  `video_num` / `record_num`.
* **Commands**: `102A` and `102C` were sent (with and without arguments, `action` 2/3, minimal and
  full setup). The device only ACKs them; no frames are emitted.
* **Video-preview open/close (`5710`)**: the SDK's `toggleVideoPreview(boolean)` maps to `5710`
  ("App 发起5710 video preview 事件", open/close). Both `arg = 0x01` (open) and `arg = 0x00`
  (close) were sent live and the device replied with the generic **no-op status**
  (`[type=0x04][len=1][0x04]`), the same reply the unimplemented `C10x` camera-control nodes give.
  No `divideType == 5` frames arrived in 15–20 s of listening on either attempt. The glasses do
  **not** implement video preview over SPP.
* **Gestures**: with an active SPP session, a 2-press gesture (video per the sibling W600 manual)
  produced **no** stored media — `5713` stayed at `video_num = 0`, `record_num = 0`, and
  `5712` reported `remain_memory == total_memory` (nothing written).
* **WiFi**: vendors advertise WiFi 6 (2.4 GHz) for "instant photo and video transfer". A WiFi scan
  from the host found **no access point** from the glasses.
* **BLE**: no BLE advertisement was observed; the device exposes only Bluetooth Classic profiles
  (SPP, A2DP, AVRCP, HFP, PnP). No GATT services were resolvable.
* **Vendor app**: public reviews of the Lensmoo app consistently state that video and audio
  recordings **cannot be downloaded** by the app, and that the official workaround (connecting the
  glasses to a computer over USB) is reported as charge-only.

**Conclusion:** recorded video/audio are kept in the glasses' internal flash and are **not exposed
through the SPP protocol**. Retrieving them would require hardware access (flash dump). Photos,
by contrast, transfer reliably (see §1–§3).

> The sibling **VIVO W600** manual (same Lensmoo app family) documents the button gestures:
> 1 press = photo, **2 presses = video recording** (1 press to stop), long press 3 s = power.

The vendor application (`com.lensmoo.app`) was decompiled and its command builders mined for node
codes. **45 node codes** were recovered, together with the request-type enum and the settings
sub-command map. Note that the vendor SDK is **shared with smartwatch products**
(`WmDeviceModel.SJ_WATCH`), so many nodes belong to watch features and are not applicable to
these glasses.

### Request types

`RequestType`: `0 = INVALID`, `1 = READ`, `2 = WRITE`, `3 = EXECUTE`, `4 = NOTIFY`.
This is the value carried in the control payload `action` field.

### Settings node `1017`

The settings are read and written through node `1017`:

* **Read**: `1017`, `action = 1`, empty data. The device replies with a 4-byte bitmask.
  Observed value on the validated unit: `1f 00 00 00`.
* **Write**: `1017`, `action = 2`, data `[sub_id:1][value:1]`.

Sub-command map (from `SettingSoundAndHaptic.kt` / `SettingWistRaise.kt`):

| sub_id | Setting |
|:---:|---|
| 0 | ringtone enabled |
| 1 | notification haptic |
| 2 | crown haptic |
| 3 | system haptic |
| 4 | wrist-raise screen wake (watch only) |
| 5 | muted |

**Result: the write did not change the observed read value** (`1f 00 00 00` before and after),
and the device's voice prompts remained audible. The official application exposes **no** sound
setting in its UI, which suggests the glasses do not surface this subsystem.

### Resolution

No resolution, image-size or quality command exists in the vendor SDK (no node, no entity field,
no string), `C104` has no measurable effect, and the settings do not expose one. The transferred
JPEG is 640x480 on the validated unit. **Resolution is treated as firmware-fixed.**

### Voice prompts

The prompts (e.g. *"please connect"*, *"power off"*) are generated by the glasses firmware. They
were **not** silenced by any setting found. The only remaining lever is audio volume: the glasses
advertise A2DP (`0x110B`) and AVRCP (`0x110C`/`0x110E`), so the phone's media volume may control
the speaker. This was **not** verified.

### Node inventory (from the vendor SDK)

The complete inventory is **68 nodes**, enumerated mechanically from the two node builders
(`l9c.k(BBBB)` and the `l9c.r(...)` default-argument bridge) in the decompiled Lensmoo APK. See
`docs/NODES.md` §7 for the full table.

Notable mappings: `1004`/`4700` notifications (both no-ops on the glasses), `5712` memory info,
`5770`/`5780` storage, `5713` media counts, `57B0` capture, `7300`/`7500` image transfer,
`102E` user bind.

Nodes from the vendor table that were **probed on hardware but produced no matching reply**:
`1008` `1030` `1031` `1032` `3300` `4700` `5500` `5610` `5620` `5710` `5711` `5720` `5750` `7200`
`7310` `7400` `7600` `9000` `A001` `B001`–`B004` `C101` `C104`.

The watch-only nodes (`2100`–`5410`, `A000`) were **not** probed; none of them ever appeared in
any capture. They are classified from the SDK's entity types only.

---

## 10. Live re-validation and `57A0` correction

The unit was re-paired to the host and the full flow re-run end to end.

### End-to-end still works

`python -m xkglasses.cli --mac … capture` → **75 061 bytes**, valid JPEG, 640×480, 3 components.
`… battery` → **100 %**.

### Device info (`1001`), live

```json
{"prod_mode":"E13C-1","soft_ver":"1.0.2","mac_addr":"FA:00:11:12:F7:73",
 "dev_id":"TBZNDZAIEYE-W20-------E13C1-----------FA001112F773896775--------",
 "dev_name":"xk one Pro_F773","prod_category":"01","prod_subcate":"01",
 "battery_main":"100","dial_ability":"2","screen":"w320h380",
 "ch":"304","cw":"320","nch":"304","ncw":"320","screen_shape":"0",
 "preview_width":"160","preview_height":"120","offline_asr_auth":"1"}
```

Two things worth noting: the `dev_id` embeds **`W20`** (the sibling W20 family this firmware is
derived from), and the advertised preview is **160×120** while the transferred JPEG is
**640×480** (4× the preview in each axis).

### Other node reads

| Node | Reply | Reading |
|---|---|---|
| `1017` | `[type=0x00][len=4][1f 00 00 00]` | settings bitmask = `0x0000001f` (bits 0–4 set) |
| `5712` | `{"total_memory":665338288,"remain_memory":665338288}` | ~634 MB, nothing stored |
| `5713` | `{"photo_num":"0","video_num":"0","record_num":"0","music_num":"0"}` | no stored media |
| `C101` `C104` `C107` `C109` `C10A` | `[type=0x04][len=1][0x04]` | identical no-op status — camera-control nodes are not implemented |
| `1003` | `[type=0x00][len=10][01 64 00 00 00 00 00 00 00 00]` | **battery**: `is_charging = 1`, `battery_main = 100` (see below) |
| `57A0` | `[type=0x00][len=1][0x00]` | video-preview state = off (see below) |

The identical `0x04` status from all five `C10x` nodes (and the same value for `1004`) confirms
they are recognised-but-unimplemented: the firmware answers a fixed status instead of data.

### Correction: `1003` is the battery node, and `is_charging` **is** available

`1003` had been mislabelled "firmware (10-byte data block)". It is the **battery status** node.

* **SDK evidence**: `SJUniWatch.commonBusiness()` dispatches on `urn[1]=='0'`, `urn[2]=='0'`,
  `urn[3]=='3'` → node `X003` → `batteryBackBusiness(NodeData)`. That method requires
  `FMT_BIN` and reads `data[0]` as `is_charging` and `data[1]` as `battery_main` into
  `BatteryBean`.
* **Live evidence**: `1001.battery_main = 100` and `1003 → is_charging = 1, battery_main = 100`
  in the same session.
* **Historical evidence**: across captures both flag values appear with a coherent level —
  `is_charging = 0` at 95/97/100 and `is_charging = 1` at 95/96/98/100 — so the flag is real,
  not a constant.

An earlier note in this document claimed there was *no* charging flag in the protocol. That was
**wrong**; it was based on `1001` alone, which genuinely has no such field. Charging comes from
`1003` only.

### Correction: `57A0` is the video-preview state, not the battery

Earlier notes (and `client.py`) treated `57A0` as a battery push. That is also wrong.

* **SDK evidence**: `Wlc` extends `AbVideoPreview`. Its `57A0` builder (`w()`) is called from the
  handler that logs *"App get video preview 事件"*, and the reply parser reads `NodeData.data[0]`
  as the preview state, logging *"device video preview state"*.
* **Live evidence**: while `1001` reported `battery_main = 100`, the `57A0` reply data byte was
  `0x00` — parsing it as a level yields `0 %` on a full battery.

Fix applied: `client.py` no longer derives battery from `57A0`; it exposes the preview state via
`preview_state` / `on_preview_state`. Battery level and charging come from `1003` (and the level
also from `1001`). Regression tests: `test_57a0_does_not_overwrite_battery`,
`test_1003_reports_level_and_charging`.

### Reply layout (re-confirmed)

For a `0x30` reply, after the 4-char node at `payload[10:14]`:

```
[type:1] [len:2 LE] [data: len bytes]
```

`type = 0x00` raw data, `0x02` JSON, `0x04` one-byte status/error. This was verified against
`1001` (type `0x02`, len `0x019b` = 411), `5712` (len 52), `5713` (len 66), `1017` (type `0x00`,
len 4) and the `C10x` no-ops (type `0x04`, len 1).

> `len` is little-endian. The previous note in §5 that read "`1001` returns a 410-byte JSON" should
> read **411**.

---

## 11. Keepalive, timeout and the `0x2B` custom channel

### No SPP keepalive is required

After `bind` + setup the session was left **completely idle — zero frames in either direction — for
240 s**, then probed:

| Probe after 240 s of silence | Result |
|---|---|
| `1001` device-info query | ✅ answered — link alive |
| `57B0` capture trigger | ✅ `57B1`/`7320` received — control path alive |

No device-initiated traffic occurred during the idle window either. So the glasses neither require
nor send a protocol keepalive, and the `0004` "keepalive" frames in the setup template are
unnecessary. The vendor app's `com.starburst.sdk.core.keepalive` module is unrelated: it is Android
background-process persistence (MIUI/Huawei/Vivo autostart helpers, wake locks, alarms).

Not characterised: multi-day idleness, and whether the glasses' own auto-power-off (independent of
the link) intervenes first.

### `0x2B` is the voice-assistant auth channel, not media

Frames with `head = 0x2B` carry `FGS`/`FND` JSON and are handled by
`com.starburst.sdk.core.auth.BtAuthDataHandler`. The surrounding `com.starburst.sdk.core` package is
a voice-AI stack (`asr`, `tts`, `voicechat`, `opus`, `recorder`, `wssmessage`, `multimodal`).

`FGSInfoConfig` holds an **Alibaba Cloud (Aliyun) IoT device triple** — `sProductKey`,
`sDeviceName`, `sDeviceSecret` — plus `sTimeStamp` and `sonce`. `FGS` message types are
`START_FGS_REQ/RESP`, `START_LP_AUTH_REQ/RESP` and `DS_DOWNLOAD_REQ/RESP`.

Live, fully decoded response:

```json
{"sid":"FGS","data":"{\"msg_type\":\"FGS_MSG_TYPE_START_FGS_RESP\",
  \"tripplestatus\":\"existtripple\",\"sidver\":1,\"sdk_ver\":\"1.0.0\"}","ver":1}
```

`"tripplestatus":"existtripple"` proves the glasses already store their IoT triple. `FND` carries a
base64 blob decoding to `01 0d 00` + an ASCII microsecond timestamp
(`"AQ0AMTc4OTY3NjIwMjQ3MTQ2NA=="` → `1789676202471464`). `Sid` values: `CCM`, `FGS`, `FND`, `GTD`,
`TKN`.

**Consequence:** the whole `0x2B` channel can be omitted by a photo-only host (already established
by ablation), and it offers no route to stored video/audio — see §9. Full details in
[PROTOCOL.md](PROTOCOL.md) §9.

---

## 12. Argument / action sweep: negative result

The `ErrorCode` enum (§10) separates "node not implemented" (`ERR_CODE_INVALID_URN`) from
"recognised but called wrongly" (`ERR_CODE_INVALID_PARAM`, `ERR_CODE_INVALID_DATA`). The latter two
were worth retrying with arguments, since the vendor SDK models them as structured writes.

Every combination was sent in a **fresh session** (the device answers a given node only once per
session), with the RFCOMM channel allowed to be released between runs.

| Node | Combinations tried | Result |
|---|---|---|
| `5780` | `action 1` with no arg, `00`, `01`, `02`; `action 2` with `00` | always `ERR_CODE_INVALID_PARAM` |
| `9001` | `action 1` with no arg, `00`, `0000`; `action 2` with `00` | always `ERR_CODE_INVALID_DATA` |
| `9000` | `action 1` / `action 2` with `00` | always `ERR_CODE_INVALID_URN` |
| `1007` | `action 1` / `action 3` with `00` | always `ERR_CODE_INVALID_URN` |

**Conclusion:** none of these four nodes becomes usable through a simple single-value query. The
error code does not change with the argument or the action, so:

* `9000` and `1007` are **not implemented** in this firmware (plain `INVALID_URN`).
* `5780` and `9001` are recognised but reject the simple query form. They are modelled in the SDK
  as item-list / package-based writes (`PayloadPackage` with `itemList`, `packageSeq`,
  `packageLimit`), so they would need a full multi-item package rather than a one-byte argument.
  Reaching them is out of scope for a photo-capture host.

> Operational note: opening sessions back-to-back **in the same process** fails with
> `OSError: [Errno 16] Device or resource busy` after the first one, even with delays and retries.
> A fresh process per session always works. Any future sweep should therefore fork per request.

---

## 13. Raw sensor streaming: negative result

The vendor SDK models a raw motion channel — `WmSensorDataRequest` / `WmSensorDataResponse` with a
G-sensor at 25 / 50 / 100 Hz. It was worth testing because it is the only modelled feature that
would add a genuinely new capability over SPP.

The builders were decoded first (`com.android.mltcode.paycertificationapi.eic`):

| Node | Builder | Payload |
|---|---|---|
| `A000` | `eic.e(WmSensorDataRequest)` | `[sensorType:1][sensorFrequency:1]`, `FMT_BIN` — `0` = `G_SENSOR`, freq `0`/`1`/`2` = 25/50/100 Hz |
| `A001` | `eic.f(boolean)` | `[flag:1]`, `FMT_BIN` — start/stop |

Live results on the validated unit:

| Node | Payload | Action | Reply |
|---|---|---|---|
| `A000` | `00 02` (G_SENSOR @100 Hz) | 3 | `ERR_CODE_INVALID_URN` |
| `A000` | `00 02` | 1, 2 | `ERR_CODE_INVALID_URN` |
| `A001` | `01` (start) | 3 | `ERR_CODE_INVALID_URN` |
| `A001` | `01` | 1, 2 | `ERR_CODE_INVALID_URN` |

Every combination returned the same `FMT_ERRCODE / ERR_CODE_INVALID_URN`, and no data frames of any
kind arrived during 12 s of listening after each request.

**Conclusion:** `A000`/`A001` are **not implemented** in this firmware. The glasses do **not**
expose raw accelerometer/motion data over SPP. This is consistent with `WmFunctionSupport` having
no sensor-related capability flag.

> Note: the request used `action 3` (EXECUTE) as well as 1/2, so this is not an
> argument-or-action problem — the URN itself is rejected.
