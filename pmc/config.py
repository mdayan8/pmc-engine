"""
PMC Engine — Configuration Manager
====================================
TOML-based config. Supports global (~/.pmc/config.yaml) and
project-level (.pmc.yaml) configuration files.
"""

import os
import yaml
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ─── Modes ──────────────────────────────────────────────────────────────────

class CompressionMode:
    CONSERVATIVE = "conservative"
    BALANCED = "balanced"
    AGGRESSIVE = "aggressive"

    _THRESHOLDS = {
        CONSERVATIVE: {"tier1": 2.0, "tier2": 0.7, "tier3": 0.2, "desc": "40-50% reduction, 98%+ quality match"},
        BALANCED: {"tier1": 2.5, "tier2": 1.0, "tier3": 0.3, "desc": "50-65% reduction, 95%+ quality match"},
        AGGRESSIVE: {"tier1": 3.5, "tier2": 1.5, "tier3": 0.5, "desc": "65-80% reduction, 90%+ quality match"},
    }

    @staticmethod
    def thresholds(mode: str) -> dict:
        if mode in CompressionMode._THRESHOLDS:
            return CompressionMode._THRESHOLDS[mode]
        return CompressionMode._THRESHOLDS[CompressionMode.BALANCED]

    @staticmethod
    def default_weights() -> dict:
        return {
            "direct": 3.0,
            "hop1": 1.5,
            "hop2": 0.6,
            "import": 0.5,
            "config_key": 1.0,
            "type_ref": 1.0,
            "test_map": 0.8,
            "convention": 0.4,
            "semantic": 0.4,
            "cache_penalty": 0.9,
        }

    @staticmethod
    def all_modes() -> list[str]:
        return [CompressionMode.CONSERVATIVE, CompressionMode.BALANCED,
                CompressionMode.AGGRESSIVE]


# ─── Config ─────────────────────────────────────────────────────────────────

@dataclass
class PMCConfig:
    mode: str = CompressionMode.BALANCED
    proxy_port: int = 8080
    proxy_host: str = "0.0.0.0"
    log_level: str = "INFO"
    max_tier1_per_query: int = 8
    max_tier2_per_query: int = 20
    max_tier3_per_query: int = 40
    max_blast_symbols: int = 8
    max_expand_per_response: int = 5
    pre_expand_threshold: int = 3  # if AI mentions N+ symbols from same file
    verify_tasks: int = 20
    weights: dict = field(default_factory=CompressionMode.default_weights)
    threshold_tier1: float = 2.5
    threshold_tier2: float = 1.0
    threshold_tier3: float = 0.3
    enabled: bool = True

    @classmethod
    def load(cls, project_dir: str | None = None) -> "PMCConfig":
        """Load config from global + project files, project overrides global."""
        cfg = cls()

        # Global config
        global_path = Path.home() / ".pmc" / "config.yaml"
        if global_path.exists():
            try:
                data = yaml.safe_load(global_path.read_text()) or {}
                cfg._apply(data)
            except Exception:
                pass

        # Project config
        if project_dir:
            for pname in (".pmc.yaml", ".pmc.yml", "pmc.yaml", "pmc.yml"):
                proj_path = Path(project_dir) / pname
                if proj_path.exists():
                    try:
                        data = yaml.safe_load(proj_path.read_text()) or {}
                        cfg._apply(data)
                    except Exception:
                        pass

        # Apply mode-based thresholds
        cfg._apply_mode()

        return cfg

    def _apply(self, data: dict):
        for key, val in data.items():
            if key == "weights" and isinstance(val, dict):
                self.weights.update(val)
            elif hasattr(self, key):
                setattr(self, key, val)

    def _apply_mode(self):
        th = CompressionMode.thresholds(self.mode)
        self.threshold_tier1 = th["tier1"]
        self.threshold_tier2 = th["tier2"]
        self.threshold_tier3 = th["tier3"]

    def save(self, path: str):
        """Save config to a YAML file."""
        data = {
            "mode": self.mode,
            "proxy_port": self.proxy_port,
            "proxy_host": self.proxy_host,
            "log_level": self.log_level,
            "max_tier1_per_query": self.max_tier1_per_query,
            "max_tier2_per_query": self.max_tier2_per_query,
            "max_tier3_per_query": self.max_tier3_per_query,
            "max_blast_symbols": self.max_blast_symbols,
            "max_expand_per_response": self.max_expand_per_response,
            "pre_expand_threshold": self.pre_expand_threshold,
            "verify_tasks": self.verify_tasks,
            "enabled": self.enabled,
            "threshold_tier1": round(self.threshold_tier1, 2),
            "threshold_tier2": round(self.threshold_tier2, 2),
            "threshold_tier3": round(self.threshold_tier3, 2),
            "weights": {k: round(v, 2) for k, v in self.weights.items()},
        }
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w") as f:
            yaml.dump(data, f, default_flow_style=False)
