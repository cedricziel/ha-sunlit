"""Translate decoded BK215 local-protocol registers into cloud entity keys.

The local TCP channel pushes register-keyed maps like
``{"t211": 50, "t536": 43.0, ...}``. The integration's existing sensors
read fields like ``battery_level`` and ``batteryMppt1InVol`` from each
battery's entry in the device-coordinator data dict.

This module is the bridge: a pure function that converts a decoded local
map into a partial cloud-key map suitable for merging into one battery
device's data, so existing entities just refresh faster when local mode
is active. Anything not in the mapping is silently dropped.
"""

from __future__ import annotations

from typing import Any

# tNNN -> tuple of cloud entity keys it should populate. A few local
# registers map to multiple cloud keys because the cloud surfaces the
# same value under more than one name (e.g. system SOC).
_REGISTER_TO_CLOUD_KEYS: dict[str, tuple[str, ...]] = {
    # System aggregates (head + all modules)
    "t211": ("battery_level", "batterySoc"),
    "t33": ("input_power_total",),
    "t34": ("output_power_total",),
    # Head unit MPPTs (1 and 2)
    "t536": ("batteryMppt1InVol",),
    "t537": ("batteryMppt1InCur",),
    "t544": ("batteryMppt2InVol",),
    "t545": ("batteryMppt2InCur",),
    "t50": ("batteryMppt1InPower",),
    "t62": ("batteryMppt2InPower",),
    # Module 1
    "t593": ("battery1Soc",),
    "t552": ("battery1Mppt1InVol",),
    "t553": ("battery1Mppt1InCur",),
    "t63": ("battery1Mppt1InPower",),
    # Module 2
    "t594": ("battery2Soc",),
    "t560": ("battery2Mppt1InVol",),
    "t561": ("battery2Mppt1InCur",),
    "t64": ("battery2Mppt1InPower",),
    # Module 3
    "t595": ("battery3Soc",),
    "t568": ("battery3Mppt1InVol",),
    "t569": ("battery3Mppt1InCur",),
    "t65": ("battery3Mppt1InPower",),
    # Module 4
    "t1001": ("battery4Soc",),
    "t969": ("battery4Mppt1InVol",),
    "t970": ("battery4Mppt1InCur",),
    "t812": ("battery4Mppt1InPower",),
    # Module 5
    "t1002": ("battery5Soc",),
    "t977": ("battery5Mppt1InVol",),
    "t978": ("battery5Mppt1InCur",),
    "t813": ("battery5Mppt1InPower",),
    # Module 6
    "t1003": ("battery6Soc",),
    "t985": ("battery6Mppt1InVol",),
    "t986": ("battery6Mppt1InCur",),
    "t814": ("battery6Mppt1InPower",),
    # Module 7
    "t1004": ("battery7Soc",),
    "t993": ("battery7Mppt1InVol",),
    "t994": ("battery7Mppt1InCur",),
    "t815": ("battery7Mppt1InPower",),
}


def translate_to_device_keys(decoded: dict[str, Any]) -> dict[str, Any]:
    """Convert decoded local registers into cloud entity keys.

    ``decoded`` is the output of :func:`protocol.decode_telemetry` — a map
    of ``tNNN`` register names to already-scaled values. The returned dict
    is a partial cloud-key map to merge into one battery device's slot in
    ``device_coordinator.data["devices"][device_id]``.

    Registers without a known cloud mapping (e.g. ``t592`` head real SOC,
    ``t49`` daily generation, ``t586`` heater bitfield) are dropped. They
    can be surfaced later as new local-only entities; until then the cloud
    poll continues to be the source of truth for derived fields like
    ``stored_energy``, which won't refresh from local pushes alone.
    """
    result: dict[str, Any] = {}
    for register, value in decoded.items():
        for cloud_key in _REGISTER_TO_CLOUD_KEYS.get(register, ()):
            result[cloud_key] = value
    return result
