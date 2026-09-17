# Session Bind, User Enrollment & Authentication

Technical reference on how the XK One Pro / LensMoo smart glasses authenticate a client, what is
actually validated, and what was disproved by controlled hardware testing.

> This document replaces an earlier version that attributed the `0x0401` error to a random bind
> blob. That explanation was **incorrect**. See [VALIDATION.md](VALIDATION.md) for the raw
> experiments.

---

## 1. Executive summary

There are **two different operations** that are easy to conflate:

| Operation | Frame | Validated? | Purpose |
|---|---|:---:|---|
| **Session bind** | `0001` + `0002` | **No** | Establishes the SPP session context |
| **User bind** | `102E` | **Yes** | Associates a user id with the device; arms the camera pipeline |

1. The session bind token/blob may be **random** — the device does not validate their content.
2. The `102E` **user bind is mandatory** and carries a **fixed, family-wide `userId`** (32 hex
   characters) that the firmware validates **offline**.
3. The glasses never contact a server during normal operation. The `userId` is not a cloud token
   at runtime, but it is a fixed value that must be provisioned.
4. A valid `userId` **cannot be synthesised locally**. Arbitrary values are rejected — including on
   a factory-reset unit and across every `bindType`.

---

## 2. Session bind (`0001` / `0002`) — not validated

The session bind is a two-step exchange sent immediately after the RFCOMM link is up:

* **Bind 1 (`0001`)**: `action = 3`, request id `1`, argument `0x00` + 61-char alphanumeric token.
* **Bind 2 (`0002`)**: `action = 3`, request id `4`, argument `0x00` + 64 bytes.

Controlled A/B/A tests (baseline → one mutation → baseline) show the device accepts:

* a fully random bind-1 token;
* a fully random bind-2 payload;
* a randomised 32-byte middle block;
* non-zero reserved bytes in the envelope (`[14:16]`).

The **only** thing that must be byte-exact is the payload length field: `len = len(rest) - 1`
(see [PROTOCOL.md](PROTOCOL.md) §2). Writing `len == len(rest)` causes the device to answer with
a generic 18-byte response and then drop the link.

> A previous version of the SDK used `len == len(argument)` and therefore could not complete a
> session. This is the actual root cause of the SDK's `Transport endpoint is not connected`
> failure against real hardware.

---

## 3. User bind (`102E`) — required and validated

Node `102E` is the bind/unbind command. Payload (the `rest` field):

```
[format: 1B = 0x00] [bindType: 1B] [randomCode: 16B] [userIdLen: 1B] [userId: N bytes]
```

`bindType` is an enum ordinal:

| Value | Name | Meaning |
|:---:|---|---|
| 0 | `SCAN_QR` | Bind by scanning a QR code |
| 1 | `DISCOVERY` | Bind by discovery |
| 2 | `CONNECT_BACK` | Reconnect to a previously bound user (used by the captured session) |
| 3 | `DISCONNECT` | Disconnect |
| 4 | `UNBIND` | Unbind — **also removes the Bluetooth pairing on the glasses** |
| 5 | `POWEROFF` | Power off |

* `randomCode` is 16 bytes; the captured working session sends 16 zero bytes.
* `userId` is 32 lowercase hex characters (16 bytes).
* A minimal session of `0001` + `0002` + `102E` is sufficient: all other setup frames are optional
  (verified by ablation).

---

## 4. Where the `userId` comes from

Analysis of the vendor application (`com.lensmoo.app`) shows:

* The bind frame builder reads the value from local storage:
  `SharedPreferences["device_cache_login_user_id"]`.
* That value is written by the account/login flow (vendor endpoints `service/user/regiestr` and
  `service/user/refreshToken`).
* The app forwards the stored value **verbatim** into the `102E` frame. There is no local hashing
  or transformation (no `MessageDigest` usage anywhere in the app except file MD5).

So the `userId` originates from the vendor's account service. Once known, it is used **offline**
and works on any unit of the family.

---

## 5. Can a `userId` be generated? (No)

This was tested exhaustively against real hardware. Every attempt to use a value other than the
provisioned one failed while the baseline kept succeeding:

| Experiment | Result |
|---|---|
| Mutate a single hex character | ❌ rejected |
| Upper-case the value | ❌ rejected |
| All zeros | ❌ rejected |
| Random 128-bit value | ❌ rejected |
| `bindType = SCAN_QR` + random value | ❌ rejected |
| `bindType = DISCOVERY` + random value | ❌ rejected |
| `bindType = CONNECT_BACK` + random value | ❌ rejected |
| After `UNBIND` | ❌ rejected |
| After a fresh Bluetooth bond | ❌ rejected |
| **On a factory-reset (virgin) unit** | ❌ rejected |
| Checksum / CRC / MAC structure inside the 16 bytes | ❌ none found |

**Conclusions:**

* The device does **not** implement "first bind wins" or per-bond registration: a virgin device
  still rejects arbitrary values.
* The check is therefore **intrinsic to the value** — a firmware-side cryptographic validation
  (signature/MAC) or a firmware whitelist. Either way, only values issued by the vendor's system
  are accepted.
* The validation secret is **not** in the Android APK (no local hashing), so it cannot be
  extracted from the app.

The only remaining route to a *different* value would be dumping the glasses firmware (UART/OTA)
to recover the validation key — out of scope for this SPP SDK and unnecessary, because the known
value works offline on every unit.

---

## 6. Transport & socket requirements

* Linux/BlueZ: a plain RFCOMM socket on **channel 8** is sufficient. No special security
  configuration was required; the link was bonded.
* Android: the vendor SDK tries secure SPP first, then insecure, then reflected channel-8 sockets.
  Prefer the secure path first.
* `UNBIND` (`bindType = 4`) breaks the Bluetooth pairing on the glasses. Re-pairing is required
  afterwards; the `userId` remains valid.

---

## 7. Privacy & offline operation

Accurate statement of the security posture:

* ✅ The transport and all data transfer are local Bluetooth. No internet access is required.
* ✅ No account, login, or cloud call is made at runtime.
* ✅ The session bind parameters are random and are not credentials.
* ⚠️ There **is** a fixed identifier (`102E` `userId`) required by the firmware. It is shared
  across units of the family and is validated offline. The earlier claim of "zero proprietary
  keys" was incorrect.
* ⚠️ Treat the `userId` as sensitive provisioning material: do not log it, and do not ship it in
  public fixtures.

---

## 8. Not yet verified

* Whether a `userId` issued by the vendor for a **different account** is accepted (no second valid
  sample was available).
* The exact cryptographic construction of the `userId` (signature vs whitelist).
* Behaviour across different firmware versions.
