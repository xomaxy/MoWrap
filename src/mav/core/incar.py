# core/incar.py
from __future__ import annotations

from collections.abc import MutableMapping
from pathlib import Path
from typing import Dict, Iterator, List, Mapping

from .. import templates
from .. import text_helpers as th
from .base import VaspFile, logger


class Incar(VaspFile, MutableMapping[str, dict]):
    """Representation and operations for INCAR data."""

    filename = "INCAR"

    def __init__(
        self,
        initial: Mapping[str, dict] | None = None,
        base_dir: Path | None = None,
    ) -> None:
        super().__init__(base_dir=base_dir)
        self._data: Dict[str, dict] = {}
        if initial:
            self._data.update(initial)

    def __getitem__(self, key: str) -> dict:
        return self._data[key]

    def __setitem__(self, key: str, value: dict) -> None:
        self._data[key] = value

    def __delitem__(self, key: str) -> None:
        del self._data[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)

    @property
    def content(self) -> Dict[str, dict]:
        """Direct access to the internal dictionary holding INCAR data."""
        return self._data

    def as_dict(self) -> Dict[str, dict]:
        """Return the internal dictionary."""
        return self.content

    def as_text(self) -> str:
        """Return INCAR file content as a single string."""
        return th.config_dict_to_text(self.content)

    def load(self, path: Path | None = None) -> None:
        """Load INCAR from disk (or start empty if missing)."""
        path = self._resolve_path(path)

        if not path.exists():
            logger.warning(
                "INCAR not found at {}. Starting with empty INCAR configuration.",
                path,
            )
            self._data.clear()
            return

        text = path.read_text()
        self._data = th.parse_config_text(text)
        logger.info("Loaded INCAR from {}.", path)

    def save(self, path: Path | None = None) -> None:
        """Write INCAR to the specified path."""
        path = self._resolve_path(path)

        path.parent.mkdir(parents=True, exist_ok=True)
        is_new = not path.exists()

        text = self.as_text()
        path.write_text(text)

        if is_new:
            logger.info("Created new INCAR at {}.", path)
        else:
            logger.info("Updated INCAR at {}.", path)

    def apply_template(self, name: str, overwrite: bool = True) -> None:
        """Merge an INCAR template into current config."""
        tmpl = templates.load_incar_template(name)

        if overwrite:
            self.content.update(tmpl)
        else:
            for key, value in tmpl.items():
                self.content.setdefault(key, value)

        logger.info(
            "Applied INCAR template {!r} (overwrite={}, +{} keys, total={})",
            name,
            overwrite,
            len(tmpl),
            len(self.content),
        )

    @staticmethod
    def list_templates() -> List[str]:
        """Return available template names and log them."""
        names = templates.list_incar_templates()
        logger.info(
            "Available INCAR templates: {}",
            ", ".join(names) or "<none>",
        )
        return names
