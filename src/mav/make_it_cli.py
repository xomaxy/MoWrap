# make_it_cli.py

from __future__ import annotations

import json
import sys
from typing import Any, Mapping

from loguru import logger

# base logging: info to stdout
logger.remove()
logger.add(sys.stdout, level="INFO")


def enable_debug_logging() -> None:
    # switch to debug on stderr
    logger.remove()
    logger.add(sys.stderr, level="DEBUG")


def _as_bool(value: str | bool | None) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    v = str(value).strip().lower()
    return v in {"1", "true", "yes", "y", "on"}


def dispatch_module(
    module_globals: Mapping[str, Any],
    *,
    flag_aliases: dict[str, str] | None = None,
    default_func_name: str | None = None,
) -> None:
    flag_aliases = flag_aliases or {}

    if len(sys.argv) < 2:
        available = [
            name
            for name, obj in module_globals.items()
            if callable(obj) and not name.startswith("_")
        ]
        logger.error(
            "Usage: python {} <function> [args...]",
            sys.argv[0],
        )
        logger.error(
            "Available functions: {}",
            ", ".join(sorted(available)),
        )
        raise SystemExit(1)

    first = sys.argv[1]

    if first.startswith("-"):
        if default_func_name is None:
            logger.error("Unknown function: {}", first)
            raise SystemExit(1)
        func_name = default_func_name
        raw_args = sys.argv[1:]
    else:
        func_name = first.replace("-", "_")
        raw_args = sys.argv[2:]

    func = module_globals.get(func_name)
    if not callable(func):
        logger.error("Unknown function: {}", func_name)
        raise SystemExit(1)

    # global debug flag
    debug_cli = False
    cleaned: list[str] = []
    for token in raw_args:
        if token in ("--debug", "-d"):
            debug_cli = True
            continue
        cleaned.append(token)
    raw_args = cleaned

    args: list[str] = []
    kwargs: dict[str, Any] = {}

    it = iter(raw_args)
    for token in it:
        if token.startswith("--"):
            if "=" in token:
                key, val = token[2:].split("=", 1)
            else:
                key = token[2:]
                try:
                    val = next(it)
                except StopIteration:
                    logger.error("Missing value for --{}", key)
                    raise SystemExit(1)
            kwargs[key] = val
        elif token in flag_aliases:
            key = flag_aliases[token]
            try:
                val = next(it)
            except StopIteration:
                logger.error("Missing value for {}", token)
                raise SystemExit(1)
            kwargs[key] = val
        else:
            args.append(token)

    # if no positional args and stdin has data -> feed it as first arg
    if not args and not sys.stdin.isatty():
        stdin_data = sys.stdin.read()
        if stdin_data:
            stdin_data = stdin_data.strip()
            try:
                obj = json.loads(stdin_data)
                args.append(obj)
            except json.JSONDecodeError:
                # not JSON, pass raw text
                args.append(stdin_data)

    debug_kw = kwargs.pop("debug", None)
    debug_enabled = debug_cli or _as_bool(debug_kw)

    if debug_enabled:
        enable_debug_logging()
        logger.debug(
            "dispatch_module: debug enabled, func={}, args={!r}, kwargs={!r}",
            func_name,
            args,
            kwargs,
        )

    logger.debug(
        "dispatch_module: calling {}(*{!r}, **{!r})",
        func_name,
        args,
        kwargs,
    )
    result = func(*args, **kwargs)
    logger.debug(
        "dispatch_module: result type={}",
        type(result).__name__,
    )

    if result is not None:
        if isinstance(result, (dict, list)):
            logger.info("{}", json.dumps(result, indent=2))
        else:
            logger.info("{}", result)
