# MoWrap
Lightweight python wrapper to use chemistry simulation tools.

## Installation

It is recommended to use a virtual environment (e.g. `conda`, `venv`, `mamba`).

### 1. Clone the repository

```bash
git clone https://github.com/your-username/your-repo.git
cd your-repo
```

# mav

Minimal VASP IO helper focused on `INCAR`, `POSCAR`, `KPOINTS`, `POTCAR` and Slurm job scripts.

## Installation

It is recommended to use a virtual environment (`conda`, `venv`, etc.).

### 1. Clone the repository

```bash
git clone https://github.com/your-username/mav.git
cd mav
````

### 2. (Optional) Create and activate a conda environment

```bash
conda create -n mav python=3.11
conda activate mav
```

### 3. Install in editable mode

Core:

```bash
pip install -e .
```

With optional visualization (requires ASE):

```bash
pip install -e .[visualization]
```

---

## Usage

### Basic example (current directory)

Assumes `INCAR`, `POSCAR`, `POTCAR` and `KPOINTS` are in the current folder.

```python
from pathlib import Path
from mav.vaspy import Vaspy

vas = Vaspy(root_path=Path("."))

# Read all main inputs
vas.read_inputs()

# Inspect / modify INCAR
print(vas.incar["ENCUT"])
vas.incar["ENCUT"] = 520

# Save everything back to disk
vas.save_all()
```

### Using as a context manager (auto read + auto save)

```python
from mav.vaspy import Vaspy

with Vaspy(root_path=".", auto_save=True) as vas:
    # Files are read automatically when entering the context
    vas.incar["ENCUT"] = 600
    vas.kpoints.set_monkhorst_pack([6, 6, 6])
    # On clean exit, INCAR/KPOINTS/POSCAR/POTCAR are saved
```

### Custom input / output layout

Example layout:

* Input files in `calc/input`
* Output written to `calc/output`

```python
from mav.vaspy import Vaspy

vas = Vaspy(
    root_path="calc",
    input_path="input",
    output_path="output",
    auto_save=False,
)

vas.read_inputs()

# Work with POSCAR
print(vas.poscar.species)
vas.poscar.translate([0.1, 0.0, 0.0])

# Write all files to calc/output
vas.save_all()
```

### Generating POTCAR from POSCAR

```python
from mav.vaspy import Vaspy

vas = Vaspy(root_path=".")
vas.read_inputs()

# Regenerate POTCAR using POSCAR species and a given potential set
vas.generate_potcar(potential_type="potpaw_PBE")
vas.save_all()
```

### Using INCAR templates

Assumes you have INCAR templates set up in your package.

```python
from mav.vaspy import Vaspy

vas = Vaspy(root_path=".")
vas.read_inputs()

print("Available templates:", vas.list_available_incar_templates())

# Apply a template on top of current INCAR
vas.apply_incar_template("relax", overwrite=True)

vas.save_all()
```

---

## Slurm integration

`Vaspy.slurm` manages a `SlurmScript` associated with the calculation:

* If `job.slurm` exists in the input directory, it is loaded.
* Otherwise, a packaged template `example.job` is used (if available), or a minimal script is created.
* `#SBATCH --output`, `#SBATCH --error` and `#SBATCH --chdir` are configured consistently from `root_path` / `output_path`.

### Without context manager: prepare and submit job

```python
from pathlib import Path
import subprocess
from mav.vaspy import Vaspy

vas = Vaspy(
    root_path=Path("calc"),
    input_path="input",
    output_path="runs",
    auto_save=False,
)

# Read main VASP inputs
vas.read_inputs()

# Access (or create) the Slurm script
slurm = vas.slurm

# Modify some directives
slurm.set_directive("job-name", "my-vasp-job")
slurm.set_directive("time", "24:00:00")
slurm.set_directive("nodes", "2")
slurm.set_directive("ntasks-per-node", "64")

# Save job.slurm in the input directory
slurm_path = vas.get_path("input") / "job.slurm"
slurm.save(slurm_path)

# Save VASP input files to the configured output directory
vas.save_all()

# Submit the job
subprocess.run(["sbatch", str(slurm_path)], check=True)
```

### With context manager: prepare and submit job

```python
from pathlib import Path
import subprocess
from mav.vaspy import Vaspy

slurm_path = None

with Vaspy(
    root_path=Path("calc"),
    input_path="input",
    output_path="runs",
    auto_save=True,  # will save INCAR/POSCAR/POTCAR/KPOINTS on exit
) as vas:
    # Inputs are read automatically on entering the context
    slurm = vas.slurm

    slurm.set_directive("job-name", "my-vasp-job")
    slurm.set_directive("time", "12:00:00")
    slurm.set_directive("nodes", "1")
    slurm.set_directive("ntasks-per-node", "32")

    # Save Slurm script inside the context
    slurm_path = vas.get_path("input") / "job.slurm"
    slurm.save(slurm_path)

    # Any modifications to INCAR/POSCAR/etc. go here
    # e.g.:
    # vas.incar["ENCUT"] = 520

# On context exit, VASP input files are saved (auto_save=True)
# Now submit the job
subprocess.run(["sbatch", str(slurm_path)], check=True)
```

---

## 3D visualization (optional, requires ASE)

Install with the extra:

```bash
pip install -e .[visualization]
```

Then:

```python
from mav.vaspy import Vaspy

vas = Vaspy(root_path=".")
vas.read_inputs()

# Open an interactive ASE viewer
vas.view_3d()
```
