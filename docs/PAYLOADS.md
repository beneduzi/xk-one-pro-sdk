# Structured Payload Reference

The vendor SDK models every payload as an **entity class**. This document catalogs those
entities and the enums that frame them, so that a reply can be decoded field by field instead of
being treated as an opaque blob.

Provenance is marked per table:

* ✅ **verified** — observed on the validated unit.
* 🔵 **SDK-derived** — extracted from the decompiled vendor app (`com.lensmoo.app`); the glasses
  may or may not implement it.

---

## 1. Reply envelope (decoded)

A `0x30` reply, after the 4-char node at `payload[10:14]`:

```
[type:1] [len:2 LE] [data: len bytes]
```

The `type` byte is the **`DataFormat` enum ordinal** — not an ad-hoc tag:

| `type` | `DataFormat` | Meaning | Observed |
|:---:|---|---|:---:|
| `0x00` | `FMT_BIN` | raw binary | ✅ 933 |
| `0x01` | `FMT_PLAIN_TXT` | plain text | – |
| `0x02` | `FMT_JSON` | JSON object | ✅ 108 |
| `0x03` | `FMT_NODATA` | acknowledgement, no data | – |
| `0x04` | `FMT_ERRCODE` | one-byte status/error code | ✅ 93 |

When `type = FMT_ERRCODE` the single data byte is the **`ErrorCode` enum**:

| Code | `ErrorCode` | Meaning |
|:---:|---|---|
| `0x00` | `ERR_CODE_OK` | success, no data |
| `0x01` | `ERR_CODE_FAIL` | generic failure |
| `0x02` | `ERR_CODE_NODATA` | no data available |
| `0x03` | `ERR_CODE_INVALID_PARAM` | wrong/missing parameter |
| `0x04` | `ERR_CODE_INVALID_URN` | **node not recognised / not implemented** |
| `0x05` | `ERR_CODE_INVALID_DATA` | malformed data |
| `0x06` | `ERR_CODE_INVALID_CMD` | unknown command |
| `0x07` | `ERR_CODE_INVALID_PACKAGE` | bad package |
| `0x08` | `ERR_CODE_INVALID_PACKAGE_SEQ` | bad package sequence |
| `0x09` | `ERR_CODE_INVALID_PACKAGE_LIMIT` | bad package limit |
| `0x0A` | `ERR_CODE_INVALID_ITEM_COUNT` | bad item count |
| `0x0B` | `ERR_CODE_INVALID_ITEM_LIST` | bad item list |
| `0x0C` | `ERR_CODE_INVALID_ITEM_DATA` | bad item data |
| `0x0D` | `ERR_CODE_INVALID_ITEM_DATA_LEN` | bad item data length |
| `0x0E` | `ERR_CODE_INVALID_ITEM_DATA_FMT` | bad item data format |
| `0x0F` | `ERR_CODE_INVALID_ITEM_DATA_URN` | bad item URN |

Observed distribution: `OK` 50, `FAIL` 23, `INVALID_URN` 14, `INVALID_DATA` 4,
`INVALID_PARAM` 2.

> This re-frames several earlier findings. The "generic no-op" replies from `C101`, `C104`,
> `C107`, `C109`, `C10A`, `1004`, `1007`, `9000`, `5710` are all
> `FMT_ERRCODE / ERR_CODE_INVALID_URN` — i.e. **the firmware does not implement those URNs**.
> `5780` returns `INVALID_PARAM` and `9001` returns `INVALID_DATA`, so those two are recognised
> but called wrongly. `2420` returns `ERR_CODE_OK` with no data — a successful no-content write.

### Request `action` field = `RequestType`

| Value | `RequestType` |
|:---:|---|
| 0 | `REQ_TYPE_INVALID` |
| 1 | `REQ_TYPE_READ` |
| 2 | `REQ_TYPE_WRITE` |
| 3 | `REQ_TYPE_EXECUTE` |
| 4 | `REQ_TYPE_NOTIFY` |

---

## 2. Verified payloads (glasses) ✅

| Node | Entity | Format | Fields / layout |
|---|---|---|---|
| `1001` | `BasicInfo` | JSON | `prod_mode`, `soft_ver`, `mac_addr`, `dev_id`, `dev_name`, `prod_category`, `prod_subcate`, `battery_main`, `dial_ability`, `screen`, `ch`, `cw`, `nch`, `ncw`, `screen_shape`, `preview_width`, `preview_height`, `offline_asr_auth` — the SDK model also defines `hard_ver`, `prod_date`, `chip_mode`, `lang`, `spo2`, `alipay`, `is_charging`, `remain_memory`, `total_memory`, `photo_num`, `video_num`, `record_num`, `music_num` (served by other nodes on this unit) |
| `1003` | `BatteryBean` | BIN | `[is_charging:1][battery_main:1]` + 8 B padding |
| `1017` | `WmSoundAndHaptic` | BIN | 5 flags in one bitmask: `isRingtoneEnabled`, `isNotificationHaptic`, `isCrownHapticFeedback`, `isSystemHapticFeedback`, `isMuted` (observed `0x1f` = all set) |
| `5712` | `WmDeviceSDInfo` | JSON | `total_memory`, `remain_memory` |
| `5713` | `WmDeviceMediaCountInfo` | JSON | `photo_num`, `video_num`, `record_num`, `music_num` |
| `7100` | `WmFunctionSupport` | BIN | `[version:1][capability mask:16][maxContacts:2][sideButtonCount:1][fixedSportCount:1][variableSportCount:1]` + 62 capability bits |
| `7110` | `WmGlassesFunctionSupport` | BIN | `noStorageDevice`, `supportAiChat`, `supportScoLink`, `supportVolcEngine`, `supportWakeWord`, `supportZlsyEngine`, `supportFunctionVersion` |
| `102E` | `WmBindInfo` | BIN | `[bindType:1][randomCode:16][userIdLen:1][userId]` |
| `57A0` | — | BIN | video-preview state, `data[0]` (0 = off, 1 = on) |
| `2410`/`2420` | `WmLanguage` | BIN | `curr_lang`, plus `bcp` / `name` in the SDK model; observed payload is a list of NUL-padded language tags (`en`, `en`, `zh-cn`) |
| `57B0`/`57B1`/`7320`/`7300`/`7500` | — | — | capture / count / element / end-transfer control path |

### `WmStorageType` (for the storage nodes `5770`/`5712`)

| Value | Meaning |
|:---:|---|
| 0 | `TOTAL` |
| 1 | `DIAL_STORAGE` |
| 2 | `MUSIC_STORAGE` |

### Image element header (on channel `0x4A`)

Each reassembled element starts with a 5-byte header:

```
[media_type: 1B] [element_length: 4B LE]
```

* `media_type = 0x00` for a photo/JPEG (the only value observed).
* `element_length` is the **total element size including the 5-byte header**, so the JPEG slice
  is `element_length - 5` bytes.
* Verified 6/6 against a live capture: declared `617`, `16389` (×4), `14414` — exactly the
  assembled element sizes.

> The reassembler previously documented this as `[length: 4B LE, media_type: 1B]`. Because the
> code simply strips 5 bytes, the reversed order was invisible — but the field order in the docs
> (and in `reassembler.py`) was wrong and is now corrected.

---

## 3. SDK data-model catalog 🔵

Full node → entity → field map extracted mechanically from the node builders and entity classes.

### Glasses-relevant

| Node | Entity | Fields |
|---|---|---|
| `1004`, `4700` | `WmNotification` | `appPackage`, `title`, `content`, `dateTime` |
| `1004`, `4700` | `WmNotificationSetting` | `msgState`, `phoneCallState` |
| `1007` | `WmDateTime` / `TimeSyncBean` | `currentDate`/`currDate`, `currentTime`/`currTime`, `timeZone`/`timeZoo`, `timestamp` |
| `102A`, `102C`, `5610`, `5620` | `WmVideoFrameInfo` | `frameId`, `frameType`, `frameLen`, `frameData` |
| `7200`, `7300`, `7310`, `7400`, `7500`, `7600` | `WmVideoFrameInfo` | same (image/video transfer) |
| `102A`, `102C`, `5610`, `5620` | `OtaCmdInfo` | `crc`, `offSet`, `payload` — **OTA update channel** |
| `1030`, `1031`, `1032` | `SyncTime` | `startTime`, `endTime` |
| `1030`, `1031`, `1032` | `WmStorageType` | `TOTAL`, `DIAL_STORAGE`, `MUSIC_STORAGE` |
| `1030`, `1031`, `1032` | `DivideInfo` | `divideType`, `payloadPackTotalLen` |
| `A000`, `A001` | `WmSensorDataRequest` / `WmSensorDataResponse` | `sensorType` (`G_SENSOR`, `OTHER`), `sensorFrequency` (`25`/`50`/`100`), `data`, `dataLen` — **raw accelerometer streaming** |
| `5500` | — | builder has no entity type |

### Watch-only

| Node | Entity | Fields |
|---|---|---|
| `2100` | `WmSportGoal` | `steps`, `calories`, `distance`, `activityDuration` |
| `2200` | `WmPersonalInfo` | `gender` (`MALE`/`FEMALE`/`OTHER`), `height`, `weight`, `birthDate{year,month,day}` |
| `2300` | `WmUnitInfo` | `distanceUnit` (`KM`/`MILE`), `temperatureUnit` (`CELSIUS`/`FAHRENHEIT`), `timeFormat` (`TWELVE_HOUR`/`TWENTY_FOUR_HOUR`), `weightUnit` (`KG`/`LB`) |
| `2500`, `2600` | `WmSedentaryReminder` | `isEnabled`, `frequency` (`EVERY_30_MINUTES`/`EVERY_1_HOUR`/`EVERY_1_HOUR_30_MINUTES`), `timeRange{startHour,startMinute,endHour,endMinute}`, `noDisturbLunchBreak` |
| `2500`, `2600` | `WmNoDisturb` | `isEnabled`, `timeRange` |
| `3100`, `3200`, `3300` | `WmDial` | `id`, `curr`, `status` |
| `4110` | `WmAlarm` | `alarmName`, `hour`, `minute`, `isOn`, `repeatOptions` |
| `4230` | `WmSport` | `id`, `type`, `buildIn` |
| `4320`, `4330` | `WmContact` | `name`, `number` |
| `4320`, `4330` | `WmEmergencyCall` | `isEnabled`, `emergencyContacts` |
| `4410`, `4420` | `WmWeather` | `location{city,country,district,latitude,longitude}`, `pubDate`, `todayWeather`, `weatherForecast` |
| `4410`, `4420` | `TodayWeather` | `date`, `hour`, `weatherCode`, `weatherDesc`, `curTemp`, `tempUnit`, `humidity`, `uvIndex`, `wind` |
| `4410`, `4420` | `WmWeatherForecast` | `date`, `week`, `dayCode`/`dayDesc`, `nightCode`/`nightDesc`, `highTemp`, `lowTemp`, `humidity`, `humidityNight`, `uvIndex`, `uvIndexNight`, `wind` |
| `4500` | `WmHeartRateAlerts` | `age`, `maxHeartRate`, `isEnableHrAutoMeasure`, `exerciseHeartRateAlert{isEnable,threshold}`, `restingHeartRateAlert{isEnable,threshold}` |
| `4600` | `WmSleepSettings` | `open`, `startHour`, `startMinute`, `endHour`, `endMinute` |
| `4900` | `WmWidget` | `type` (20 values: `WIDGET_HEART_RATE`, `WIDGET_WEATHER`, `WIDGET_REMOTE_CAMERA`, …) |
| `5110`, `5120`, `5210`, `5220` | `WmFind` | `count`, `timeSeconds` |
| `5410` | `WmMusicInfo` | `playerName`, `trackTitle`, `trackArtist`, `trackAlbum`, `trackDuration`, `playerVolume`, `queueCount`, `queueIndex`, `queueRepeatMode`, `queueShuffleMode`, `playerBackInfo` |
| `5410` | `WmMusicControlType` | `MUSIC_REQUEST`, `PLAY`, `PAUSE`, `PLAY_PAUSE`, `NEXT_SONG`, `PREV_SONG`, `VOLUME_UP`, `VOLUME_DOWN` |
| `B001`–`B004` | `WmMuslimCalcParam` | `latitude`, `longitude`, `timeZone`, `year`, `month`, `day`, `calcType`, `juristicMethod` |
| `B001`–`B004` | `WmMuslimPrayTime` | `id`, `hour`, `minute` |
| `B001`–`B004` | `PrayRemind` | `id`, `open`, `Fajr`, `Sunrise`, `Dhuhr`, `Asr`, `Maghrib`, `Isha`, `Sunset` |
| `B001`–`B004` | `WmRosaryReminder` | `switch`, `frequency` (30/60/120/180), `startHour`/`startMinute`, `endHour`/`endMinute`, `repeatRules`, `version` |
| `B001`–`B004` | `WmAllah` / `WmAllahCollect` | `id`, `collect` / `allahList`, `version` |

### Entities with no node binding found (app-side models)

`SportInitInfo` (`birthday`, `gender`, `height`, `weight`, `step_goal`, `dis_goal`, `heat_goal`),
`WmSleepSummary` (score, deep/light/REM/awake minutes and percentages, bed/get-up time),
`WmSportSummaryData` (per-10 s calories / distance / heart-rate / step-frequency series),
`WmDailyActivityDurationData`, `WmDiscoverDevice` (`deviceNamePrefix`, `deviceType`,
`frontViewImg`, `sideViewImg`), `WmDevice`, `WmBaseSyncData`, `AppViewBean`/`AppViewListBean`.

---

## 4. What this changes

1. **Replies are typed, not opaque.** `type` is `DataFormat`; `0x04` payloads are `ErrorCode`.
   The "mysterious no-ops" are `ERR_CODE_INVALID_URN` — the node simply is not implemented.
2. **`1001` is a subset.** The SDK's `BasicInfo` defines 31 fields; this unit serves 18 via `1001`
   and the rest via `1003`/`5712`/`5713`.
3. **`ERR_CODE_OK` with no data is meaningful** (e.g. `2420`) — a successful write, not a failure.
4. **Unexplored but modelled:** OTA (`OtaCmdInfo` + `supportOtaState`), raw sensor streaming
   (`A000`/`A001`), time sync (`1007`/`1030`–`1032`), notifications (`1004`/`4700`).

> Caveat: §3 is a *data-model* catalog. Membership in the SDK does not imply the glasses firmware
> implements the node — §2 and the `ERR_CODE_INVALID_URN` results are the hardware evidence.
