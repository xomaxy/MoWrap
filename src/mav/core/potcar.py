# core/potcar.py
from __future__ import annotations

from pathlib import Path

from .base import VaspFile, logger


class Potcar(VaspFile):
    """Representation and operations for POTCAR data."""

    filename = "POTCAR"
    BASE_PATH = Path("/sw/ex109genoa/vasp/pot54")

    def __init__(
        self,
        initial: str | None = None,
        base_dir: Path | None = None,
    ) -> None:
        super().__init__(base_dir=base_dir)
        self.content: str = initial or ""

    def load(self, path: Path | None = None) -> None:
        """Load POTCAR from disk (or start empty if missing)."""
        path = self._resolve_path(path)

        if not path.exists():
            self.content = ""
            logger.warning(
                "POTCAR not found at {}. Starting with empty POTCAR.",
                path,
            )
            return

        self.content = path.read_text()
        logger.info("Loaded POTCAR from {}.", path)

    def save(self, path: Path | None = None) -> None:
        """Write POTCAR to the specified path."""
        if not self.content:
            return

        path = self._resolve_path(path)

        path.parent.mkdir(parents=True, exist_ok=True)
        is_new = not path.exists()

        path.write_text(self.content)

        if is_new:
            logger.info("Created new POTCAR at {}.", path)
        else:
            logger.info("Updated POTCAR at {}.", path)

    def generate(self, species: list[str], potential_type: str) -> None:
        """Generate POTCAR by concatenating files for the given species."""
        if not species:
            logger.warning("Cannot generate POTCAR: species list is empty.")
            return

        potential_dir = self.BASE_PATH / potential_type
        if not potential_dir.exists():
            logger.error(
                "Potential directory not found: {}. Cannot generate POTCAR.",
                potential_dir,
            )
            return

        potcar_parts = []
        for symbol in species:
            potcar_file = potential_dir / symbol / "POTCAR"
            if not potcar_file.exists():
                logger.error(
                    "POTCAR file for species '{}' not found at {}. Aborting.",
                    symbol,
                    potcar_file,
                )
                return
            potcar_parts.append(potcar_file.read_text())

        self.content = "".join(potcar_parts)
        logger.info(
            "Generated new POTCAR for species ({}) using potential '{}'.",
            ", ".join(species),
            potential_type,
        )
