from __future__ import annotations

import os
import sys
from collections.abc import MutableMapping
from functools import partial
from io import StringIO
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Mapping, Tuple

import nglview as nv
from loguru import logger

try:
    from ase.io import read, write
    from ase.visualize import view
except ImportError:
    read, write, view = None, None, None

from . import templates
from . import text_helpers as th
from .kpoints_generator import CoordType, Kpoints_generator

# ---- logging setup ---------------------------------------------------------

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


# ---- INCAR object ----------------------------------------------------------


class Incar(MutableMapping[str, dict]):
    """Representation + operations for INCAR data."""

    def __init__(self, initial: Mapping[str, dict] | None = None) -> None:
        self._data: Dict[str, dict] = {}
        if initial:
            self._data.update(initial)

    # --- dict-like behaviour ------------------------------------------------

    def __getitem__(self, key: str) -> dict:
        return self._data[key]

    def __setitem__(self, key: str, value: dict) -> None:
        self._data[key] = value

    def __delitem__(self, key: str) -> None:
        del self._data[key]

    def __iter__(self):
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)

    @property
    def content(self) -> Dict[str, dict]:
        """Direct access to the internal dictionary holding INCAR data."""
        return self._data

    def as_dict(self) -> Dict[str, dict]:
        """Return the internal dictionary. For consistency, prefer .content."""
        return self.content

    def as_text(self) -> str:
        """Return INCAR file content as a single string."""
        return th.config_dict_to_text(self.content)

    # --- file operations ----------------------------------------------------

    def load(self, path: Path) -> None:
        """Load INCAR from disk (or start empty if missing)."""
        if not path.exists():
            logger.warning(
                "INCAR not found at {}. Starting with empty INCAR configuration.",
                path,
            )
            self._data.clear()
            return

        text = path.read_text()
        self._data = th.parse_config_text(text)

    def save(self, path: Path) -> None:
        """Write INCAR to the specified path."""
        path.parent.mkdir(parents=True, exist_ok=True)
        is_new = not path.exists()

        text = self.as_text()
        path.write_text(text)

        if is_new:
            logger.info("Created new INCAR at {}.", path)
        else:
            logger.info("Updated INCAR at {}.", path)

    # --- templates ----------------------------------------------------------

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


# ---- POSCAR object ---------------------------------------------------------


class Poscar:
    """Representation and operations for POSCAR data."""

    def __init__(self, initial: str | None = None) -> None:
        self.content: str = initial or ""

    @property
    def species(self) -> List[str]:
        """Extract atomic species from the 6th line of POSCAR content."""
        if not self.content:
            return []
        lines = self.content.strip().split("\n")
        if len(lines) < 6:
            logger.warning("POSCAR has fewer than 6 lines, cannot determine species.")
            return []
        return lines[5].strip().split()

    def as_text(self) -> str:
        """Return POSCAR content as a single string."""
        return self.content

    def load(self, path: Path) -> None:
        """Load POSCAR from disk (or start empty if missing)."""
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
        """Load atomic structure from a file using ASE and convert to POSCAR."""
        if read is None or write is None:
            logger.error("ASE is not installed. Cannot load from ASE-compatible file.")
            return

        atoms = read(path)

        if cell:
            atoms.cell = cell
        atoms.pbc = pbc

        buf = StringIO()
        write(buf, atoms, format="vasp", vasp5=vasp5, sort=sort)
        self.content = buf.getvalue()
        logger.info(
            "Loaded POSCAR from ASE-readable file: {} (cell={}, pbc={}, sort={}, vasp5={})",
            path,
            cell,
            pbc,
            sort,
            vasp5,
        )

    def save(self, path: Path) -> None:
        """Write POSCAR to the specified path."""
        if not self.content:
            return

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
            return

        if not self.content:
            logger.warning("POSCAR is empty, nothing to view.")
            return

        from io import StringIO

        with StringIO(self.content) as f:
            atoms = read(f, format="vasp")

        return nv.show_ase(atoms)


# ---- POTCAR object ---------------------------------------------------------


class Potcar:
    """Representation and operations for POTCAR data."""

    BASE_PATH = Path("/sw/ex109genoa/vasp/pot54")

    def __init__(self, initial: str | None = None) -> None:
        self.content: str = initial or ""

    def load(self, path: Path) -> None:
        """Load POTCAR from disk (or start empty if missing)."""
        if not path.exists():
            self.content = ""
            return

        self.content = path.read_text()
        logger.info("Loaded POTCAR from {}.", path)

    def save(self, path: Path) -> None:
        """Write POTCAR to the specified path."""
        if not self.content:
            return

        path.parent.mkdir(parents=True, exist_ok=True)
        is_new = not path.exists()

        path.write_text(self.content)

        if is_new:
            logger.info("Created new POTCAR at {}.", path)
        else:
            logger.info("Updated POTCAR at {}.", path)

    def generate(self, species: List[str], potential_type: str) -> None:
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
        for s in species:
            potcar_file = potential_dir / s / "POTCAR"
            if not potcar_file.exists():
                logger.error(
                    "POTCAR file for species '{}' not found at {}. Aborting.",
                    s,
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


# ---- KPOINTS object --------------------------------------------------------


class Kpoints:
    """Representation and operations for KPOINTS data."""

    def __init__(self, initial: str | None = None) -> None:
        self.content: str = initial or ""

    def as_text(self) -> str:
        """Return KPOINTS content as a single string."""
        return self.content

    def load(self, path: Path) -> None:
        """Load KPOINTS from disk (or start empty if missing)."""
        if not path.exists():
            logger.warning(
                "KPOINTS not found at {}. Starting with empty KPOINTS.",
                path,
            )
            self.content = ""
            return

        self.content = path.read_text()
        logger.info("Loaded KPOINTS from {}.", path)

    def save(self, path: Path) -> None:
        """Write KPOINTS to the specified path."""

        path.parent.mkdir(parents=True, exist_ok=True)
        is_new = not path.exists()

        path.write_text(self.content)

        if is_new:
            logger.info("Created new KPOINTS at {}.", path)
        else:
            logger.info("Updated KPOINTS at {}.", path)

    # --- generators ---------------------------------------------------------

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
        gen = Kpoints_generator.explicit(kpts, weights, coord_type, comment)
        self.content = gen.to_string()
        logger.info(
            "Generated new KPOINTS from explicit list of {} k-points", len(list(kpts))
        )

    def line_mode(
        self,
        segments: Iterable[
            Tuple[
                Tuple[float, float, float],
                str,
                Tuple[float, float, float],
                str,
            ]
        ],
        divisions: int = 40,
        coord_type: CoordType = "fractional",
        comment: str = "Line mode",
    ) -> None:
        """Generate KPOINTS for a band structure calculation and update content."""
        gen = Kpoints_generator.line_mode(segments, divisions, coord_type, comment)
        self.content = gen.to_string()
        logger.info("Generated new KPOINTS in line mode with {} divisions", divisions)


# ---- main object -----------------------------------------------------------


class Vaspy:
    """Minimal VASP IO helper focused on INCAR and calc layout."""

    def __init__(
        self,
        root_path: Path | str | None = None,
        input_path: str | None = None,
        output_path: str | None = None,
        auto_save: bool = True,
    ) -> None:
        self.root_path = Path(root_path) if root_path is not None else Path(".")
        self.input_path = input_path
        self.output_path = output_path
        self.auto_save = auto_save

        # VASP file objects
        self._incar = Incar()
        self._poscar = Poscar()
        self._potcar = Potcar()
        self._kpoints = Kpoints()

        # Dynamically bind save methods to this manager instance
        self._bind_save_methods()

    def _bind_save_methods(self) -> None:
        """
        Dynamically replaces the .save() methods on the data objects
        with versions that are bound to this Vaspy instance. This enables
        calling .save() without a path argument, creating a clean API
        without a persistent circular dependency in the class definitions.
        """

        def _create_bound_save(
            vaspy_instance: Vaspy, original_method: Callable, filename: str
        ):
            """Creates a new save method that closes over the Vaspy instance."""

            def bound_save(path: Path | None = None) -> None:
                if path is None:
                    # Use the vaspy_instance to resolve the default path
                    path = vaspy_instance.get_path("input") / filename
                # Call the original, unbound save method with the resolved path
                original_method(path)

            return bound_save

        for obj, filename in [
            (self._incar, "INCAR"),
            (self._poscar, "POSCAR"),
            (self._potcar, "POTCAR"),
            (self._kpoints, "KPOINTS"),
        ]:
            # The original method is on the object's class
            original_save_method = getattr(obj.__class__, "save")
            # Create the new bound method
            bound_method = _create_bound_save(
                self, original_save_method.__get__(obj), filename
            )
            # Monkey-patch the instance's save method
            setattr(obj, "save", bound_method)

    # ---- context manager ---------------------------------------------------

    def __enter__(self) -> Vaspy:
        self.read_inputs()
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        if exc_type is None and self.auto_save:
            self.save_all()
        elif exc_type is not None:
            logger.error("Exception in Vaspy context: {}", exc)
        return False  # do not suppress exceptions

    # ---- public API --------------------------------------------------------

    def read_inputs(self) -> None:
        """Read main inputs (INCAR, POSCAR, POTCAR, KPOINTS) and log missing files."""
        main_files = ["POSCAR", "INCAR", "KPOINTS", "POTCAR"]
        input_dir = self.get_path("input")

        # Load main VASP inputs
        self._incar.load(input_dir / "INCAR")
        self._poscar.load(input_dir / "POSCAR")
        self._potcar.load(input_dir / "POTCAR")
        self._kpoints.load(input_dir / "KPOINTS")

        # Auto-generate POTCAR if missing and POSCAR is present
        if not self._potcar.content and self._poscar.content:
            logger.info("POTCAR not found. Attempting to generate from POSCAR species.")
            self.generate_potcar()  # Uses default potential
            self.potcar.save()  # Saves to the default input path

        self._check_missing_files(main_files, input_dir)

    def save_all(self) -> None:
        """Write all modified data (INCAR, POSCAR, POTCAR, KPOINTS) to the output path."""
        out_dir = self.get_path()
        # Call the objects' own save methods with an explicit path
        self._incar.save(out_dir / "INCAR")
        self._poscar.save(out_dir / "POSCAR")
        self._potcar.save(out_dir / "POTCAR")
        self._kpoints.save(out_dir / "KPOINTS")
        logger.info("Saved all files to {}.", out_dir)

    @property
    def incar(self) -> Incar:
        """Access the full INCAR object."""
        return self._incar

    @incar.setter
    def incar(self, value: Incar | Dict[str, dict]) -> None:
        if isinstance(value, Incar):
            self._incar = value
        else:
            self._incar = Incar(value)
        self._bind_save_methods()  # Re-bind after assignment

    @property
    def poscar(self) -> Poscar:
        """Access the full POSCAR object."""
        return self._poscar

    @poscar.setter
    def poscar(self, value: Poscar | str) -> None:
        if isinstance(value, Poscar):
            self._poscar = value
        elif isinstance(value, str):
            self._poscar = Poscar(initial=value)
        else:
            raise TypeError("poscar must be a Poscar object or a string.")
        self._bind_save_methods()  # Re-bind after assignment

    @property
    def potcar(self) -> Potcar:
        """Access the full POTCAR object."""
        return self._potcar

    @potcar.setter
    def potcar(self, value: Potcar | str) -> None:
        if isinstance(value, Potcar):
            self._potcar = value
        elif isinstance(value, str):
            self._potcar = Potcar(initial=value)
        else:
            raise TypeError("potcar must be a Potcar object or a string.")
        self._bind_save_methods()  # Re-bind after assignment

    @property
    def kpoints(self) -> Kpoints:
        """Access the full Kpoints object."""
        return self._kpoints

    @kpoints.setter
    def kpoints(self, value: Kpoints | str) -> None:
        if isinstance(value, Kpoints):
            self._kpoints = value
        elif isinstance(value, str):
            self._kpoints = Kpoints(initial=value)
        else:
            raise TypeError("kpoints must be a Kpoints object or a string.")
        self._bind_save_methods()  # Re-bind after assignment

    def get_path(self, opt: str = "root") -> Path:
        """Return input/output/root path depending on option."""
        opt_lower = opt.lower()

        if opt_lower == "root":
            return self.root_path

        target_path_str = None
        if opt_lower == "input":
            target_path_str = self.input_path
        elif opt_lower == "output":
            target_path_str = self.output_path
        else:
            raise ValueError(f"Unknown path option: {opt!r}")

        # If the specific path (input/output) is not defined, default to the root path.
        if target_path_str is None:
            return self.root_path

        # If the specific path is defined, resolve it.
        target_path = Path(target_path_str)

        # If the target path is absolute, use it directly.
        # Otherwise, join it with the root path.
        if target_path.is_absolute():
            return target_path
        else:
            return self.root_path / target_path

    # ---- file generation & template helpers --------------------------------

    def generate_potcar(self, potential_type: str = "potpaw_PBE") -> None:
        """Generate POTCAR from POSCAR species using a specific potential type."""
        species = self._poscar.species
        self._potcar.generate(species, potential_type)

    def apply_incar_template(self, name: str, overwrite: bool = True) -> None:
        """Merge an INCAR template into current config."""
        self._incar.apply_template(name, overwrite=overwrite)

    def list_available_incar_templates(self) -> List[str]:
        """Expose available INCAR template names."""
        return self._incar.list_templates()

    def view_3d(self) -> None:
        """Visualize the structure using ASE's viewer."""
        self._poscar.view_3d()

    # ---- internal helpers --------------------------------------------------

    def _check_missing_files(
        self,
        match_files: Iterable[Path | str],
        directory: Path,
    ) -> list[Path]:
        """Check for missing files and log them."""
        missing = [
            p
            for p in [directory / Path(name) for name in match_files]
            if not p.exists()
        ]
        if missing:
            details = ", ".join(f"{p.name}" for p in missing)
            logger.warning(
                "Missing main files in {}: {}",
                directory,
                details,
            )
        return missing


# ---- quick manual test -----------------------------------------------------


if __name__ == "__main__":
    calc_dir = Path("./test_calc")
    calc_dir.mkdir(exist_ok=True)

    # Create a dummy POSCAR to test auto-generation
    (calc_dir / "POSCAR").write_text(
        """Cubic Si
1.0
5.43 0.00 0.00
0.00 5.43 0.00
0.00 0.00 5.43
Si
2
direct
0.0 0.0 0.0
0.25 0.25 0.25
"""
    )
    # Clean up previous runs
    if (calc_dir / "output").exists():
        import shutil

        shutil.rmtree(calc_dir / "output")
    if (calc_dir / "INCAR").exists():
        (calc_dir / "INCAR").unlink()
    if (calc_dir / "POTCAR").exists():
        (calc_dir / "POTCAR").unlink()
    if (calc_dir / "KPOINTS").exists():
        (calc_dir / "KPOINTS").unlink()

    logger.info(
        "=== Context-manager usage (read from './test_calc', write to 'output') ==="
    )
    with Vaspy(calc_dir, output_path="output") as proj:
        proj.incar.apply_template("example", overwrite=True)
        proj.kpoints.automatic_length(length=60.0)
        proj.incar.content["ENCUT"] = {"value": 600, "comment": "context tweak"}
        # POTCAR was auto-generated from POSCAR.
        # All files will be saved to the 'output' directory on exit.

    logger.info("\n=== Non-context usage (read/write from './test_calc') ===")
    mgr = Vaspy(calc_dir)
    # read_inputs will read files and auto-generate POTCAR, saving it.
    mgr.read_inputs()

    # Overwrite the auto-generated POTCAR with a GGA one
    logger.info("Generating a new POTCAR with a different potential.")
    mgr.generate_potcar("potpaw_GGA")
    mgr.potcar.save()  # Saves to ./test_calc/POTCAR (no path needed!)

    # Generate and save a new KPOINTS file
    logger.info("Generating and saving a new KPOINTS file.")
    mgr.kpoints.automatic_mesh(mesh=(8, 8, 8))
    mgr.kpoints.save()  # Saves to ./test_calc/KPOINTS (no path needed!)

    logger.info("Modifying and saving INCAR.")
    mgr.incar.content["ISIF"] = {"value": 3}
    mgr.incar.save()  # Saves to ./test_calc/INCAR (no path needed!)

    print(
        f"\nFind generated files in '{calc_dir.resolve()}' and '{(calc_dir / 'output').resolve()}'"
    )
