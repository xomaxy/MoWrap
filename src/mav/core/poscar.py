# core/poscar.py
from __future__ import annotations

from io import StringIO
from pathlib import Path
from typing import List

import nglview as nv

from .base import VaspFile, logger

try:
    from ase.io import read, write
    from ase.visualize import view
except ImportError:
    read, write, view = None, None, None


class Poscar(VaspFile):
    """Representation and operations for POSCAR data."""

    filename = "POSCAR"

    def __init__(
        self,
        initial: str | None = None,
        base_dir: Path | None = None,
    ) -> None:
        super().__init__(base_dir=base_dir)
        self.content: str = initial or ""

    @property
    def species(self) -> List[str]:
        """Extract atomic species from the 6th line of POSCAR content."""
        if not self.content:
            return []
        lines = self.content.strip().split("\n")
        if len(lines) < 6:
            logger.warning(
                "POSCAR has fewer than 6 lines, cannot determine species.",
            )
            return []
        return lines[5].strip().split()

    def as_text(self) -> str:
        """Return POSCAR content as a single string."""
        return self.content

    def load(self, path: Path | None = None) -> None:
        """Load POSCAR from disk (or start empty if missing)."""
        path = self._resolve_path(path)

        if not path.exists():
            logger.warning(
                "POSCAR not found at {}. Starting with empty POSCAR.",
                path,
            )
            self.content = ""
            return

        self.content = path.read_text()
        logger.info("Loaded POSCAR from {}.", path)

    def load_from_ase(
        self,
        path: Path | str,
        cell: List[float] | None = None,
        pbc: bool = True,
        sort: bool = True,
        vasp5: bool = True,
    ) -> None:
        """Load atomic structure using ASE and convert to POSCAR."""
        if read is None or write is None:
            logger.error(
                "ASE is not installed. Cannot load from ASE-compatible file.",
            )
            return

        atoms = read(path)

        if cell:
            atoms.cell = cell
        atoms.pbc = pbc

        buf = StringIO()
        write(buf, atoms, format="vasp", vasp5=vasp5, sort=sort)
        self.content = buf.getvalue()
        logger.info(
            "Loaded POSCAR from ASE-readable file: {} (cell={}, pbc={}, "
            "sort={}, vasp5={})",
            path,
            cell,
            pbc,
            sort,
            vasp5,
        )

    def save(self, path: Path | None = None) -> None:
        """Write POSCAR to the specified path."""
        if not self.content:
            return

        path = self._resolve_path(path)

        path.parent.mkdir(parents=True, exist_ok=True)
        is_new = not path.exists()

        path.write_text(self.content)

        if is_new:
            logger.info("Created new POSCAR at {}.", path)
        else:
            logger.info("Updated POSCAR at {}.", path)

    def view_3d(self, viewer: str = "ngl") -> "nv.NGLWidget | None":
        """Visualize the structure using ASE's viewer."""
        if read is None or view is None:
            logger.error("ASE is not installed. Cannot display 3D view.")
            return None

        if not self.content:
            logger.warning("POSCAR is empty, nothing to view.")
            return None

        with StringIO(self.content) as f:
            atoms = read(f, format="vasp")

        if viewer == "ngl":
            return nv.show_ase(atoms)
        view(atoms)
        return None
