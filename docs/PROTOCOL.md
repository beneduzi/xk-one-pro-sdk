# Protocol

## Transport and frame

Use Bluetooth Classic RFCOMM/SPP channel **8**. Channel 1 is an AT/HFP command interface and sends `AT+BRSF=157\r` on connection. Frames are binary and may begin with `0x30`, `0x4a`, or `0x2b`.

Normal header (wire offsets):

| Offset | Size | Encoding |
|---|---:|---|
| 0 | 1 | head (`30` normally) |
| 1 | 1 | command order |
| 2 | 2 | command, little-endian in final implementation |
| 4 | 2 | divide type, little-endian |
| 6 | 2 | payload length, little-endian |
| 8 | 4 | offset/pack total, little-endian |
| 12 | 2 | CRC, little-endian |
| 14 | 2 | request ID, big-endian |
| 16 | N | payload |

Payload package layout is `pkId[2] ff ff ff ff format 00 00 01 node[4] status/action[2] data`. Formats observed are 03 (binary request), 02 (response package), and 04 (response data). A captured request is `3048010000001100000000005D7000006000FFFFFFFF0100000137313030000000`: payload length 0x11, node `7100`, and zero action. A short ACK is `3001048000020200000000003e2e00000100`.

Split frames include a divide index; the SDK removes the package header before exposing data. Bounds-check lengths and resynchronise on a valid head.

## CRC

CRC is CRC-16/CCITT: polynomial `0x1021`, init `0xffff`, non-reflected, xorout zero. Compute over payload only (bytes 16 through `16+payloadLen`), store the result little-endian at bytes 12–13. This matches 15 device and 6 app frames (21/21), including bind and polls. The Kotlin port computes the same algorithm.

## Commands

`0001` bind/query; `0002` bind continuation; `0004` ACK/poll; `1001`, `1003`, `1007` (JSON), `102E` information/config; `102A` preview-picture request; `2410`, `2420` preview capabilities (`2420` carries `en`); `57A0`, `57B0`, `57B1`, `5713`, `5770` camera state/capture queries; `7100`, `7110` status; `7320` photo-element count; `7300` photo element by index; `4A0001` device-to-app photo data; `4A0009` stream poll/ACK; `7500` end transfer; `C10A`, `C104` camera/device controls; `2B0002` unsolicited custom indication; `2B0004` app custom transport. Exact subfields not established are **UNKNOWN**.

## Bind and setup

Bind with node `0001`, a random 61-character alphanumeric token, then node `0002` with random binary data. Live testing accepted completely random values; no crypto is required and replay/randomness semantics beyond that are **UNKNOWN**. Interleave `0004` polls.

After bind, send in order: `7100`; `102E` with constant userId `1f1823e0e2896cdb8012a3ac083a35e6`; `7110`; `2B0004` `F0600100`; `F0600300`; FGS JSON; FND JSON; `1007`; `1001`; `1003`; `2410`; `2420`; `C10A`; `C104`; `57A0`; `5770`; `5713`; `57B0`, with `0004` polls interleaved. Without setup responses report status `0401`; success is `04800001 ... 00010000`.

FGS example: `{"sid":"FGS","data":"{\"msg_type\":\"FGS_MSG_TYPE_START_FGS_REQ\",\"sidver\":1}","ver":1}`. FND carries base64 application data; captured `photo_num=0, video_num=0, record_num=0, music_num=0`.

## Photos and custom messages

The observed dialog is `57B0`/arm → `7320` (count, live count 6) → each index `1..N`: `7300`, device response, `4A0001` burst, and app `4A0009` poll (one-byte `01`) → next index → `7500`. Example `7300`: `303601000000120000000000119900003E00FFFFFFFF020000013733303000010001`; `7500`: `3042010000001200000000004FD400005600FFFFFFFF030000013735303000010000`. For `4A0001`, concatenate chunks in divide-index order; JPEG bytes start at payload offset 20. Captures suggest ~10.8 KiB/frame and ~200 frames for a 2.2 MiB JPEG. End-to-end persistence is **PENDING**.

`2B0004` wraps JSON after binary fields; `2B0002` is pushed by the device. `FGS` starts foreground service; `FND` discovers file/photo numbers. Other SIDs are **UNKNOWN**.

Keep `0004` housekeeping polls and application keepalive traffic active. Idle RFCOMM sessions drop after approximately 60 seconds; reconnect and repeat bind/setup.
