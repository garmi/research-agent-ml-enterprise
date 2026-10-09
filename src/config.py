from pathlib import Path
from typing import Any, Dict

import yaml


def load_config(path: str = "config.yaml") -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def ensure_directories(base_dir: str = "outputs") -> None:
    dirs = [
        Path(base_dir) / "reports",
        Path(base_dir) / "json",
        Path(base_dir) / "csv",
    ]
    for directory in dirs:
        directory.mkdir(parents=True, exist_ok=True)
