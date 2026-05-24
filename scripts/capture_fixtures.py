#!/usr/bin/env python3
"""Capture sanitized Sunlit API responses as test fixtures.

Reuses the real ``SunlitApiClient`` so the captured payloads match exactly
what the coordinators consume, then strips PII/IDs (tokens, serial numbers,
family/device IDs, names, addresses, coordinates) to stable fake values and
writes the result to ``tests/fixtures/api/``.

Usage (credentials from gitignored .env, same as scripts/verify-api.sh):
    SUNLIT_EMAIL=you@example.com SUNLIT_PASSWORD=... \\
        .venv-314/bin/python scripts/capture_fixtures.py

Relationships are preserved: a given real ID always maps to the same fake,
so e.g. spaceId == familyId still holds after sanitization.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any

import aiohttp

# Make `custom_components` importable when run from the repo root.
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from custom_components.sunlit.api_client import SunlitApiClient  # noqa: E402

FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "api"

# --- sanitization ----------------------------------------------------------
REDACT_KEYS = {
    "access_token",
    "refresh_token",
    "accesstoken",
    "refreshtoken",
    "token",
    "userid",
    "account",
    "email",
    "phone",
    "mobile",
    "password",
}
PII_KEYS = {
    "name",
    "familyname",
    "nickname",
    "username",
    "stationname",
    "address",
    "addressdetail",
    "province",
    "city",
    "district",
    "street",
    "latitude",
    "longitude",
    "lat",
    "lng",
    "lon",
    "timezone",
}
ID_KEYS = {"familyid", "spaceid", "deviceid", "maindeviceid", "id", "homeid", "parentid"}
SN_KEYS = {"devicesn", "sn", "parentdevicesn", "serialnumber", "collectorsn"}

_id_map: dict[Any, int] = {}
_sn_map: dict[Any, str] = {}


def _fake_id(value: Any) -> Any:
    if value is None:
        return None
    if value not in _id_map:
        _id_map[value] = 10000 + len(_id_map) + 1
    fake = _id_map[value]
    return str(fake) if isinstance(value, str) else fake


def _fake_sn(value: Any) -> Any:
    if value is None:
        return None
    if value not in _sn_map:
        _sn_map[value] = f"SN{1000 + len(_sn_map) + 1:04d}"
    return _sn_map[value]


def sanitize(obj: Any) -> Any:
    """Recursively sanitize a JSON-like structure in place-ish (returns new)."""
    if isinstance(obj, dict):
        out = {}
        for key, value in obj.items():
            lk = key.lower()
            if lk in REDACT_KEYS:
                out[key] = "REDACTED"
            elif lk in SN_KEYS:
                out[key] = (
                    [_fake_sn(v) for v in value]
                    if isinstance(value, list)
                    else _fake_sn(value)
                )
            elif lk in ID_KEYS and isinstance(value, (str, int)):
                out[key] = _fake_id(value)
            elif lk in PII_KEYS:
                out[key] = "REDACTED" if value is not None else None
            else:
                out[key] = sanitize(value)
        return out
    if isinstance(obj, list):
        return [sanitize(item) for item in obj]
    return obj


def _key_for(real_id: Any) -> str:
    """Filename-safe key based on the sanitized id."""
    return str(_fake_id(real_id))


def write_fixture(name: str, data: Any) -> None:
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    path = FIXTURE_DIR / f"{name}.json"
    path.write_text(json.dumps(sanitize(data), indent=2, ensure_ascii=False) + "\n")
    print(f"  wrote {path.relative_to(REPO_ROOT)}")


async def _try(label: str, coro):
    try:
        return await coro
    except Exception as err:  # noqa: BLE001 - capture tool, log and continue
        print(f"  ! {label}: {type(err).__name__}: {err}")
        return None


async def main() -> None:
    email = os.environ.get("SUNLIT_EMAIL")
    password = os.environ.get("SUNLIT_PASSWORD")
    token = os.environ.get("SUNLIT_TOKEN")
    if not token and not (email and password):
        raise SystemExit("Set SUNLIT_EMAIL + SUNLIT_PASSWORD, or SUNLIT_TOKEN.")

    async with aiohttp.ClientSession() as session:
        client = SunlitApiClient(session, access_token=token)
        if not token:
            print("Logging in…")
            await client.login(email, password)
        print("Authenticated.\n")

        print("families:")
        families = await _try("fetch_families", client.fetch_families()) or []
        write_fixture("families", families)

        for family in families:
            fid = family.get("id")
            fkey = _key_for(fid)
            print(f"\nfamily {fkey}:")

            devices = (
                await _try("fetch_device_list", client.fetch_device_list(fid)) or []
            )
            write_fixture(f"device_list_family_{fkey}", devices)

            for endpoint, coro in (
                ("space_index", client.fetch_space_index(fid)),
                ("space_soc", client.fetch_space_soc(fid)),
                ("current_strategy", client.fetch_space_current_strategy(fid)),
                ("strategy_history", client.fetch_space_strategy_history(fid)),
                ("charging_box_strategy", client.get_charging_box_strategy(int(fid))),
            ):
                result = await _try(endpoint, coro)
                if result is not None:
                    write_fixture(f"{endpoint}_family_{fkey}", result)

            for device in devices:
                did = device.get("deviceId")
                dtype = device.get("deviceType", "UNKNOWN")
                dkey = _key_for(did)
                print(f"\n  device {dkey} ({dtype}):")

                stats = await _try(
                    "fetch_device_statistics", client.fetch_device_statistics(did)
                )
                if stats is not None:
                    write_fixture(f"device_statistics_{dtype}_{dkey}", stats)
                    if dtype == "ENERGY_STORAGE_BATTERY":
                        _report_battery_mppt(stats)

                details = await _try(
                    "fetch_device_details", client.fetch_device_details(did)
                )
                if details is not None:
                    write_fixture(f"device_details_{dtype}_{dkey}", details)

    print(f"\nID map: {len(_id_map)} ids, {len(_sn_map)} serials remapped.")
    print(f"Fixtures in {FIXTURE_DIR.relative_to(REPO_ROOT)}/")


def _report_battery_mppt(stats: dict) -> None:
    """Print MPPT-related fields for #72 diagnosis."""
    print("    #72 — MPPT-related fields in battery statistics:")
    found = False
    for key in sorted(stats):
        if "mppt" in key.lower() or "module" in key.lower():
            print(f"      {key} = {stats[key]!r}")
            found = True
    if not found:
        print("      (no keys containing 'mppt' or 'module')")
    print(f"    all stat keys: {sorted(stats)}")


if __name__ == "__main__":
    asyncio.run(main())
