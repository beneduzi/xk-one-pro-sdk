# Hardware

Observed unit: Bluetooth name **xk one Pro_F773**, address `FA:00:11:12:F7:73`. The address/name suffix pattern is observed, but the general MAC allocation pattern is **UNKNOWN**.

| Service | Characteristics / observation |
|---|---|
| `aaa0` | `aaa1`, `aaa2` |
| `fff00000` | `fff1`, `fff2`, `fff3` |
| HID `0x1812` | HID service |
| Battery | Battery service (UUID/value details **UNKNOWN**) |
| Device Information | manufacturer `shenju`, model `w20`, firmware `1.0.1` |

BR/EDR exposes SPP, A2DP, AVRCP, and HFP. HFP/SCO is used for microphone audio; A2DP is used for playback. Audio routing remains **PENDING** in this project.

There are two physical buttons and touch input (button count/touch from retail listings). Capture works only with an active app session; otherwise the glasses say “please connect to the app”. No distinct button-event frame was observed; the app initiates capture through camera queries. Button media-key behavior is **PENDING**.

Bonded devices may disappear from scanners. A factory reset restores discoverability. Exact reset procedure is **UNKNOWN**.
