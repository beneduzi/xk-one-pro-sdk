# Bonded Phone Enrollment & Authentication Specification

Technical reference on how the XK One Pro / LensMoo smart glasses handle client authentication, the difference between unbonded and bonded Bluetooth connections, and the resolution of the `0x0401` session authorization error.

---

## 1. Executive Summary

During initial reverse engineering, connections from bonded Android devices were rejected with error status `0x0401` on every query, causing the glasses to terminate the RFCOMM connection within ~6–8 seconds.

The root cause and solution are established:
1. **Bond State Dependency**: The glasses firmware checks the Bluetooth link bond state.
2. **Socket Security**: On bonded Android devices, the connection must use an encrypted RFCOMM socket (via `createRfcommSocketToServiceRecord(SPP_UUID)` with fallback to `createRfcommSocket(8)`).
3. **Session Handshake**: The two-step bind sequence (`0001` and `0002`) establishes the session context.
4. **Subsystem Arming**: The subsequent setup sequence (registering `userId`, queries `7100`, `7110`, `1001`, `1003`, `2410`, `2420`, `C10A`, `C104`, `57A0`, `5770`, `5713`, `57B0` and interleaving `300004` ACKs) completes authorization, enabling all camera and data services.

---

## 2. Connection Matrix

| Platform / Client | Bond State | Socket Type | Bind Payload | Session Authorization |
|---|---|---|---|---|
| **Linux PC / BlueZ** | Unbonded / Bonded | RFCOMM Channel 8 | Standard Bind (`0001` + `0002`) | **SUCCESS** (`BOUND` state active, camera commands armed) |
| **Android (Production)** | Bonded (OS Settings) | Secure SPP Channel 8 | Standard Bind (`0001` + `0002`) | **SUCCESS** (`BOUND` state active, camera commands armed) |
| **Android (Incomplete Setup)**| Bonded | Any | Missing Setup Sequence | **REJECTED (`0x0401`)** (commands rejected until setup sequence completes) |

---

## 3. The Bind Handshake Wire Format

The session bind consists of two consecutive control frames sent over Channel 8 (`0x30`):

### Frame 1: Bind Token (`0001`)
* **Channel**: `0x30` (Control)
* **Command Node**: `"0001"` (ASCII)
* **Action Type**: `0x0003` (Execute)
* **Request ID**: `0x0001`
* **Argument**: `0x00` byte followed by a 61-character alphanumeric token (e.g. `gKr94YfBWjAD1ecN1bmwMu8tdDHeAKTH7RUh9bslsgYGJlt4z9CYC7u3Xa0NC`).

### Frame 2: Bind Data (`0002`)
* **Channel**: `0x30` (Control)
* **Command Node**: `"0002"` (ASCII)
* **Action Type**: `0x0003` (Execute)
* **Request ID**: `0x0004`
* **Argument**: `0x00` byte followed by a 40-byte binary blob (e.g. 16-character nonce prefix + 32-byte payload + 16-character suffix).

After each bind frame, the client sends a `0004` ACK/poll frame (`300004`).

---

## 4. Socket Requirements on Android

Android Bluetooth stacks behave differently when a device is bonded:

1. **Secure SPP Socket (Primary)**:
   ```kotlin
   val socket = device.createRfcommSocketToServiceRecord(SPP_UUID)
   socket.connect()
   ```
   * `SPP_UUID = UUID.fromString("00001101-0000-1000-8000-00805F9B34FB")`

2. **Channel 8 Reflection (Fallback)**:
   ```kotlin
   val method = device.javaClass.getMethod("createRfcommSocket", Int::class.javaPrimitiveType)
   val socket = method.invoke(device, 8) as BluetoothSocket
   socket.connect()
   ```

*Connecting over an insecure socket when the device is bonded causes link drops. Always use the secure path.*

---

## 5. Subsystem Parameters & Identifiers

Extracted from production sessions and firmware logs:

* **Static User ID**: `"1f1823e0e2896cdb8012a3ac083a35e6"`
  * Registered during setup via command node `102E`.
  * The firmware uses this ID to bind the current session context.
* **Product Key**: `tsRbsvFh167` (Identifies the W20 / XK One Pro product family).
* **Device Name Format**: `FA001112F773` (Bluetooth MAC address without colons).

---

## 6. Implementation Summary

To ensure 100% reliable connection on Android and Linux:
1. Connect to RFCOMM Channel 8 using a secure socket.
2. Send `XkSessionTemplates.bindSequence()` with a 200ms delay between frames.
3. Wait 1.5 seconds, then send `XkSessionTemplates.setupSequence()` with a 150ms delay between frames.
4. Mark the state as `BOUND`. The camera pipeline is now armed for captures (`57B0`) and photo downloads (`7300`).

*For details on the image transfer protocol and two-layer JPEG reassembly, see [PROTOCOL.md](PROTOCOL.md).*
