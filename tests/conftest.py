"""Shared pytest fixtures and import path setup."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config.niches import get_niche  # noqa: E402


@pytest.fixture
def real_estate_niche():
    return get_niche("real_estate")


@pytest.fixture
def saas_niche():
    return get_niche("saas")