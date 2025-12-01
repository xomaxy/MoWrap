from __future__ import annotations

from typing import Dict, Mapping

from loguru import logger

# a little peak


def parse_config_text(text: str) -> Dict[str, Dict[str, str]]:
    """
    Parse an INCAR-style config text into a nested dict.

    Handles:
    - key = value
    - multiple statements separated by `;`
    - inline comments with # or ! (only parsed if outside quotes)
    - multiline quoted values
    - backslash continued lines
    """
    logger.debug("parse_config_text: starting parse, text length={}", len(text))

    result: Dict[str, Dict[str, str]] = {}

    def _split_comment(line: str) -> tuple[str, str]:
        in_quotes = False
        for idx, ch in enumerate(line):
            if ch == '"':
                in_quotes = not in_quotes
            elif ch in ("#", "!") and not in_quotes:
                return line[:idx], line[idx + 1 :].strip()
        return line, ""

    def _split_statements(code: str) -> list[str]:
        statements = []
        in_quotes = False
        start = 0
        for idx, ch in enumerate(code):
            if ch == '"':
                in_quotes = not in_quotes
            elif ch == ";" and not in_quotes:
                statements.append(code[start:idx])
                start = idx + 1
        statements.append(code[start:])
        return statements

    # ---- Merge continuation lines "\" ---------------------------------------

    raw_lines = text.splitlines()
    logical_lines: list[str] = []
    continuation: str | None = None

    for raw_line in raw_lines:
        stripped = raw_line.rstrip()
        if continuation is not None:
            if stripped.endswith("\\"):
                continuation += " " + stripped[:-1].strip()
                continue
            else:
                logical_lines.append(continuation + " " + raw_line.strip())
                continuation = None
                continue

        if stripped.endswith("\\"):
            continuation = stripped[:-1]
        else:
            logical_lines.append(raw_line)

    if continuation is not None:
        logical_lines.append(continuation)

    # ---- Parse ---------------------------------------------------------------

    in_multiline = False
    current_name: str | None = None
    current_value: list[str] = []
    current_comment: str = ""

    def _commit_multiline():
        nonlocal current_name, current_value, current_comment
        if current_name:
            result[current_name] = {
                "value": "\n".join(current_value),
                "comment": current_comment,
            }
        current_name = None
        current_value = []
        current_comment = ""

    for line in logical_lines:
        stripped = line.strip()

        if in_multiline:
            if '"' in stripped:
                before, _, after = stripped.partition('"')
                current_value.append(before)
                _, extra_comment = _split_comment(after)
                if extra_comment:
                    current_comment = extra_comment
                _commit_multiline()
                in_multiline = False
            else:
                current_value.append(stripped)
            continue

        if not stripped or stripped.startswith(("#", "!")):
            continue

        if "=" not in stripped:
            continue

        code, comment = _split_comment(stripped)
        statements = _split_statements(code)

        for idx, stmt in enumerate(statements):
            stmt = stmt.strip()
            if not stmt or "=" not in stmt:
                continue

            name, value = stmt.split("=", 1)
            name = name.strip()
            value = value.strip()

            stmt_comment = comment if idx == len(statements) - 1 else ""

            if value.startswith('"'):
                rest = value[1:]
                if '"' in rest:
                    val, _, after = rest.partition('"')
                    _, extra_comment = _split_comment(after)
                    final_comment = stmt_comment or extra_comment
                    result[name] = {"value": val, "comment": final_comment}
                else:
                    in_multiline = True
                    current_name = name
                    current_comment = stmt_comment
                    if rest:
                        current_value = [rest]
            else:
                result[name] = {"value": value, "comment": stmt_comment}

    if in_multiline:
        _commit_multiline()

    logger.debug("parse_config_text: finished, parsed {} entries", len(result))
    return result


def config_dict_to_text(config: Mapping[str, Mapping[str, str]]) -> str:
    """
    Convert parsed dictionary back into INCAR text.

    - Single-line values: key = value
    - Multiline values: quoted block style
    """
    logger.debug("config_dict_to_text: starting, entries={}", len(config))

    lines: list[str] = []

    for name, meta in config.items():
        raw_val = meta.get("value", "")
        raw_comment = meta.get("comment", "")
        value = "" if raw_val is None else str(raw_val)
        comment = "" if raw_comment is None else str(raw_comment)

        if "\n" in value:
            lines.append(f'{name} = "')
            lines.extend(value.splitlines())
            closing = '"'
            if comment.strip():
                closing += f"  # {comment.strip()}"
            lines.append(closing)
        else:
            line = f"{name} = {value}"
            if comment.strip():
                line += f"  # {comment.strip()}"
            lines.append(line)

    text = "\n".join(lines)
    logger.debug("config_dict_to_text: finished, output length={}", len(text))
    return text


if __name__ == "__main__":
    from .make_it_cli import dispatch_module

    dispatch_module(
        globals(),
        flag_aliases={"-f": "file", "-d": "debug"},
    )
