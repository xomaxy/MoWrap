from __future__ import annotations

from importlib.resources import files
from pathlib import Path
from typing import List

from loguru import logger

from .. import text_helpers as th

_INCAR_TEMPLATES_PKG = f"{__name__}.incar"

logger.info("INCAR templates package: {}", _INCAR_TEMPLATES_PKG)


def list_incar_templates() -> List[str]:
    """Return available INCAR template names (without extension)."""
    pkg = files(_INCAR_TEMPLATES_PKG)
    names: List[str] = []

    for entry in pkg.iterdir():
        # convert to pathlib.Path-like behavior safely
        p = Path(entry.name)

        if p.suffix.lower() != ".incar":
            continue

        names.append(p.stem)

    return sorted(names)


def load_incar_template(name: str):
    """Load an INCAR template as the internal dict structure."""
    pkg = files(_INCAR_TEMPLATES_PKG)

    # allow with or without ".incar"
    stem = Path(name).stem
    target = pkg / f"{stem}.incar"

    if not target.is_file():
        available_list = list_incar_templates()
        available = ", ".join(available_list) or "<none>"
        logger.error(
            "Requested INCAR template {!r} not found. Available: {}",
            name,
            available,
        )
        raise KeyError(f"Unknown INCAR template: {name!r} (available: {available})")

    text = target.read_text()
    cfg = th.parse_config_text(text)

    logger.info(
        "Loaded INCAR template {!r} ({} params) from {}",
        stem,
        len(cfg),
        target,
    )
    return cfg
