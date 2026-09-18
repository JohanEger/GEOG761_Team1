"""Load shared configuration and resolve data paths.

Every notebook and module should get paths and parameters from here rather than
hardcoding them, so that changing the grid size or data location is a one-line edit.
"""

from pathlib import Path
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent


def load_config(path: str | Path | None = None) -> dict:
    """Read config.yaml from the repository root."""
    path = Path(path) if path else REPO_ROOT / "config.yaml"
    with open(path) as f:
        return yaml.safe_load(f)


def data_path(cfg: dict, key: str, *parts: str) -> Path:
    """Build a path inside the shared data folder.

    Example:
        data_path(cfg, "raw", "nukualofa", "20220114")
    """
    root = Path(cfg["paths"]["data_root"])
    return root.joinpath(cfg["paths"][key], *parts)


def aoi_path(cfg: dict, name: str) -> Path:
    """Path to an AOI GeoJSON file in the repo."""
    return REPO_ROOT / cfg["paths"]["aoi_dir"] / name
