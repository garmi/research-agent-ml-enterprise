import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml


def load_config(path: str = "config.yaml") -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def default_outputs_dir() -> str:
    """Outputs directory: RESEARCH_OUTPUTS_DIR when set, otherwise 'outputs'."""
    return os.getenv("RESEARCH_OUTPUTS_DIR") or "outputs"


def ensure_directories(base_dir: Optional[str] = None) -> None:
    base_dir = base_dir or default_outputs_dir()
    dirs = [
        Path(base_dir) / "reports",
        Path(base_dir) / "json",
        Path(base_dir) / "csv",
    ]
    for directory in dirs:
        directory.mkdir(parents=True, exist_ok=True)
