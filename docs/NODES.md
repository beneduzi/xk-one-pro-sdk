# Command & Node Inventory

Inventory of the commands mapped for the Shenju XK One Pro / XK-W202 glasses family, with an
explicit confidence level for each entry. This is **not** a vendor specification: most entries
were recovered from the vendor application and only some were exercised against real hardware.

Confidence legend:

| Mark | Meaning |
|:---:|---|
| ✅ | **Confirmed on hardware** — exercised end-to-end against a real unit |
| 🟡 | **Observed** — the device answered, but the semantics are only partly understood |
| 🔵 | **Mapped from the vendor SDK** — the node exists and its builder was located; the function is inferred |
| ⌚ | **Watch-only** — present in the shared SDK (`WmDeviceModel.SJ_WATCH`), not expected on the glasses |
| ❌ | **Absent** — searched for and not found |

See [VALIDATION.md](VALIDATION.md) for the raw experiments behind the ✅ entries.

---

## 1. Enumerations

### `RequestType` (control payload `action` field)

| Value | Name |
|:---:|---|
| 1 | `READ` |
| 2 | `WRITE` |
| 3 | `EXECUTE` |
| 4 | `NOTIFY` |

### `bindType` (inside the `102E` payload)

| Value | Name |
|:---:|---|
| 0 | `SCAN_QR` |
| 1 | `DISCOVERY` |
| 2 | `CONNECT_BACK` (used by the working session) |
| 3 | `DISCONNECT` |
| 4 | `UNBIND` (also removes the Bluetooth pairing) |
| 5 | `POWEROFF` |

---

## 2. ✅ Confirmed on hardware

| Function | Node / frame | Notes |
|---|---|---|
| Session bind | `0001` + `0002` | Required; payload content is **not** validated (random works) |
| User bind | `102E` | Required; carries the fixed, firmware-validated `userId` |
| Bind/unbind by type | `102E` + `bindType` | See enum above |
| Capture trigger | `57B0` | Shutter; answers `57B1` then `7320` |
| Element count | `7320` | Unsolicited indication with element count (1..20) |
| Element request | `7300` | Fetches element *i*; answered by a `0x4A` burst |
| Image transport | `0x4A` frames | `divide_type` 1/2/3 with a 4-byte LE `cmd_idx` prefix |
| Burst ACK | `4A0009` | Sent on the final fragment (`divide_type 3`) |
| End transfer | `7500` | Closes the image session |
| JPEG reassembly | 2 layers | Strip 4B `cmd_idx` + 5B metadata → 640x480 JPEG |
| Device info + battery | `1001` | JSON: `prod_mode`, `soft_ver`, `mac_addr`, `dev_id`, `dev_name`, `battery_main`, `screen`, `preview_*`, `offline_asr_auth` |
| Media counts | `5713` | JSON: `photo_num`, `video_num`, `record_num`, `music_num` |
| Settings (read) | `1017` | Returns a 4-byte bitmask |
| Generic ACK | `0004` | Payload `[0x01, received_order]` |

---

## 3. 🟡 Observed (semantics partial)

| Node | What is known |
|---|---|
| `7100` | Device status (16-byte data block) |
| `7110` | Device capabilities |
| `1003` | Firmware (10-byte data block) |
| `5712` | **Memory info** — JSON `{"total_memory":N,"remain_memory":N}` |
| `57A0` | **Video-preview state** — empty-payload query; reply `data[0]` = state (0 = off, 1 = on). Not battery (see §3 note) |
| `5770` | Storage capacity |
| `5780` | Answers with a short status block (`…0401 0003`); likely unsupported |
| `1004` | Answers with a short status block (`…0401 0004`) |
| `C107` | Answers with a short status block (`…0401 0004`) |
| `C109` | Answers with a short status block (`…0401 0004`) |
| `C10A` / `C104` | Camera control; `C104` does **not** change resolution |
| `2410` / `2420` | Preview parameters |
| `2B` custom | `FGS`, `FND`, `F0600100`, `F0600300` — all optional |
| `C101` | Touch / voice button event |
| `5710` | **Video-preview open/close** (`toggleVideoPreview`); replies with the `0x04` no-op status — preview is **not implemented** on this unit (see [VALIDATION.md](VALIDATION.md) §9) |
| `5760` | Emitted by the device **after** an image transfer completes (`7500`); not present in the vendor SDK's node table |

### Physical button gestures (observed on hardware)

| Gesture | Action |
|---|---|
| **1 click** on the capture button | Photo capture (`57B0` path: `57B1` → `7320` → elements) |
| **2 clicks** | **Voice recording** (audio memo; counted by `record_num` in `5713`) |

> The glasses require an **active SPP session** for the button to work; otherwise they play a
> local "please connect to the app" prompt. If the host does not complete the transfer (ACK the
> `7320` announcement and download the elements), **the glasses stay blocked waiting for the
> acknowledgement**. A host must therefore always finish (or abort with `7500`) the transfer.
>
> Voice recordings and videos are counted by `5713` (`record_num`, `video_num`); the audio
> subsystem is exposed as `toggleAudio` / `observeAudioState` in the SDK.

> **Probing notes.** The device answers most nodes **once per session**, and several nodes
> (`7100`, `7110`, `2410`, `2420`, `C10A`, `57A0`, `5770`) only reply when queried in the
> context/order of the full setup sequence — a standalone query is ignored. Nodes that require an
> argument do not answer an argument-less query.
>
> **Reply layout** (bytes after the node in a `0x30` reply): `[type:1][len:2 LE][data]`.
> `type = 0x02` means data follows (e.g. `1001` returns a 410-byte JSON, `5712` a 52-byte JSON);
> `type = 0x04` means a one-byte status/error code follows instead of data. Nodes returning
> `0x04` are recognised by the device but produce no usable data:
> `1004` (→ `04`), `1007` (→ `04`), `5780` (→ `03`), `9001` (→ `05`), `C107` (→ `04`),
> `C109` (→ `04`).

---

## 4. 🔵 Mapped from the vendor SDK (function inferred)

| Node | Probable function |
|---|---|
| `1004`, `4700` | Notification settings (`WmNotification`, `WmNotificationSetting`) — `1004` replies with a no-op status, `4700` is silent |
| `1007` | Date-time sync (`WmDateTime`) |
| `1008` | SDK settings (`SJUniWatch`) |
| `102A`, `102C`, `5610`, `5620` | Video control / frame info (`WmVideoFrameInfo`) |
| `5710` | Video-preview open/close (`toggleVideoPreview`) — not implemented |
| `5711`, `5720`, `5750` | Media / camera module (`WmVideoFrameInfo`) |
| `7200`, `7300`, `7310`, `7400`, `7500`, `7600` | Image / video transfer (`WmVideoFrameInfo`) |
| `9000`, `9001` | Media transfer control |
| `3300` | Watch dials (`WmDial`) — same builder as the watch-only `3100`/`3200` |
| `5500` | Unidentified (builder class has no entity type) |
| `A001` | Raw sensor data (`WmSensorDataResponse`) |
| `B001`–`B004` | Muslim prayer reminders |
| `1030`, `1031`, `1032` | Unidentified |
| `C109` | Camera control (ad-hoc, not in the builder table) |

Node → feature mapping above is derived from the entity types each builder class references; see
§7 for the full 68-node table.

### Settings sub-commands (`1017`)

| sub_id | Setting |
|:---:|---|
| 0 | ringtone enabled |
| 1 | notification haptic |
| 2 | crown haptic |
| 3 | system haptic |
| 4 | wrist-raise screen wake ⌚ |
| 5 | muted |

> The write path was ACKed by the device but did not change the observed bitmask, and did not
> silence the device voice prompts.

---

## 5. ⌚ Watch-only (shared SDK, not expected on the glasses)

These nodes come from the *shared* SJ/WM SDK and only make sense on a smartwatch. They were
enumerated from the vendor SDK's node builders (see §7) and none of them appeared in the
captured working glasses session.

| Node | Feature | Entity |
|---|---|---|
| `2100` | Sport goal | `WmSportGoal` |
| `2200` | Personal info | `WmPersonalInfo` |
| `2300` | Unit info | `WmUnitInfo` |
| `2500` | Sedentary reminder | `WmSedentaryReminder` |
| `2600` | DND / reminder window | `WmNoDisturb`, `WmTimeRange` |
| `3100`, `3200` | Watch dials | `WmDial` |
| `4110` | Alarms | `WmAlarm` |
| `4230` | Sport modes | `WmSport` |
| `4320`, `4330` | Contacts / emergency call | `WmContact`, `WmEmergencyCall` |
| `4410`, `4420` | Weather / location | `WmWeather`, `WmLocation` |
| `4500` | Heart-rate alerts | `WmHeartRateAlerts` |
| `4600` | Sleep settings | `WmSleepSettings` |
| `4900` | Widgets | `WmWidget` |
| `5110`, `5120`, `5210`, `5220` | Find device / find phone | `WmFind` |
| `5410` | Music control | `WmMusicInfo`, `WmMusicControlType` |
| `A000`, `A001` | Raw sensor data | `WmSensorDataRequest`, `WmSensorDataResponse` |
| `B001`–`B004` | Muslim prayer / Allah reminders | `PrayRemind`, `WmAllah` |

None of these nodes was ever sent by the glasses or answered a query. They are classified as
watch-only from the entity types their builder classes reference, not from hardware probing.

> **Also in the SDK frame set but silent on the glasses** (probed with no matching reply):
> `3300`, `4700`, `5500`, `1008`, `1030`–`1032`, `5610`, `5620`, `5711`, `5720`, `5750`,
> `7200`, `7310`, `7400`, `7600`, `9000`, `C101`, `C104`.

> **Shared with the glasses** (present in the captured working session, so *not* watch-only):
> `2410`/`2420` (language, `WmLanguage`), `7100`/`7110` (status / capabilities),
> `1007` (date-time, `WmDateTime`), `1004` (replies with an 18-byte no-op status block).

---

## 6. ❌ Absent

* **Resolution / quality control** — no node, entity field or string exists in the SDK; `C104` has
  no measurable effect. Resolution is treated as firmware-fixed (~640x480 on the validated unit).
* **Voice-prompt control** — no setting found; `1017` sub 5 (`isMuted`) does not silence prompts.
* **Audio routing over SPP** — audio uses HFP/SCO and A2DP, outside this protocol.

---

## 7. 📋 Complete vendor node table (68 nodes)

Every node the vendor SDK can build, enumerated mechanically from the two node builders in the
decompiled Lensmoo APK:

* **`l9c.k(BBBB)[B`** — packs four ASCII bytes; called directly with the node name.
* **`l9c.r(l9c;BBBBILjava/lang/Object;)[B`** — the Kotlin default-argument bridge over `k`; the
  fourth byte defaults to `0x00`, so `[0x33,0x31,0x00,0x00]` is node `3100`.

Scanning all call sites yields **42** direct nodes and **26** bridge nodes (no overlap) = **68**.

| Builder class | Nodes | Scope / feature |
|---|---|---|
| `l9c` (core) | `0001` `0002` `1001` `1003` `1017` `102E` `1030` `1031` `1032` `5712` `5713` `7100` `7110` | session bind, device info, settings, user bind, memory, media counts, status, capabilities |
| `kcc` | `1007` | date-time (`WmDateTime`) |
| `SJUniWatch` | `1008` | SDK settings |
| `chc` | `1004` `4700` | notification / notification settings |
| `yac` | `102A` `102C` | video control (ACK-only, see §6) |
| `nlc` / `wlc` | `5710` `5711` `5720` `5750` `5770` `5780` `57A0` `57B0` | media / camera module |
| `jfc` | `5610` `5620` | video frame info |
| `xhc` | `7200` `7300` `7310` `7400` `7500` `7600` | image / video transfer |
| `i7c` | `9000` `9001` | media transfer control |
| `eic` | `A000` `A001` | raw sensor data |
| `ogc` | `B001` `B002` `B003` `B004` | Muslim prayer / Allah reminders |
| `bdc` | `3100` `3200` `3300` | watch dials |
| `lfc` | `2100` | sport goal |
| `ncc` | `2200` | personal info |
| `vfc` | `2300` | unit info |
| `cec` | `2410` `2420` | language |
| `edc` | `2500` | sedentary reminder |
| `bbc` | `2600` | DND / reminder window |
| `d9c` | `4110` | alarms |
| `lic` | `4230` | sport modes |
| `wbc` | `4320` `4330` | contacts / emergency call |
| `bmc` | `4410` `4420` | weather / location |
| `bcc` | `4500` | heart-rate alerts |
| `rdc` | `4600` | sleep settings |
| `imc` | `4900` | widgets |
| `pdc` | `5110` `5120` `5210` `5220` | find device / find phone |
| `tfc` | `5410` | music control |

Nodes in §2/§3 that are **not** in this table (`57B1`, `7320`, `C101`, `C104`, `C107`, `C10A`,
`C109`) are handled outside the node builder — they are parsed from replies or built ad-hoc by the
session code, which is why they never appear as builder constants.

---

## 8. Capability bitmask (function support)

The `7100`/`7110` replies carry a **128-bit capability mask**. The reply data (after the format
byte) is laid out as:

```
[version:1][capability mask: 16 bytes][maxContacts:2][sideButtonCount:1][fixedSportCount:1][variableSportCount:1]
```

Observed on the validated unit (identical across sessions, so these are static capabilities):

| Node | version | capability mask | maxContacts | sideButtons | fixedSport | varSport |
|---|---|---|---|---|---|---|
| `7100` | `0x10` | `ffff4b0a5fa30d040000000000000000` | 100 | 2 | 8 | 12 |
| `7110` | `0x10` | `37000000000000000000000000000000` | 100 | 2 | 8 | 12 |

`sideButtonCount = 2` matches the glasses' two physical buttons.

### Bit → function map (extracted from the vendor SDK)

| bit | function | bit | function |
|:---:|---|---|:---:|---|
| 0 | weather | 32 | step goal |
| 1 | sport | 33 | calorie goal |
| 2 | heart rate | 34 | activity-duration goal |
| 3 | camera control | 35 | sedentary reminder |
| 4 | notify msg | 36 | drink-water reminder |
| 5 | alarm | 37 | wash-hands reminder |
| 6 | transfer music | 38 | auto rate |
| 7 | contact | 39 | REM |
| 8 | find device | 40 | multi-sport |
| 9 | find phone | 41 | show fix motion type |
| 10 | app view | 42 | sport auto-recognise start |
| 11 | set ring | 43 | sport auto-recognise end |
| 12 | set notify touch | 44 | alarm label |
| 13 | set crown touch | 45 | alarm remark |
| 14 | set system touch | 46 | world clock |
| 15 | wrist screen | 47 | app change language |
| 16 | blood oxygen | 48 | widgets |
| 17 | blood pressure | 49 | app control volume |
| 18 | blood sugar | 50 | quiet HR alert |
| 19 | sleep | 51 | sport HR alert |
| 20 | transfer ebook | 52 | daily HR alert |
| 21 | slow mode | 53 | continuous oxygen |
| 22 | camera preview | 54 | BT disconnect reminder |
| 23 | video transfer | 55 | BT/BLE same name |
| 24 | payee code | 56 | event reminder |
| 25 | dial market | 57 | screen reminder |
| 26 | unfold notification | 58 | reboot device |
| 27 | BLE delete | 64 | map navigation |
| 28 | show BLE-delete switch | 65 | map compass |
| 29 | emergency contact | 66 | Muslim prayer |
| 30 | sync collect contact | | |
| 31 | quick respond | | |

### Glasses-specific capability flags

The vendor SDK also exposes a separate glasses-only structure (`WmGlassesFunctionSupport`) with
seven flags:

`noStorageDevice`, `supportAiChat`, `supportFunctionVersion`, `supportScoLink`,
`supportVolcEngine`, `supportWakeWord`, `supportZlsyEngine`.

These map to the voice-assistant features (AI chat, SCO audio link, wake word, and the
VolcEngine / ZLSY speech engines).

> **Caveat:** the bit *order within each byte* of the mask was not verified against the device
> (the SDK expands each byte to 8 bits and reverses it, so the LSB-first reading is the most
> likely). The bit→function mapping itself was extracted directly from the vendor parser.

See §7 for the complete 68-node builder table.

Nodes observed in the captured working session but **not** produced by the node builder — they
are parsed from replies or assembled ad-hoc by the session code:

`57B1` (capture ACK), `7320` (element count), `C101`, `C104`, `C107`, `C10A`, `C109` (camera
control).
