# core/kpoints.py
from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Tuple

from ..kpoints_generator import CoordType, Kpoints_generator
from .base import VaspFile, logger


class Kpoints(VaspFile):
    """Representation and operations for KPOINTS data."""

    filename = "KPOINTS"

    def __init__(
        self,
        initial: str | None = None,
        base_dir: Path | None = None,
    ) -> None:
        super().__init__(base_dir=base_dir)
        self.content: str = initial or ""

    def as_text(self) -> str:
        """Return KPOINTS content as a single string."""
        return self.content

    def load(self, path: Path | None = None) -> None:
        """Load KPOINTS from disk (or start empty if missing)."""
        path = self._resolve_path(path)

        if not path.exists():
            logger.warning(
                "KPOINTS not found at {}. Starting with empty KPOINTS.",
                path,
            )
            self.content = ""
            return

        self.content = path.read_text()
        logger.info("Loaded KPOINTS from {}.", path)

    def save(self, path: Path | None = None) -> None:
        """Write KPOINTS to the specified path."""
        path = self._resolve_path(path)

        path.parent.mkdir(parents=True, exist_ok=True)
        is_new = not path.exists()

        path.write_text(self.content)

        if is_new:
            logger.info("Created new KPOINTS at {}.", path)
        else:
            logger.info("Updated KPOINTS at {}.", path)

    def automatic_mesh(
        self,
        mesh: Tuple[int, int, int],
        scheme: str = "Gamma",
        comment: str = "Automatic mesh",
        shift: Tuple[int, int, int] = (0, 0, 0),
    ) -> None:
        """Generate KPOINTS from an automatic mesh and update content."""
        gen = Kpoints_generator.automatic_mesh(mesh, scheme, comment, shift)
        self.content = gen.to_string()
        logger.info("Generated new KPOINTS from automatic mesh: {}", mesh)

    def automatic_length(
        self,
        length: float,
        scheme: str = "Auto",
        comment: str = "Automatic length mesh",
    ) -> None:
        """Generate KPOINTS from a length density and update content."""
        gen = Kpoints_generator.automatic_length(length, scheme, comment)
        self.content = gen.to_string()
        logger.info("Generated new KPOINTS from length density: {}", length)

    def explicit(
        self,
        kpts: Iterable[Tuple[float, float, float]],
        weights: Iterable[float] | None = None,
        coord_type: CoordType = "reciprocal",
        comment: str = "Explicit k-points",
    ) -> None:
        """Generate KPOINTS from an explicit list and update content."""
        kpts_list = list(kpts)
        gen = Kpoints_generator.explicit(
            kpts_list,
            weights,
            coord_type,
            comment,
        )
        self.content = gen.to_string()
        logger.info(
            "Generated new KPOINTS from explicit list of {} k-points",
            len(kpts_list),
        )

    def line_mode(
        self,
        segments: Iterable[
            tuple[
                tuple[float, float, float],
                str,
                tuple[float, float, float],
                str,
            ]
        ],
        divisions: int = 40,
        coord_type: CoordType = "fractional",
        comment: str = "Line mode",
    ) -> None:
        """Generate KPOINTS for a band structure calculation."""
        gen = Kpoints_generator.line_mode(segments, divisions, coord_type, comment)
        self.content = gen.to_string()
        logger.info(
            "Generated new KPOINTS in line mode with {} divisions",
            divisions,
        )
