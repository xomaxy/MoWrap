# vaspy.py
from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable, List

from .core.base import logger
from .core.incar import Incar
from .core.kpoints import Kpoints
from .core.poscar import Poscar
from .core.potcar import Potcar
from .core.slurm_helper import SlurmScript


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

        input_dir = self.get_path("input")

        self._incar = Incar(base_dir=input_dir)
        self._poscar = Poscar(base_dir=input_dir)
        self._potcar = Potcar(base_dir=input_dir)
        self._kpoints = Kpoints(base_dir=input_dir)

        self._slurm: SlurmScript | None = None

    def __enter__(self) -> "Vaspy":
        self.read_inputs()
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        if exc_type is None and self.auto_save:
            self.save_all()
        elif exc_type is not None:
            logger.error("Exception in Vaspy context: {}", exc)
        return False

    def read_inputs(self) -> None:
        """Read main inputs (INCAR, POSCAR, POTCAR, KPOINTS)."""
        main_files = ["POSCAR", "INCAR", "KPOINTS", "POTCAR"]
        input_dir = self.get_path("input")

        self._incar.base_dir = input_dir
        self._poscar.base_dir = input_dir
        self._potcar.base_dir = input_dir
        self._kpoints.base_dir = input_dir

        self._incar.load()
        self._poscar.load()
        self._potcar.load()
        self._kpoints.load()

        if not self._potcar.content and self._poscar.content:
            logger.info(
                "POTCAR not found. Attempting to generate from POSCAR species.",
            )
            self.generate_potcar()
            self.potcar.save()

        self._check_missing_files(main_files, input_dir)

    def save_all(self) -> None:
        """Write all modified data to the output path."""
        out_dir = self.get_path()
        self._incar.save(out_dir / "INCAR")
        self._poscar.save(out_dir / "POSCAR")
        self._potcar.save(out_dir / "POTCAR")
        self._kpoints.save(out_dir / "KPOINTS")
        logger.info("Saved all files to {}.", out_dir)

    # ------------------------------------------------------------------
    # Slurm integration
    # ------------------------------------------------------------------
    @property
    def slurm(self) -> SlurmScript:
        """
        SlurmScript associated with this calculation.

        - If job.slurm exists in the input directory, it is loaded.
        - Otherwise, the packaged template 'example.job' is used.
        - #SBATCH --output and --err are forced to:
          output_path (if set) -> root_path -> input_path.
        """
        if self._slurm is None:
            input_dir = self.get_path("input")
            script_path = input_dir / "job.slurm"

            if script_path.exists():
                logger.debug(f"Loading existing Slurm script from {script_path}")
                self._slurm = SlurmScript.from_file(script_path)
            else:
                try:
                    self._slurm = SlurmScript.from_template(
                        template_name="example.job",
                        package="mav.templates.sbatch",
                    )
                    logger.debug("Loaded SlurmScript from template 'example.job'.")
                except FileNotFoundError:
                    logger.warning(
                        "Slurm template 'example.job' not found; using minimal script.",
                    )
                    self._slurm = SlurmScript()

            self._configure_slurm_output_paths()

        return self._slurm

    def _configure_slurm_output_paths(self) -> None:
        """
        Ensure #SBATCH --output, --err and --chdir are set consistently.

        output/err:
            1. output_path (si no es None)
            2. root_path
            3. input_path

        chdir:
            siempre root_path.
        """
        if self._slurm is None:
            return

        run_dir = self.get_path("root")
        out_dir = self._get_slurm_output_dir()
        out_dir.mkdir(parents=True, exist_ok=True)

        # Si el dir de salida coincide con el de ejecución, usa nombres simples
        if out_dir == run_dir:
            output_value = "std.out"
            err_value = "std.err"
        else:
            output_value = str(out_dir / "std.out")
            err_value = str(out_dir / "std.err")

        self._slurm.set_directive("output", output_value)
        self._slurm.set_directive("err", err_value)
        self._slurm.set_directive("chdir", str(run_dir))

    def _get_slurm_output_dir(self) -> Path:
        """Directory where Slurm batch std.out/std.err will be written."""
        if self.output_path is not None:
            return self.get_path("output")

        root_dir = self.get_path("root")
        if root_dir is not None:
            return root_dir

        return self.get_path("input")

    # ------------------------------------------------------------------
    # INCAR / POSCAR / POTCAR / KPOINTS
    # ------------------------------------------------------------------
    @property
    def incar(self) -> Incar:
        return self._incar

    @incar.setter
    def incar(self, value: Incar | Dict[str, dict]) -> None:
        if isinstance(value, Incar):
            self._incar = value
        else:
            self._incar = Incar(value, base_dir=self.get_path("input"))
        self._incar.base_dir = self.get_path("input")

    @property
    def poscar(self) -> Poscar:
        return self._poscar

    @poscar.setter
    def poscar(self, value: Poscar | str) -> None:
        if isinstance(value, Poscar):
            self._poscar = value
        elif isinstance(value, str):
            self._poscar = Poscar(initial=value, base_dir=self.get_path("input"))
        else:
            raise TypeError("poscar must be a Poscar object or a string.")
        self._poscar.base_dir = self.get_path("input")

    @property
    def potcar(self) -> Potcar:
        return self._potcar

    @potcar.setter
    def potcar(self, value: Potcar | str) -> None:
        if isinstance(value, Potcar):
            self._potcar = value
        elif isinstance(value, str):
            self._potcar = Potcar(initial=value, base_dir=self.get_path("input"))
        else:
            raise TypeError("potcar must be a Potcar object or a string.")
        self._potcar.base_dir = self.get_path("input")

    @property
    def kpoints(self) -> Kpoints:
        return self._kpoints

    @kpoints.setter
    def kpoints(self, value: Kpoints | str) -> None:
        if isinstance(value, Kpoints):
            self._kpoints = value
        elif isinstance(value, str):
            self._kpoints = Kpoints(initial=value, base_dir=self.get_path("input"))
        else:
            raise TypeError("kpoints must be a Kpoints object or a string.")
        self._kpoints.base_dir = self.get_path("input")

    def get_path(self, opt: str = "root") -> Path:
        """Return input/output/root path depending on option."""
        opt_lower = opt.lower()

        if opt_lower == "root":
            return self.root_path

        if opt_lower == "input":
            target_path_str = self.input_path
        elif opt_lower == "output":
            target_path_str = self.output_path
        else:
            raise ValueError(f"Unknown path option: {opt!r}")

        if target_path_str is None:
            return self.root_path

        target_path = Path(target_path_str)
        if target_path.is_absolute():
            return target_path
        return self.root_path / target_path

    def generate_potcar(self, potential_type: str = "potpaw_PBE") -> None:
        """Generate POTCAR from POSCAR species."""
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

    def _check_missing_files(
        self,
        match_files: Iterable[str],
        directory: Path,
    ) -> list[Path]:
        """Check for missing files and log them."""
        missing = [
            p
            for p in [directory / Path(name) for name in match_files]
            if not p.exists()
        ]
        if missing:
            details = ", ".join(p.name for p in missing)
            logger.warning(
                "Missing main files in {}: {}",
                directory,
                details,
            )
        return missing
