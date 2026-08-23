"""CLI entry point. Dispatch, exit codes, and nothing else of substance."""

from __future__ import annotations

import argparse
import sys

from slackchat.cli.render import render_result
from slackchat.core.detect import detect
from slackchat.core.types import EmptyInputError
from slackchat.service import build_service

EXIT_OK = 0
EXIT_EMPTY_INPUT = 1
EXIT_USAGE = 2
EXIT_PROVIDER_ERROR = 3

SUBCOMMANDS = frozenset({"detect", "log", "eval", "serve"})


def _stdin_is_tty() -> bool:
    return sys.stdin.isatty()


def _stdout_is_tty() -> bool:
    return sys.stdout.isatty()


def _read_stdin() -> str:
    return sys.stdin.read()


def _oneshot_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="slackchat",
        description="Fix English text, or translate Vietnamese to English.",
    )
    parser.add_argument("text", nargs="?", help="text to process; omit to read stdin or start a session")
    parser.add_argument(
        "--mode",
        choices=["correction", "translation"],
        default=None,
        help="force a mode instead of detecting it",
    )
    parser.add_argument(
        "--raw",
        action="store_true",
        help="print the processed text only, with no diff or metadata",
    )
    return parser


def _run_oneshot(text: str, *, mode: str | None, raw: bool) -> int:
    service = build_service()
    try:
        result = service.run(text, mode, client="cli")
    except EmptyInputError:
        print("slackchat: input is empty", file=sys.stderr)
        return EXIT_EMPTY_INPUT

    if raw:
        print(result.output)
    else:
        print(render_result(result, color=_stdout_is_tty()), end="")

    if result.error:
        print(f"slackchat: {result.error}", file=sys.stderr)
        return EXIT_PROVIDER_ERROR
    return EXIT_OK


def _cmd_detect(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="slackchat detect")
    parser.add_argument("text")
    args = parser.parse_args(argv)
    print(detect(args.text))
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)

    if args and args[0] in SUBCOMMANDS:
        command, rest = args[0], args[1:]
        if command == "detect":
            return _cmd_detect(rest)
        print(f"slackchat: '{command}' is not implemented yet", file=sys.stderr)
        return EXIT_USAGE

    parsed = _oneshot_parser().parse_args(args)

    if parsed.text is not None:
        return _run_oneshot(parsed.text, mode=parsed.mode, raw=parsed.raw)

    if not _stdin_is_tty():
        return _run_oneshot(_read_stdin().strip("\n"), mode=parsed.mode, raw=parsed.raw)

    print("slackchat: interactive session arrives in a later task", file=sys.stderr)
    return EXIT_USAGE


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
