"""
core/config_loader.py
----------------------
Loads core/config.toml and provides typed access to all settings.

Usage:
    from core import load_config
    cfg = load_config()
    print(cfg["sampling"]["dc_interval"])  # 4.0
"""

import tomllib
from pathlib import Path
from typing import Any, Dict

_CONFIG_PATH = Path(__file__).parent / "config.toml"


def load_config(path: Path = _CONFIG_PATH) -> Dict[str, Any]:
    """
    Parse and return the TOML config as a plain dict.

    Args:
        path: Override the config file location (useful in tests).

    Returns:
        Nested dict matching the TOML structure.

    Raises:
        FileNotFoundError: If config.toml doesn't exist at `path`.
    """
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}")
    with open(path, "rb") as f:
        return tomllib.load(f)


if __name__ == "__main__":
    import json
    cfg = load_config()
    print(json.dumps(cfg, indent=2))
