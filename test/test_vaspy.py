from pathlib import Path

from mav import Vaspy
from mav import text_helpers as th


def test_vaspy_creates_incar_in_root_path_by_default(tmp_path: Path) -> None:
    """
    Test Vaspy creates a new INCAR in the root directory when input/output
    paths are not specified.
    """
    # 1. Setup: just a root directory
    root_dir = tmp_path / "test_dir" / "root"
    root_dir.mkdir(parents=True)

    dummy_params = {"PREC": {"value": "Accurate", "comment": "precision level"}}

    # 2. Instantiate Vaspy, defaulting to root_dir for input/output
    # When the 'with' block is exited, save() should be called automatically.
    with Vaspy(root_path=root_dir) as mgr:
        # Since no INCAR exists at the start, the incar object should be empty.
        assert len(mgr.incar) == 0
        # Add a new parameter
        mgr.incar.update(dummy_params)
        mgr.incar.save()

    # 3. Verify the output
    output_incar_path = root_dir / "INCAR"
    assert output_incar_path.exists(), (
        "INCAR file was not created in the root directory."
    )

    # Check the content of the created INCAR file
    expected_text = th.config_dict_to_text(dummy_params)
    actual_text = output_incar_path.read_text()
    assert actual_text == expected_text, (
        "The content of the created INCAR is incorrect."
    )


def test_input_path_with_default_output(tmp_path: Path) -> None:
    """
    Test Vaspy reads from a relative input path and writes to the root
    path when no output path is given.
    """
    # 1. Setup directory structure
    root_dir = tmp_path / "test_dir"
    input_dir = root_dir / "input"
    input_dir.mkdir(parents=True)

    dummy_params = {"IBRION": {"value": 2, "comment": "ionic relaxation"}}

    # 2. Instantiate Vaspy with an input_path but no output_path
    with Vaspy(root_path=root_dir, input_path="input") as mgr:
        # No INCAR in 'input', so it should be empty
        assert len(mgr.incar) == 0
        mgr.incar.update(dummy_params)

    # 3. Verify the output
    # The INCAR should be written to the root_dir by default
    output_incar_path = root_dir / "INCAR"
    assert output_incar_path.exists(), (
        "INCAR file was not created in the root directory."
    )

    # Verify content
    expected_text = th.config_dict_to_text(dummy_params)
    actual_text = output_incar_path.read_text()
    assert actual_text == expected_text, (
        "The content of the created INCAR is incorrect."
    )

    # Also, ensure no INCAR was written to the input directory
    assert not (input_dir / "INCAR").exists(), (
        "INCAR file was incorrectly written to the input directory."
    )


def test_vaspy_context_manager_creates_incar_and_poscar(tmp_path: Path) -> None:
    """
    Test that using Vaspy as a context manager correctly creates both
    INCAR and POSCAR files on exit.
    """
    # 1. Setup
    root_dir = tmp_path / "test_run"
    root_dir.mkdir()

    incar_params = {"ISMEAR": {"value": -5, "comment": "tetrahedron smearing"}}
    poscar_content = "Test POSCAR\n1.0\n10.0 0.0 0.0\n0.0 10.0 0.0\n0.0 0.0 10.0\nSi\n1\nDirect\n0.0 0.0 0.0 Si\n"

    # 2. Execute using context manager
    with Vaspy(root_path=root_dir) as mgr:
        mgr.incar.update(incar_params)
        mgr.poscar = poscar_content
        # At this point, files should not exist yet
        assert not (root_dir / "INCAR").exists()
        assert not (root_dir / "POSCAR").exists()

    # 3. Verify files were created after exiting the 'with' block
    incar_path = root_dir / "INCAR"
    poscar_path = root_dir / "POSCAR"

    assert incar_path.exists(), "INCAR file was not created by context manager."
    assert poscar_path.exists(), "POSCAR file was not created by context manager."

    # Verify INCAR content
    expected_incar_text = th.config_dict_to_text(incar_params)
    actual_incar_text = incar_path.read_text()
    assert actual_incar_text == expected_incar_text

    # Verify POSCAR content
    actual_poscar_text = poscar_path.read_text()
    assert actual_poscar_text == poscar_content
