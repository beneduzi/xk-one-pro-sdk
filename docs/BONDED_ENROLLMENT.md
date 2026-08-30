# Bonded enrollment & the 0401 wall — RESOLVED

**Status: RESOLVED (2026-08-28).** Root cause found and validated live on a
bonded Android phone: the **bind2 blob must contain a valid vendor enrollment**
(the native `encryptData` output). A random blob is accepted structurally
(`4a55` ack) but the session is never authorized — every query answers
`0401 0001` and the device resets the connection ~6-8 s after connect.
Replaying a captured valid enrollment authorizes the session immediately.

---

## 1. The core finding

The glasses distinguish clients by **link bond state**, and bonded clients must
present a **valid enrollment** in the bind2 frame:

| Client | Bind | Queries (7100/102E/7110...) | Session |
|---|---|---|---|
| **Unbonded** (Linux PC via BlueZ, no pairing) | Accepted — any well-formed random token works (`4a55` ack) | **SUCCESS** (`0016 0010` + data) | Stable 40+ s, photo count query returns 9 |
| **Bonded Android, random blob** | Accepted (`4a55` ack — structural check only) | **`0401 0001` — REJECTED** | `Connection reset by peer` ~6-8 s after connect |
| **Bonded Android, valid enrollment** (replayed or freshly generated) | Accepted (`4a55` ack) | **SUCCESS** — languages, `{"photo_num":7}`, camera arm `57B0→57B1` | **Stable** — `BOUND ok`, device pushes `7320` count |

Conclusion: the `4a55` bind response is a *packet-accepted* ack, not
*session-authorized*. Bonded clients must present the **vendor's native
enrollment** — the crypto blob produced by `BtUtils.encryptData()` in
`libbtsdk-lib.so`.

**Proven live (2026-08-28):** re-sending the exact bind1+bind2 frames captured
from a working Lensmoo session (which contain a valid enrollment) over the
phone's secure SPP socket produces a fully authorized session: `2410`
languages answered, `5713` photo-count JSON answered, `57B0` camera-arm acked
(`57B1`), `7320` photo count pushed by the device (`7`), no reset.

## 2. The bind on the wire

Session-random (changes every connection). Structure (from captured sessions):

```
bind1: payload = [pkId:2][ff ff ff ff][03][00 00][01]["0001"][00 3d][00]
                + 61 alphanumeric chars  (random token; NOT validated)
bind2: payload = [pkId:2][ff ff ff ff][03][00 00][01]["0002"][00 40][00]
                + [16 ASCII chars][32 bytes binary][16 ASCII chars]
                  e.g. "byLfUPye2jp9a3by" + 3293c6c4... + "byLfUPye2jp9a3rE"
                  (the 16-char sonce appears twice; last 2 chars differ —
                  checksum-like)
```

- The **32-byte binary block is the enrollment** — `encryptData(key, plaintext)`
  output. Random bytes here → `0401` wall on bonded phones.
- The sonce/tail come from the SDK's `h(n)` random-string generator (see §4).

## 3. The socket requirement (Android)

The vendor SDK connects with the **SECURE** SPP socket
(`createRfcommSocketToServiceRecord(SPP_UUID)`, `e7c$e$a.smali:284`). On a
bonded phone the glasses require the encrypted link:

- `createInsecureRfcommSocket(8)` (hidden API) → connect succeeds but the
  session dies the same way as with a random blob (and Android auto-bonds the
  device anyway, so "insecure + unbonded" is not reachable on Android).
- **Fix: try the secure path first** — `createRfcommSocketToServiceRecord(SPP)`
  → fallback `createRfcommSocket(8)` → insecure only as last resort.

## 4. The enrollment key material — WHERE IT COMES FROM (decompiled)

`l9c.smali` (SDK's frame/command helper) reveals the generator behind the
bind payloads:

- **`h(n)` = Java `new Random(System.currentTimeMillis())`** seeded RNG over
  the alphabet `A-Za-z0-9`, returning `n` random chars hex-encoded
  (`stringToHexString`). This produces the sonce/tail/random strings.
- In `L()` (bind frame builder):
  - `v0[0] = h(14)hex`, `v0[1] = h(2)hex`, `v0[2] = h(32)hex`, `v0[3] = h(16)hex`
  - `plaintext = hexStringToByteArray(h(32)hex)` (32 bytes)
  - `key = Integer.parseInt(h(2)hex, radix)` (radix from `uq0.a(16)`)
  - `encryptData(key, plaintext)` → the 32-byte enrollment
- **`encryptData` is native** (`Java_com_sjbt_sdk_utils_BtUtils_encryptData(I[BI)[B`
  in `libbtsdk-lib.so`, wrapper `com.sjbt.sdk.utils.BtUtils`). Java-side crypto
  (`paycertificationapi/bs1.smali`) is a red herring — never called during bind.

Because `h()` is seeded with `System.currentTimeMillis()`, a fresh enrollment
is **reproducible in any JVM**: replicate `h()`, derive key + plaintext, call
the bundled `.so` via JNI. See §6.

## 5. The vendor app's internals (from instrumentation)

### Queue architecture (why naive instrumentation fails)
All frames flow through **two queue layers**; the producer's stack is lost:

```
producer → [ThreadPool queue: e7c$b workers → e7c.m] → e7c.d (enqueue)
         → [UI-thread queue: e7c$d runnable] → socketNotify (SJUniWatch:127)
         → sendNoTimeOutMsg (SJUniWatch:12) → e7c.s (write) → socket
```

Instrumented points (tag `XKPROBE`): `e7c.s` (write), `sendNoTimeOutMsg`
(caller chain + payload length), `e7c.d` (enqueue), the "SEND BIND INFO" site
(bind flow entry). The bind payload generation sits BELOW the queues (native).

> Instrumentation gotcha: a patched `l9c.K()` that referenced a helper under
> the wrong class name compiled fine (apktool does not resolve cross-method
> refs) but threw `NoSuchMethodError` at runtime — the first bind silently
> died and every subsequent connect stalled at "connecting". When instrumenting
> smali, only reference methods that exist in the target class (or `BtUtils`).

### Connection prerequisites
- The SDK requires a **logged-in account** (userId). Empty → `CONNECT_FAIL_INVALID_USERID`.
- SDK manages pairing itself: discovery → BOND → `spp connect success` → `SEND BIND INFO` → bind frames → `device bind search success:true`.

### Custom messages
- `FGS` JSON (`{"msg_type":"FGS_MSG_TYPE_START_FGS_REQ","sidver":1}`) — **static**.
- `FND` JSON — data = `[01 0D 00] + epoch anchor digits` (ms or µs), changes per
  session. Format: `{"sid":"FND","data":"<base64>","ver":1}`. Generateable
  (implemented in the Android app as `XkSessionTemplates.freshFnd()`).

## 6. Fixing it in your own app (validated)

Two options, both proven to work:

1. **Replay a captured valid bind** (fastest): re-send bind1+bind2 verbatim
   from a working Lensmoo session (see the repo's Android app,
   `XkSessionTemplates.bindSequence()`). Validated live on the bonded phone:
   full session authorization. Risk: enrollment may rotate after firmware
   reset/reboot of the glasses.
2. **Generate a fresh enrollment** (robust): replicate `h()` with
   `java.util.Random(System.currentTimeMillis())` in the app, derive
   key/plaintext per §4, and call the vendor `.so`'s `encryptData` through a
   JNI wrapper (`BtUtils.encryptData(int key, byte[] data, int len)`).
   Bundle `libbtsdk-lib.so` (+ `libc++_shared.so`) in `jniLibs/arm64-v8a/`.
   **Keep the `.so` out of public repos** (vendor IP); document the approach
   instead — see `ANDROID_INTEGRATION.md`.

Additional requirements for the Android path:
- **Secure SPP socket first** (§3).
- Full setup sequence (queries + FGS/FND custom messages + polls) must follow
  the bind — without it responses carry `0401`.

## 7. The bind inputs — EXTRACTED (from the SDK's own file logs)

The vendor app's SDK writes detailed logs to:

```
/sdcard/Android/data/com.lensmoo.app/files/starburstsdk/log/starburstsdk_log.txt
/sdcard/Android/data/com.lensmoo.app/files/agent_log/agent_log/YYYY-MM-DD.log
```

These contain (no instrumentation needed!):

```
[D] DefaultDataHandler: productKey ==>   tsRbsvFh167
[D] MultiModalChatWs: appId==>appid-6eHjyPlYdwRH9ang, token=><REDACTED>,
    productKey = tsRbsvFh167, deviceName==>FA001112F773, timestamp==>1787881430083
    sign==>A32BD66F1E9D59449D9A9AE22DB3B8E4B007707366DE49A3E3F2877BC66056BC
```

- `productKey = tsRbsvFh167` (stable per product/account)
- `deviceName = FA001112F773` (device MAC without colons)
- `timestamp` = ms epoch at session time
- `sign` = SHA-256-style cloud signature (appId+token+productKey+deviceName+timestamp)
- `userId = 1f1823e0e2896cdb8012a3ac083a35e6` (stable across installs; the SDK
  refuses to connect without it — `CONNECT_FAIL_INVALID_USERID`)

> The cloud `token` value is redacted here — it is a live account credential.
> These inputs feed the cloud-side `sign`; they are NOT the bind2 enrollment
> key material (that comes from `h()` + native `encryptData`, §4).

## 8. Shipping an instrumented Lensmoo (the full pipeline)

Getting a modified Lensmoo installed on MIUI required solving, in order:

1. **apktool decode must NOT use `--no-res`** — with it, the manifest stays
   BINARY (with the split attributes) and every edit silently does nothing.
2. **Remove split requirements** from the decoded manifest:
   `android:requiredSplitTypes`, `android:splitTypes`, and the
   `com.android.vending.splits(.required)` / `com.android.vending.derived.apk.id`
   meta-data (the Play-installed app is a split APK; `adb install` rejects a
   single APK with `INSTALL_FAILED_MISSING_SPLIT` otherwise).
3. **Merge the arm64 native libs** into the base (the base has NO `lib/` — all
   35 `.so` files live in `split_config.arm64_v8a`).
4. **`android:extractNativeLibs="true"`** (else `Failed to extract native libraries, res=-110`).
5. **`resources.arsc` stored uncompressed + 4-byte aligned** (targetSdk ≥ 30):
   add `resources.arsc` + `lib/` to `doNotCompress` in `apktool.yml`, then
   **`zipalign -f -p 4`** and sign with apksigner AFTER aligning.
6. **PairIP license bypass** (the app is Play-licensed with anti-tamper):
   - `LicenseClient.retryOrThrow(LicenseCheckException, Z)` → `return-void`
   - `LicenseActivity.showPaywallAndCloseApp()` and `closeApp()` → `finish()`
   - Launcher intent-filter moved from `LaunchActivity` to `MainActivity`
   (the check runs from the Application/startup flow, not just the launcher).
7. User must **log in** in the instrumented app (userId is required).
8. Install large APKs via `adb push` + `pm install -r /data/local/tmp/...`
   (streamed `adb install` is flaky for 180 MB+ APKs).

Result: the instrumented app runs, connects, binds and logs everything (tag
`XKPROBE` + the SDK's own `SJ_SDK>>>>>` logcat + the file logs).

## 9. Recommended next steps

1. **Vendor SDK (best path):** Shenju sells the W20 SoC/OEM solutions
   (`shenjugroup.com`, `console.shenjugroup.com`, `support@shenjugroup.com`).
   Request the `com.sjbt.sdk` / Starburst SDK for the W20/XKOENPRO platform.
   You can present the exact protocol map and the extracted parameters
   (productKey format, deviceName, timestamp, sign) as proof of a serious
   integration. The bind algorithm is likely documented there.
2. **Fresh enrollment generation** (see §6 option 2): bundle the `.so`, port
   `h()`, done — the app becomes independent of captured frames.
3. **PC as gateway:** the unbonded SPP session works TODAY (see the Python
   SDK): connect, bind (random), setup, photo count. The phone app can talk to
   the PC over the network and drive the glasses through it.

## 10. TL;DR

- The protocol, bind, setup, queries and photo flow are fully decoded and
  validated on hardware — **including from bonded Android phones**.
- The `0401` wall was the **bind2 enrollment blob**: random → rejected;
  valid `encryptData` output → fully authorized session (proven live).
- Bonded clients must also use the **secure SPP socket** (vendor behavior).
- The enrollment generator is `h()` (time-seeded Java `Random`) + native
  `encryptData`; both are reproducible (`.so` bundling + a few lines of Kotlin).
- All artifacts, logs and instrumentation points are documented here so the
  work can continue from this exact point.

## 11. Lensmoo photo/poll sequence (observed protocol findings)

The following sequence was observed in a working Lensmoo session. It is
included as a wire-level observation, not as a claim that these commands are
part of a public or standardized protocol:

1. The device pushes `7320`.
2. The app responds with `300004`, whose payload acknowledges the command order
   (`cmdOrder`) of the frame it received.
3. The app sends `7300` polls. The first observed request ID is `0x003E`,
   followed by `0x0042`, `0x0046`, and subsequent IDs.
4. The exchange includes `8004`/`8001` ACKs, then `300004`.
5. The device sends `4A0001` fragments, ending with a `4A0009` fragment whose
   payload is `[01]`, followed by the next `7300` poll.

### `300004` command-order detail

The `300004` payload is `[01, cmdOrder-of-the-received-frame]`. The second
byte is the `cmdOrder` from the frame being acknowledged; it is distinct from
the `cmdOrder` belonging to the `300004` poll/response frame itself. Confusing
these two command orders produces an incorrect interpretation of the ACK
relationship.

### `4A` fragmentation and logical units

Observed `4A` media fragmentation uses `divideType` values `1`, `2`, and `3`.
The observed fragment payload sizes include 583 bytes and 42 bytes. A
4-byte fragment index is restarted for each logical element, rather than
continuing across the whole transfer. The first fragment carries the media
header.

The logical unit and totals observed are important: one photo is composed of
multiple `7300` elements, and the corresponding `4A` fragments belong to
those elements. These observations must not be described as a standard
protocol or used to assert that the format is standardized.

### Limitations and open confirmation

The bytes sent by the app still need to be captured directly to confirm the
reported failure at `idx=2`. Also, the `4A` protocol appears proprietary;
the names, sequence, and fragment structure above describe observed behavior
only and do not establish a public specification.

## 12. Lensmoo photo-transfer protocol findings (2026-08-28)

Verified capture conclusions from eight transfers: five app-triggered transfers
and three button-triggered transfers. Both trigger paths showed the same
post-trigger flow.

- `7320` count values were `6, 6, 6, 7, 7` for the five app-triggered
  transfers and `6` for the button-triggered transfers.
- Observed transfer latency was 720–905 ms for app-triggered transfers and
  796–873 ms for button-triggered transfers.
- Each element followed this sequence: `7300` request → response →
  `300004` payload `[01, response cmdOrder]` → `4A0001`.
- The `divideType` is the raw value masked with `& 3`. For `divideType` 1, 2,
  and 3, the payload contains a little-endian `u32` fragment index. Type 0 is
  unfragmented.
- Exactly one `4A0009` was observed, only after type 3. The next `7300` was
  sent only afterward; `7500` appeared at the end of the transfer.
- Each element contained five non-JPEG bytes. The JPEG EOI marker appeared
  only in the final aggregate, not in each element.
- CRC validation was true for all observed packets. Packet-loss diagnostics
  were also observed in the capture.
- The request/cmdOrder baseline for `7300` was `cmdOrder 0x28` and request
  `0x003D`; the request ID increased by 4 for each element.

Button detection already works in the application and is explicitly out of
scope here; this section documents the resulting transfer protocol only.
