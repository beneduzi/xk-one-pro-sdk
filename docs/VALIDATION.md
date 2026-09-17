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
  forwards it verbatim.

**Conclusion:** the firmware validates the value intrinsically (signature/MAC or whitelist).
Only values issued by the vendor's system are accepted. A virgin device rejecting arbitrary values
rules out "first bind wins" and per-bond registration.

---

## 5. Observed response semantics

* `action = 0x8002` — response to a query (`7100`, `1001`, `5713`, ...).
* `action = 0x8001` — unsolicited indication (`57B1`, `7320`, `C101`, `57A0`, ...).
* `action = 0x8004` — ACK.
* ACKs reference the **received** `cmd_order`; TX and RX counters are independent.
* `1001` returns a JSON blob with `battery_main`, `dev_id`, `dev_name`, `mac_addr`, `soft_ver`,
  `screen`, `preview_width/height`.

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
* Battery `57A0`/`57A1` semantics and charging transitions (no charge/discharge test performed).
* A resolution-selection command (none found).
* Long-run keepalive/timeout behaviour.

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

```
0001 0002 1001 1003 1004 1007 1008 1017 102A 102C 102E 1030 1031 1032
3300 4700 5500 5610 5620 5710 5711 5712 5713 5720 5750 5770 5780 57A0 57B0
7200 7300 7310 7400 7500 7600 9000 9001 A001 B001 B002 B003 B004 C109
```

Notable mappings: `1004`/`4700` notifications, `1032` memory info, `5770`/`5780` storage,
`5713` media counts, `57B0` capture, `7300`/`7500` image transfer, `102E` user bind.
