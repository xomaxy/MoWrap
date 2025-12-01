from __future__ import annotations

import re
import shlex
import subprocess
import tempfile
from collections import OrderedDict
from importlib import resources
from pathlib import Path
from typing import Dict, Iterable, List, Literal, Optional

from loguru import logger


class SlurmScript:
    """
    High-level wrapper around a Slurm batch script (.slurm).

    Features
    --------
    - Create from scratch, from a file, or from a string.
    - Preserve unknown lines exactly.
    - Work with:
        * #SBATCH directives (job options).
        * module lines.
        * export VAR=VALUE environment variables.
        * body commands (e.g. srun, python, bash).
        * per-command options (e.g. --ntasks).
        * comments.
    - Submit via sbatch (job runs asynchronously).
    """

    SBATCH_PREFIX: str = "#SBATCH"

    def __init__(self, lines: Optional[List[str]] = None) -> None:
        """
        Initialize a script object.

        Parameters
        ----------
        lines:
            Optional list of lines (without trailing newlines). If None, a
            minimal script with a `#!/bin/bash` shebang is created.
        """
        if lines is None:
            self._lines: List[str] = ["#!/bin/bash"]
        else:
            self._lines = list(lines)

    # ------------------------------------------------------------------
    # I/O
    # ------------------------------------------------------------------
    @classmethod
    def from_file(cls, path: str | Path) -> "SlurmScript":
        """
        Load a script from a file.

        Parameters
        ----------
        path:
            Path to the script file.

        Returns
        -------
        SlurmJobScript
        """
        path = Path(path)
        logger.debug(f"Loading SlurmJobScript from {path}")
        text = path.read_text()
        return cls(text.splitlines())

    @classmethod
    def from_text(cls, text: str) -> "SlurmScript":
        """
        Create a script from a raw text string.

        Parameters
        ----------
        text:
            Full script content as a single string.

        Returns
        -------
        SlurmJobScript
        """
        logger.debug("Creating SlurmJobScript from raw text")
        return cls(text.splitlines())

    @classmethod
    def from_template(
        cls,
        template_name: str = "example.job",
        package: str = "mav.templates.sbatch",
    ) -> "SlurmScript":
        """
        Create a script from a packaged template file.
        """
        logger.debug(f"Loading SlurmScript template {package}/{template_name}")
        text = resources.read_text(package, template_name)
        return cls(text.splitlines())

    def load_template(
        self,
        template_name: str = "example.job",
        package: str = "mav.templates.sbatch",
    ) -> None:
        """
        Replace current script content with a packaged template.

        Preserve existing output/err/chdir directives (e.g. set by Vaspy).
        """
        prev_directives = self.list_directives()

        logger.debug(
            f"Loading template into existing SlurmScript: {package}/{template_name}"
        )
        text = resources.read_text(package, template_name)
        self._lines = text.splitlines()

        # Reaplica directivas que manda Vaspy
        for key in ("output", "err", "chdir"):
            if key in prev_directives:
                self.set_directive(key, prev_directives[key])

    @property
    def content(self) -> str:
        """Full script text as a single string."""
        return self.to_string()

    @content.setter
    def content(self, text: str) -> None:
        """Replace script content from a raw string."""
        self._lines = text.splitlines()

    def to_string(self) -> str:
        """
        Render the script into a single string.

        Returns
        -------
        str
            Script text with a trailing newline.
        """
        return "\n".join(self._lines) + "\n"

    def to_file(self, path: str | Path) -> None:
        """
        Save the script to a file.

        Parameters
        ----------
        path:
            Destination path.
        """
        path = Path(path)
        logger.info(f"Saving SlurmJobScript to {path}")
        path.write_text(self.to_string())

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _iter_lines(self) -> Iterable[tuple[int, str]]:
        """
        Iterate over (index, line) pairs.

        Returns
        -------
        Iterable[tuple[int, str]]
        """
        for idx, line in enumerate(self._lines):
            yield idx, line

    # ------------------------------------------------------------------
    # SBATCH directives
    # ------------------------------------------------------------------
    def list_directives(self) -> OrderedDict[str, Optional[str]]:
        """
        List all #SBATCH directives.

        Returns
        -------
        OrderedDict[str, Optional[str]]
            Mapping from directive name to value.
            Example: '#SBATCH --time=24:00:00' -> {'time': '24:00:00'}.
            Directives without explicit values map to None.
        """
        directives: "OrderedDict[str, Optional[str]]" = OrderedDict()
        pattern = re.compile(r"^#SBATCH\s+--([^=\s]+)(?:=(.*))?\s*$")

        for _, line in self._iter_lines():
            match = pattern.match(line.strip())
            if not match:
                continue
            name, value = match.group(1), match.group(2)
            directives[name] = value
        logger.debug(f"Extracted directives: {directives}")
        return directives

    def set_directive(self, name: str, value: Optional[str] = None) -> None:
        """
        Add or update a #SBATCH directive.

        If it exists, its line is replaced.
        Otherwise, it is inserted after the last existing #SBATCH line,
        or after the shebang if none exist.

        Parameters
        ----------
        name:
            Directive name without leading dashes (e.g. 'time', 'nodes').
        value:
            Directive value. If None, no '=value' is added.
        """
        logger.debug(f"Setting directive {name}={value}")
        pattern = re.compile(rf"^#SBATCH\s+--{re.escape(name)}(?:=.*)?\s*$")
        new_line = (
            f"{self.SBATCH_PREFIX} --{name}"
            if value is None
            else f"{self.SBATCH_PREFIX} --{name}={value}"
        )

        last_sbatch_idx = -1
        updated = False

        for idx, line in self._iter_lines():
            stripped = line.strip()
            if stripped.startswith(self.SBATCH_PREFIX):
                last_sbatch_idx = idx
            if pattern.match(stripped):
                self._lines[idx] = new_line
                updated = True
                break

        if not updated:
            if last_sbatch_idx >= 0:
                insert_idx = last_sbatch_idx + 1
            else:
                insert_idx = 1 if self._lines and self._lines[0].startswith("#!") else 0
            self._lines.insert(insert_idx, new_line)

    def remove_directive(self, name: str) -> None:
        """
        Remove all #SBATCH directives with the given name.

        Parameters
        ----------
        name:
            Directive name without leading dashes.
        """
        logger.debug(f"Removing directive {name}")
        pattern = re.compile(rf"^#SBATCH\s+--{re.escape(name)}(?:=.*)?\s*$")
        self._lines = [line for line in self._lines if not pattern.match(line.strip())]

    # ------------------------------------------------------------------
    # module lines
    # ------------------------------------------------------------------
    def list_modules(self) -> List[str]:
        """
        List all module lines.

        Returns
        -------
        List[str]
            Lines that start with 'module ' (stripped).
        """
        result: List[str] = []
        for _, line in self._iter_lines():
            stripped = line.strip()
            if stripped.startswith("module "):
                result.append(stripped)
        logger.debug(f"Found module lines: {result}")
        return result

    def add_module(
        self,
        action: str,
        name: str,
        position: Literal[
            "after_last_module", "before_first_non_shebang", "end"
        ] = "after_last_module",
    ) -> None:
        """
        Insert a line of the form 'module <action> <name>'.

        Parameters
        ----------
        action:
            Sub-command for module (e.g. 'load', 'switch').
        name:
            Module name (or argument string).
        position:
            Where to insert:
              - 'after_last_module'
              - 'before_first_non_shebang'
              - 'end'
        """
        new_line = f"module {action} {name}"
        logger.debug(f"Adding module line: {new_line} (position={position})")

        if position == "end":
            self._lines.append(new_line)
            return

        last_module_idx = -1
        for idx, line in self._iter_lines():
            if line.strip().startswith("module "):
                last_module_idx = idx

        if position == "after_last_module" and last_module_idx >= 0:
            self._lines.insert(last_module_idx + 1, new_line)
            return

        if position == "before_first_non_shebang":
            insert_idx = 0
            if self._lines and self._lines[0].startswith("#!"):
                insert_idx = 1
            self._lines.insert(insert_idx, new_line)
            return

        self._lines.append(new_line)

    def remove_module(self, name_substring: str) -> None:
        """
        Remove all module lines whose text contains the given substring.

        Parameters
        ----------
        name_substring:
            Substring to search for within module lines.
        """
        logger.debug(f"Removing module lines containing: {name_substring}")
        self._lines = [
            line
            for line in self._lines
            if not (line.strip().startswith("module ") and name_substring in line)
        ]

    # ------------------------------------------------------------------
    # Environment variables
    # ------------------------------------------------------------------
    def get_env_vars(self) -> Dict[str, str]:
        """
        Get environment variables from 'export VAR=VALUE' lines.

        Returns
        -------
        Dict[str, str]
            Mapping from variable name to value.
        """
        env: Dict[str, str] = {}
        pattern = re.compile(r"^export\s+([A-Za-z_][A-Za-z0-9_]*)=(.*)$")

        for _, line in self._iter_lines():
            match = pattern.match(line.strip())
            if not match:
                continue
            key, value = match.group(1), match.group(2)
            env[key] = value
        logger.debug(f"Extracted environment: {env}")
        return env

    def set_env_var(self, key: str, value: str) -> None:
        """
        Add or update an 'export KEY=VALUE' line.

        Parameters
        ----------
        key:
            Environment variable name.
        value:
            Value (as shell text).
        """
        logger.debug(f"Setting env var {key}={value}")
        pattern = re.compile(rf"^export\s+{re.escape(key)}(?:=.*)?\s*$")
        new_line = f"export {key}={value}"

        last_export_idx = -1
        updated = False

        for idx, line in self._iter_lines():
            stripped = line.strip()
            if stripped.startswith("export "):
                last_export_idx = idx
            if pattern.match(stripped):
                self._lines[idx] = new_line
                updated = True
                break

        if not updated:
            insert_idx = (
                last_export_idx + 1 if last_export_idx >= 0 else len(self._lines)
            )
            self._lines.insert(insert_idx, new_line)

    def unset_env_var(self, key: str) -> None:
        """
        Remove all lines exporting the given environment variable.

        Parameters
        ----------
        key:
            Environment variable name.
        """
        logger.debug(f"Unsetting env var {key}")
        pattern = re.compile(rf"^export\s+{re.escape(key)}(?:=.*)?\s*$")
        self._lines = [line for line in self._lines if not pattern.match(line.strip())]

    # ------------------------------------------------------------------
    # Body commands
    # ------------------------------------------------------------------
    def add_body_command(
        self, command: str, where: Literal["end", "top"] = "end"
    ) -> None:
        """
        Add a body command (e.g. srun, python, bash).

        Parameters
        ----------
        command:
            Command line to add.
        where:
            - 'end': append at end of script.
            - 'top': insert at the very top.
        """
        logger.debug(f"Adding body command: {command} (where={where})")
        if where == "end":
            self._lines.append(command)
        elif where == "top":
            self._lines.insert(0, command)
        else:
            raise ValueError("where must be 'end' or 'top'")

    def list_commands(self, prefix: str) -> List[str]:
        """
        List body commands starting with a specific prefix.

        Parameters
        ----------
        prefix:
            Command prefix (e.g. 'srun', 'python').

        Returns
        -------
        List[str]
        """
        out: List[str] = []
        for _, line in self._iter_lines():
            stripped = line.strip()
            if stripped.startswith(prefix + " "):
                out.append(stripped)
        logger.debug(f"Commands with prefix '{prefix}': {out}")
        return out

    # ------------------------------------------------------------------
    # Command options
    # ------------------------------------------------------------------
    @staticmethod
    def _set_option_tokens(tokens: List[str], flag: str, value: str) -> List[str]:
        """
        Internal helper to update or insert an option in a tokenized command.

        Supports:
        - cmd --flag value prog
        - cmd --flag=value prog

        If option does not exist, inserts '--flag=value' before first non-option.
        """
        idx: Optional[int] = None
        for i, tok in enumerate(tokens):
            if tok == flag or tok.startswith(flag + "="):
                idx = i
                break

        if idx is not None:
            if (
                tokens[idx] == flag
                and idx + 1 < len(tokens)
                and not tokens[idx + 1].startswith("-")
            ):
                tokens[idx + 1] = value
            else:
                tokens[idx] = f"{flag}={value}"
            return tokens

        insert_pos = len(tokens)
        for i, tok in enumerate(tokens[1:], start=1):
            if not tok.startswith("-"):
                insert_pos = i
                break

        tokens[insert_pos:insert_pos] = [f"{flag}={value}"]
        return tokens

    def set_option_on_command(
        self,
        command: str,
        flag: str,
        value: str | int | float,
        which: Literal["first", "all"] = "first",
    ) -> None:
        """
        Update or add an option on command lines starting with 'command'.

        Parameters
        ----------
        command:
            Command prefix (e.g. 'srun').
        flag:
            Option name (e.g. '--ntasks').
        value:
            Desired value.
        which:
            - 'first': modify only first matching line.
            - 'all'  : modify all matching lines.
        """
        value_str = str(value)
        logger.debug(
            f"Setting option {flag}={value_str} on command '{command}' (which={which})"
        )

        for i, line in self._iter_lines():
            stripped = line.strip()
            if not stripped.startswith(command + " "):
                continue

            tokens = shlex.split(stripped)
            tokens = self._set_option_tokens(tokens, flag, value_str)
            self._lines[i] = " ".join(tokens)

            if which == "first":
                break

    def set_option_on_command_at(
        self,
        command: str,
        occurrence: int,
        flag: str,
        value: str | int | float,
    ) -> None:
        """
        Update or add an option on a specific occurrence of a command.

        Parameters
        ----------
        command:
            Command prefix.
        occurrence:
            0-based index of the matching line.
        flag:
            Option name.
        value:
            Desired value.
        """
        value_str = str(value)
        logger.debug(
            f"Setting option {flag}={value_str} on command '{command}', occurrence={occurrence}"
        )
        seen = 0

        for i, line in self._iter_lines():
            stripped = line.strip()
            if not stripped.startswith(command + " "):
                continue

            if seen == occurrence:
                tokens = shlex.split(stripped)
                tokens = self._set_option_tokens(tokens, flag, value_str)
                self._lines[i] = " ".join(tokens)
                return

            seen += 1

    def normalize_command_options(
        self,
        command: str,
        preferred_order: List[str],
        occurrence: Optional[int] = None,
    ) -> None:
        """
        Normalize long option order for a given command.

        Parameters
        ----------
        command:
            Command prefix (e.g. 'srun').
        preferred_order:
            List of option names (e.g. ['--ntasks', '--map-by', '--hint']).
        occurrence:
            - None: normalize all matching lines.
            - int : normalize only that occurrence (0-based).
        """
        logger.debug(
            f"Normalizing options for command '{command}', "
            f"preferred_order={preferred_order}, occurrence={occurrence}"
        )
        seen = 0

        for i, line in self._iter_lines():
            stripped = line.strip()
            if not stripped.startswith(command + " "):
                continue

            if occurrence is not None and seen != occurrence:
                seen += 1
                continue

            tokens = shlex.split(stripped)
            if not tokens:
                seen += 1
                continue

            cmd = tokens[0]
            opts: List[str] = []
            rest_start = len(tokens)

            for j, tok in enumerate(tokens[1:], start=1):
                if tok.startswith("-"):
                    opts.append(tok)
                else:
                    rest_start = j
                    break

            rest = tokens[rest_start:]

            flag_map: Dict[str, str] = {}
            for opt in opts:
                if opt.startswith("--") and "=" in opt:
                    name = opt.split("=", 1)[0]
                    flag_map[name] = opt

            used = set()
            new_opts: List[str] = []

            for name in preferred_order:
                if name in flag_map:
                    new_opts.append(flag_map[name])
                    used.add(name)

            for opt in opts:
                if opt.startswith("--") and "=" in opt:
                    name = opt.split("=", 1)[0]
                    if name in used:
                        continue
                new_opts.append(opt)

            self._lines[i] = " ".join([cmd] + new_opts + rest)
            seen += 1

            if occurrence is not None and seen > occurrence:
                break

    # ------------------------------------------------------------------
    # Comments
    # ------------------------------------------------------------------
    def add_comment(self, text: str, where: Literal["end", "top"] = "end") -> None:
        """
        Add a full-line comment.

        Parameters
        ----------
        text:
            Comment text (without '#').
        where:
            - 'end': append at end.
            - 'top': insert after shebang if present, else at top.
        """
        line = f"# {text}"
        logger.debug(f"Adding comment: {line} (where={where})")
        if where == "end":
            self._lines.append(line)
        elif where == "top":
            if self._lines and self._lines[0].startswith("#!"):
                self._lines.insert(1, line)
            else:
                self._lines.insert(0, line)
        else:
            raise ValueError("where must be 'end' or 'top'")

    def add_comment_above_command(
        self,
        command: str,
        text: str,
        which: Literal["first", "all"] = "first",
    ) -> None:
        """
        Insert a comment line immediately above matching commands.

        Parameters
        ----------
        command:
            Command prefix (e.g. 'srun').
        text:
            Comment text.
        which:
            - 'first': above first match only.
            - 'all'  : above all matches.
        """
        comment_line = f"# {text}"
        logger.debug(
            f"Adding comment above command '{command}': {comment_line} (which={which})"
        )
        new_lines: List[str] = []

        for idx, line in self._iter_lines():
            stripped = line.strip()
            if stripped.startswith(command + " "):
                new_lines.append(comment_line)
                new_lines.append(line)
                if which == "first":
                    new_lines.extend(self._lines[idx + 1 :])
                    self._lines = new_lines
                    return
            else:
                new_lines.append(line)

        self._lines = new_lines

    def add_comment_above_line_containing(
        self,
        substring: str,
        text: str,
        which: Literal["first", "all"] = "first",
    ) -> None:
        """
        Insert a comment above lines containing a given substring.

        Parameters
        ----------
        substring:
            Substring to search for.
        text:
            Comment text.
        which:
            - 'first': above first match only.
            - 'all'  : above all matches.
        """
        comment_line = f"# {text}"
        logger.debug(
            f"Adding comment above lines containing '{substring}': {comment_line} (which={which})"
        )
        new_lines: List[str] = []

        for idx, line in self._iter_lines():
            if substring in line:
                new_lines.append(comment_line)
                new_lines.append(line)
                if which == "first":
                    new_lines.extend(self._lines[idx + 1 :])
                    self._lines = new_lines
                    return
            else:
                new_lines.append(line)

        self._lines = new_lines

    # ------------------------------------------------------------------
    # Submission
    # ------------------------------------------------------------------
    def submit_via_srun(self) -> None:
        """
        Placeholder for potential 'srun' submission mode.

        Currently not supported: logs a warning only.
        """
        logger.warning("srun is temporaly not suported")

    def submit(
        self,
        sbatch_path: str = "sbatch",
        extra_args: Optional[List[str]] = None,
        keep_script: bool = False,
    ) -> int:
        """
        Submit the script using sbatch via subprocess.

        This waits only for sbatch to finish; the job itself runs asynchronously.

        Parameters
        ----------
        sbatch_path:
            Path or name of the sbatch executable.
        extra_args:
            Extra arguments for sbatch (e.g. ['--dependency=afterok:12345']).
        keep_script:
            If True, keep the temporary script file; otherwise remove it.

        Returns
        -------
        int
            Job ID parsed from sbatch output.

        Raises
        ------
        RuntimeError
            If sbatch fails or the job ID cannot be parsed.
        """
        extra_args = extra_args or []
        script_text = self.to_string()

        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".slurm",
            delete=False,
        ) as tmp:
            tmp.write(script_text)
            tmp_path = Path(tmp.name)

        logger.info(f"Submitting job via sbatch using script: {tmp_path}")
        cmd = [sbatch_path] + extra_args + [str(tmp_path)]
        logger.debug(f"Running command: {' '.join(shlex.quote(c) for c in cmd)}")

        try:
            proc = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
        except Exception as exc:
            logger.error(f"Failed to execute sbatch: {exc}")
            raise RuntimeError(f"Failed to execute sbatch: {exc}") from exc
        finally:
            if not keep_script:
                try:
                    tmp_path.unlink(missing_ok=True)
                    logger.debug(f"Removed temporary script {tmp_path}")
                except Exception as exc:
                    logger.warning(
                        f"Failed to remove temporary script {tmp_path}: {exc}"
                    )

        stdout = proc.stdout.strip()
        stderr = proc.stderr.strip()
        logger.debug(f"sbatch stdout: {stdout}")
        if stderr:
            logger.debug(f"sbatch stderr: {stderr}")

        if proc.returncode != 0:
            logger.error(f"sbatch failed with return code {proc.returncode}")
            raise RuntimeError(
                f"sbatch failed with code {proc.returncode}: {stderr or stdout}"
            )

        match = re.search(r"Submitted batch job (\d+)", stdout)
        if not match:
            logger.error("Could not parse job ID from sbatch output")
            raise RuntimeError(f"Could not parse job ID from sbatch output: {stdout}")

        job_id = int(match.group(1))
        logger.info(f"Submitted job with ID {job_id}")
        return job_id

    # Alias for people who expect a 'sbatch' method
    def sbatch(
        self,
        sbatch_path: str = "sbatch",
        extra_args: Optional[List[str]] = None,
        keep_script: bool = False,
    ) -> int:
        """
        Alias for submit(), to match Slurm terminology.

        Parameters
        ----------
        sbatch_path, extra_args, keep_script:
            Forwarded to submit().

        Returns
        -------
        int
            Job ID.
        """
        return self.submit(
            sbatch_path=sbatch_path,
            extra_args=extra_args,
            keep_script=keep_script,
        )
