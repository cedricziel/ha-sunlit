#!/usr/bin/env python3
"""Probe whether enabling local mode diverts cloud freshness.

Open question from docs/local-protocol.md: when the BK215 has local mode on
(and HA is connected to the local TCP socket), does the device still upload
fresh values to the cloud, or does the cloud go stale?

This script samples the cloud-side battery state at a fixed interval and
prints a small table showing whether the dynamic fields change between
samples. The signal we're after:

  * inputPowerTotal / outputPowerTotal change every few seconds on a real
    battery, so if they're identical across 60+ s of samples the cloud is
    almost certainly stale.
  * batterySoc moves slowly during charge/discharge, less diagnostic.

Run two passes for a clean experiment:

  1. With nothing locally connected (HA disabled / verify-local.py not
     running). Just the cloud channel.
  2. With ``scripts/verify-local.py`` listening in another shell, so the
     device's TCP socket is owned.

If pass 1 shows fresh cloud values but pass 2 shows stale ones, the
device diverts when HA holds the LAN socket. If both passes are stale,
local mode itself diverts regardless of who's connected.

Usage::

    SUNLIT_EMAIL=you@example.com SUNLIT_PASSWORD=secret \
      .venv/bin/python scripts/probe-cloud-freshness.py --samples 6 --interval 30
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime
import os
from pathlib import Path
import sys

import aiohttp

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from custom_components.sunlit.api_client import SunlitApiClient  # noqa: E402

# Fields we expect to change on a working battery; stale values here are
# the strongest signal that the cloud channel is no longer updating.
DYNAMIC_FIELDS = (
    "inputPowerTotal",
    "outputPowerTotal",
    "batterySoc",
    "batteryLevel",
    "batteryMppt1InPower",
    "batteryMppt2InPower",
)


def _now() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _load_env() -> None:
    """Tolerantly source key=value lines from a local .env file."""
    env_path = REPO_ROOT / ".env"
    if not env_path.is_file():
        return
    for raw in env_path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


async def _resolve_token(client: SunlitApiClient) -> str | None:
    if token := os.environ.get("SUNLIT_TOKEN"):
        return token
    email = os.environ.get("SUNLIT_EMAIL")
    password = os.environ.get("SUNLIT_PASSWORD")
    if not (email and password):
        return None
    print(f"[{_now()}]  logging in as {email}")
    login = await client.login(email, password)
    return login.get("access_token")


async def _pick_battery(client: SunlitApiClient) -> tuple[str, str, str] | None:
    """Return (family_id, device_id, device_sn) for the first battery."""
    families = await client.fetch_families()
    for family in families:
        family_id = str(family["id"])
        devices = await client.fetch_device_list(family_id)
        for device in devices:
            if device.get("deviceType") == "ENERGY_STORAGE_BATTERY":
                return family_id, str(device["deviceId"]), device.get("deviceSn", "")
    return None


async def _sample(
    client: SunlitApiClient, family_id: str, device_id: str
) -> dict[str, object]:
    """Pull dynamic fields from both endpoints the integration consumes.

    The cloud splits battery state across two endpoints: ``device/list`` carries
    the input/output power totals, while ``device/statistics/static`` carries
    the MPPT readings. Statistics consistently returns null for the totals on
    battery devices, so we sample list-side for those.
    """
    sample: dict[str, object] = dict.fromkeys(DYNAMIC_FIELDS)
    devices = await client.fetch_device_list(family_id)
    for device in devices:
        if str(device.get("deviceId")) == device_id:
            for field in ("inputPowerTotal", "outputPowerTotal"):
                if device.get(field) is not None:
                    sample[field] = device[field]
            break
    stats = await client.fetch_device_statistics(device_id)
    for field in (
        "batterySoc",
        "batteryLevel",
        "batteryMppt1InPower",
        "batteryMppt2InPower",
    ):
        if stats.get(field) is not None:
            sample[field] = stats[field]
    return sample


def _format_sample(idx: int, sample: dict[str, object]) -> str:
    values = "  ".join(f"{k}={v!r}" for k, v in sample.items())
    return f"  #{idx + 1:>2} [{_now()}]  {values}"


def _summarize(samples: list[dict[str, object]]) -> None:
    """Per-field, count distinct values and flag suspicious frozen ones."""
    if len(samples) < 2:
        print("\n(not enough samples for a freshness verdict)")
        return
    print("\nFreshness per field:")
    for field in DYNAMIC_FIELDS:
        values = [s.get(field) for s in samples]
        distinct = {v for v in values if v is not None}
        if not distinct:
            verdict = "no data"
        elif len(distinct) == 1:
            verdict = f"FROZEN at {next(iter(distinct))!r}"
        else:
            verdict = f"{len(distinct)} distinct values across {len(samples)} samples"
        print(f"  {field}: {verdict}")


async def _amain(args: argparse.Namespace) -> int:
    _load_env()

    async with aiohttp.ClientSession() as session:
        client = SunlitApiClient(session)
        token = await _resolve_token(client)
        if not token:
            print(
                "No credentials in env. Set SUNLIT_EMAIL+SUNLIT_PASSWORD or "
                "SUNLIT_TOKEN, or populate .env at the repo root."
            )
            return 2
        client._access_token = token

        picked = await _pick_battery(client)
        if picked is None:
            print("No ENERGY_STORAGE_BATTERY found in any configured family.")
            return 3
        family_id, device_id, device_sn = picked
        print(
            f"[{_now()}]  family={family_id} battery deviceId={device_id} "
            f"sn={device_sn or '?'}"
        )
        print(
            f"[{_now()}]  sampling {len(DYNAMIC_FIELDS)} fields, "
            f"{args.samples} times, every {args.interval:.1f}s"
        )
        print()

        samples: list[dict[str, object]] = []
        for idx in range(args.samples):
            sample = await _sample(client, family_id, device_id)
            print(_format_sample(idx, sample))
            samples.append(sample)
            if idx < args.samples - 1:
                await asyncio.sleep(args.interval)

        _summarize(samples)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--samples", type=int, default=6, help="Number of samples (default: 6)."
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=30.0,
        help="Seconds between samples (default: 30).",
    )
    args = parser.parse_args()
    return asyncio.run(_amain(args))


if __name__ == "__main__":
    sys.exit(main())
