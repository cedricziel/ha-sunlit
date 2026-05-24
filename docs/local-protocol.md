# BK215 local-mode (TCP) protocol

Reverse-engineered reference for the **local** control/telemetry protocol exposed
by the Sunlit / SunEnergyXT **BK215** battery when *local mode* is enabled. This
is **not yet implemented** in this integration — it documents the protocol so a
future opt-in local-polling channel can be built (see issue tracker).

> Source: observed device behaviour plus the official, separate
> `SunEnergyXT/SunEnergyXT-BK` Home Assistant plugin (`iot_class: local_polling`).
> That code is a reference only; anything here is reimplemented, not copied.

## Relationship to the cloud integration

The battery's *local mode* is the **same flag** the cloud exposes:

| Layer | Representation |
|---|---|
| Local register | `t598` (`wifi_system_local_comm_enable`) |
| Cloud read | `localModeEnabled` / `supportLocalMode` in `GET /device/{id}`; `batteryLocalModeEnabled` in `POST /v1.7/strategy/device/status` |
| Cloud write | `POST /v1.7/battery/updateLocalModeConfig` `{enable, deviceSn}` |
| This integration | `switch.*_local_mode` (#160) + binary sensors (#157) |

Local mode must be **on** for the device's TCP server to be reachable. The cloud
stays authoritative for account/family aggregates, tariff, strategy and earnings
(no local equivalent).

**Open questions to verify before implementing:**
- Does enabling local mode *divert* reporting away from the cloud (i.e. are the
  two channels mutually exclusive for fresh data)?
- Does the device accept only **one** TCP client at a time (app vs Home Assistant
  contention)?

## Discovery

mDNS / zeroconf — the same signal this integration already uses for onboarding
(`config_flow.async_step_zeroconf`):

- Service type: `_http._tcp.local.`
- Match: service name contains **`hp-bk215`**
- `host`: from the mDNS A-record (the **reliable** local address — the cloud
  `device.ip` field is frequently `null`)
- `port`, `serial_number`, `sw_version`, `hw_version`: from TXT properties
  (observed control port: **8000**)

## Transport & framing

- Plain **TCP** to `host:port`; persistent connection.
- The device **pushes** telemetry unsolicited (no polling needed).
- Payload is **newline-delimited, compact JSON**, ASCII-encoded. Read in chunks
  and split on lines; ignore non-`{"code":...}` lines and keepalive bytes.
- Heartbeat: if no data for ~60 s, drop and reconnect (poll connection ~every 5 s).

```jsonc
// telemetry push (device -> client)
{"code":24656,"data":{"t211":50,"t33":97,"t34":40,"t536":430,"t537":2, ...}}
// set request (client -> device)
{"code":24662,"data":{"t598":1}}
// set ack (device -> client); data.<field> == 0 means success
{"code":24663,"data":{"t598":0}}
```

### Message codes

| Code (hex) | Code (dec) | Direction | Meaning |
|---|---|---|---|
| `0x6056` | 24662 | client → device | **Set** one or more registers |
| `0x6057` | 24663 | device → client | Set **ack** (`data.<field> == 0` ⇒ success) |
| `0x6052` | 24658 | device → client | Telemetry push |
| `0x6055` | 24661 | device → client | Telemetry push |
| `0x6060` | 24672 | device → client | Telemetry push |

### Writing a register

Build a payload containing **only** the field(s) being changed and send it with
code `0x6056`; every other register is the unset sentinel `0xFFFFFFFF` and is
stripped before sending. Then wait (~2 s) for a `0x6057` ack whose field value is
`0`.

```jsonc
// enable local mode
{"code":24662,"data":{"t598":1}}
// set discharge-min SOC to 10 %
{"code":24662,"data":{"t362":10}}
```

## Value scaling

| Convention | Decode |
|---|---|
| `raw` | use as-is |
| `×0.1` | `value / 10` (MPPT V/A) |
| `×0.01` | `value / 100` (PV power) |
| `×0.001` | `value / 1000` (energy → kWh) |
| `−273` | `value - 273` (cell temperature, °C) |
| `BITn` | bit *n* of the value (heater status, 0=main … 7=module 7) |

## Register map

The system has a **main** unit (BK215 head) plus up to **7** extension modules
(B215). Registers below are grouped by access.

### Writable — switches (booleans)

| Register | Meaning | Default |
|---|---|---|
| `t598` | System **local-mode** enable | on |
| `t700_1` | Charge mode (charging box) | off |
| `t701_1` | Car-charge mode (charging box) | off |
| `t702_1` | Home-appliance mode (charging box) | off |
| `t728` | Allow grid mix during EV charge mode | off |

### Writable — numbers

| Register | Meaning | Range | Unit |
|---|---|---|---|
| `t362` | Allowed discharge **min SOC** | 1–20 | % |
| `t363` | Allowed charge **max SOC** | 70–100 | % |
| `t590` | System **charge power** setpoint | 0–3600 | W |
| `t596` | Auto-off timeout (no input/output) | 15–1440 | min |
| `t597` | Auto-off timeout (reached DOD floor) | 5–1440 | min |
| `t720` | Charging-box home-mode DOD min SOC | 5–20 | % |
| `t721` | Charging-box EV-mode DOD min SOC | 5–40 | % |
| `t727` | Charging-box charge-mode DOD max SOC | 80–100 | % |

### Read — SOC

| Register | Meaning | Unit |
|---|---|---|
| `t211` | System SOC (remaining capacity) | % |
| `t592` | Main real SOC | % |
| `t593`–`t595`, `t1001`–`t1004` | Module 1–7 real SOC | % |
| `t507` / `t508` | Main BMS hw discharge-min / charge-max SOC | % |
| `t509`/`t510`, `t511`/`t512`, `t513`/`t514` | Module 1/2/3 BMS hw min/max SOC | % |
| `t948`/`t949` … `t954`/`t955` | Module 4–7 BMS hw min/max SOC | % |

### Read — power & energy

| Register | Meaning | Unit | Scale |
|---|---|---|---|
| `t33` | Total input power | W | raw |
| `t34` | Total output power | W | raw |
| `t49` | Daily generation | kWh | ×0.001 |
| `t66` | Daily output energy | kWh | ×0.001 |
| `t710` | Charging-box daily AC-charge energy | kWh | ×0.001 |
| `t711` | Charging-box AC input power | W | raw |
| `t701_4` | Car-charge mode power | W | raw |
| `t702_4` | Home-appliance mode power | W | raw |
| `t50`, `t62`–`t65`, `t812`–`t815` | PV1–PV9 input power | W | ×0.01 |

### Read — MPPT (voltage / current)

| Unit | Voltage reg | Current reg | Scale |
|---|---|---|---|
| Main MPPT1 | `t536` | `t537` | ×0.1 |
| Main MPPT2 | `t544` | `t545` | ×0.1 |
| Module 1 MPPT | `t552` | `t553` | ×0.1 |
| Module 2 MPPT | `t560` | `t561` | ×0.1 |
| Module 3 MPPT | `t568` | `t569` | ×0.1 |
| Module 4 MPPT | `t969` | `t970` | ×0.1 |
| Module 5 MPPT | `t977` | `t978` | ×0.1 |
| Module 6 MPPT | `t985` | `t986` | ×0.1 |
| Module 7 MPPT | `t993` | `t994` | ×0.1 |

### Read — temperature & heater

| Register | Meaning | Unit | Scale |
|---|---|---|---|
| `t220` | Main min cell temperature | °C | −273 |
| `t233`, `t246`, `t259`, `t836`, `t849`, `t862`, `t875` | Module 1–7 min cell temperature | °C | −273 |
| `t586` | Heater working status (bitfield: BIT0=main … BIT7=module 7) | — | bits |

### Diagnostics

| Source | Meaning |
|---|---|
| connection state | derived from socket state |
| last report time | timestamp of last telemetry line |
| `t475` | Wireless network RSSI (`-<value> dB`; `0xFFFFFFFF` = unknown) |

## Mapping to existing entities

To keep local and cloud feeding the **same** Home Assistant entities, map the
local registers onto the keys already used by the cloud coordinators, e.g.:

| Local register(s) | Existing key |
|---|---|
| `t211` | `battery_level` |
| `t592`–`t595`, `t1001`–`t1004` | `batteryNSoc` (per module) |
| `t33` / `t34` | `input_power_total` / `output_power_total` |
| `t536`/`t537` … | `batteryMppt1InVol`/`...InCur` (per MPPT) |
| `t586` (bits) | `battery_heater_N` |
| `t507`/`t508` | `hw_soc_min` / `hw_soc_max` |

Writable registers (`t598`, `t362`, `t363`, `t590`, …) become `switch` / `number`
control entities, complementing the cloud-side local-mode switch (#160).
