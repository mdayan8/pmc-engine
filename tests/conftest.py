"""
Shared test fixtures for PMC Engine tests.
"""

import os
import sys
import pytest
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from pmc import PMCEngine, PMCConfig, CompressionMode


SAMPLE_AUTH_DIR = os.path.join(os.path.dirname(__file__), "test_fixtures", "sample_auth")


@pytest.fixture
def sample_auth_dir() -> str:
    """Path to sample auth codebase."""
    return SAMPLE_AUTH_DIR


@pytest.fixture
def engine() -> PMCEngine:
    """PMC engine with default config."""
    config = PMCConfig()
    config.mode = CompressionMode.BALANCED
    config._apply_mode()
    return PMCEngine(config=config)


@pytest.fixture
def indexed_engine(sample_auth_dir) -> PMCEngine:
    """PMC engine with pre-built index."""
    config = PMCConfig()
    config.mode = CompressionMode.BALANCED
    config._apply_mode()
    eng = PMCEngine(config=config)
    eng.index(sample_auth_dir)
    return eng


@pytest.fixture
def conservative_engine(sample_auth_dir) -> PMCEngine:
    """PMC engine in conservative mode with index."""
    config = PMCConfig()
    config.mode = CompressionMode.CONSERVATIVE
    config._apply_mode()
    eng = PMCEngine(config=config)
    eng.index(sample_auth_dir)
    return eng


@pytest.fixture
def aggressive_engine(sample_auth_dir) -> PMCEngine:
    """PMC engine in aggressive mode with index."""
    config = PMCConfig()
    config.mode = CompressionMode.AGGRESSIVE
    config._apply_mode()
    eng = PMCEngine(config=config)
    eng.index(sample_auth_dir)
    return eng
