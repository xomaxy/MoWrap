# core/base.py
from __future__ import annotations

import os
import sys
from pathlib import Path

from loguru import logger

LOG_LEVEL = os.getenv("VASPY_LOG_LEVEL", "DEBUG")
DISABLE_LOGS = os.getenv("VASPY_DISABLE_LOGS", "0") == "1"

logger.remove()
logger.add(
    sys.stderr,
    level=LOG_LEVEL,
    format=" <level>{level}</level> | {message}",
)

if DISABLE_LOGS:
    logger.disable(__name__)


class VaspFile:
    """
    Base class for VASP text-based files that know their default filename
    and an optional base directory to load/save from when no path is given.
    """

    filename: str

    def __init__(self, base_dir: Path | None = None) -> None:
        self.base_dir: Path | None = base_dir

    def _resolve_path(self, path: Path | None) -> Path:
        """Resolve a concrete path, falling back to base_dir / filename."""
        if path is not None:
            return path
        if self.base_dir is None:
            msg = (
                "No path provided and base_dir is not set for "
                f"{self.__class__.__name__}."
            )
            raise ValueError(msg)
        return self.base_dir / self.filename
