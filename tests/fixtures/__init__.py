"""Helpers for loading sanitized API fixtures.

Fixtures under ``tests/fixtures/api/`` are captured from the live Sunlit API
by ``scripts/capture_fixtures.py`` (PII/IDs sanitized to stable fakes). They
let tests run against real response shapes instead of hand-built mocks.
"""

import json
from pathlib import Path

_API_DIR = Path(__file__).parent / "api"


def load_api_fixture(name: str):
    """Load a captured API fixture by file stem (without the .json suffix)."""
    return json.loads((_API_DIR / f"{name}.json").read_text())
