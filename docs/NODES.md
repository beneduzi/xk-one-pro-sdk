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
| `57A0` | Battery / power indication (`action 0x8001`) |
| `5770` | Storage capacity |
| `5780` | Answers with a short status block (`…0401 0003`); likely unsupported |
| `1004` | Answers with a short status block (`…0401 0004`) |
| `C107` | Answers with a short status block (`…0401 0004`) |
| `C109` | Answers with a short status block (`…0401 0004`) |
| `C10A` / `C104` | Camera control; `C104` does **not** change resolution |
| `2410` / `2420` | Preview parameters |
| `2B` custom | `FGS`, `FND`, `F0600100`, `F0600300` — all optional |
| `C101` | Touch / voice button event |

> **Probing notes.** The device answers most nodes **once per session**, and several nodes
> (`7100`, `7110`, `2410`, `2420`, `C10A`, `57A0`, `5770`) only reply when queried in the
> context/order of the full setup sequence — a standalone query is ignored. Nodes that require an
> argument do not answer an argument-less query. A short `…0401 000X` reply is returned for nodes
> that are recognised but produce no data.

---

## 4. 🔵 Mapped from the vendor SDK (function inferred)

| Node | Probable function |
|---|---|
| `1004`, `4700` | Notification settings |
| `1032` | Memory info |
| `1007`, `1008` | Time / location sync |
| `5710`, `5711`, `5712`, `5720`, `5750` | Media / time related |
| `7200`, `7310`, `7400`, `7600` | Unidentified |
| `3300`, `5500`, `5610`, `5620` | Unidentified |
| `9000`, `9001`, `A001`, `B001`–`B004`, `C109` | Unidentified |
| `102A`, `102C`, `1030`, `1031` | Unidentified |

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

Heart rate alerts, sleep settings, sport goals, sedentary reminder, drink-water reminder,
personal info, unit info, wrist raise, alarms, contacts, weather, Muslim prayer times,
widgets, watch dials, find-device.

---

## 6. ❌ Absent

* **Resolution / quality control** — no node, entity field or string exists in the SDK; `C104` has
  no measurable effect. Resolution is treated as firmware-fixed (~640x480 on the validated unit).
* **Voice-prompt control** — no setting found; `1017` sub 5 (`isMuted`) does not silence prompts.
* **Audio routing over SPP** — audio uses HFP/SCO and A2DP, outside this protocol.

---

## 7. Complete node list recovered from the vendor SDK

```
0001 0002 1001 1003 1004 1007 1008 1017 102A 102C 102E 1030 1031 1032
3300 4700 5500 5610 5620 5710 5711 5712 5713 5720 5750 5770 5780 57A0 57B0
7200 7300 7310 7400 7500 7600 9000 9001 A001 B001 B002 B003 B004 C109
```

Plus nodes used by the captured working session that are built outside the vendor SDK's node
table: `2410`, `2420`, `7100`, `7110`, `C101`, `C104`, `C107`, `C10A`, `7320`, `57B1`.
