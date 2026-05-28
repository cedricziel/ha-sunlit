"""Opt-in local-mode (TCP) channel for the BK215 battery.

When a battery has local mode enabled and its LAN address is known (from
zeroconf), the integration can talk to it directly over TCP for real-time push
telemetry instead of waiting on the 30 s cloud poll. The cloud channel stays
authoritative and acts as the floor if the local connection drops.

See ``docs/local-protocol.md`` for the reverse-engineered protocol reference.
"""
