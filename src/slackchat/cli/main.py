"""CLI entry point. Dispatch, exit codes, and nothing else of substance."""

from __future__ import annotations

import argparse
import json
import sys

from slackchat.cli.clipboard import copy as copy_to_clipboard
from slackchat.cli.render import render_result
from slackchat.cli.repl import run_session
from slackchat.config import load_dotenv
from slackchat.core.detect import detect
from slackchat.core.types import EmptyInputError
from slackchat.service import build_service
from slackchat.store import sqlite as store

EXIT_OK = 0
EXIT_EMPTY_INPUT = 1
EXIT_USAGE = 2
EXIT_PROVIDER_ERROR = 3

SUBCOMMANDS = frozenset({"detect", "log", "serve"})


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
    parser.add_argument(
        "text", nargs="?", help="text to process; omit to read stdin or start a session"
    )
    parser.add_argument(
        "--raw",
        action="store_true",
        help="print the processed text only, with no diff or metadata",
    )
    return parser


def _run_oneshot(text: str, *, raw: bool) -> int:
    service = build_service()
    try:
        result = service.run(text, client="cli")
    except EmptyInputError:
        print("slackchat: input is empty", file=sys.stderr)
        return EXIT_EMPTY_INPUT

    if raw:
        print(result.output)
    else:
        print(
            render_result(
                result,
                color=_stdout_is_tty(),
                show_status=service.config.cli.show_status,
            ),
            end="",
        )

    if result.error:
        print(f"slackchat: {result.error}", file=sys.stderr)
        return EXIT_PROVIDER_ERROR

    if (
        _stdout_is_tty()
        and service.config.cli.auto_copy
        and result.output
        and copy_to_clipboard(result.output)
    ):
        print("(copied to clipboard)")
    return EXIT_OK


def _cmd_detect(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="slackchat detect")
    parser.add_argument("text")
    args = parser.parse_args(argv)
    print(detect(args.text))
    return EXIT_OK


def _cmd_log(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="slackchat log")
    parser.add_argument("--last", type=int, default=20)
    parser.add_argument("--mode", choices=["correction", "translation"], default=None)
    args = parser.parse_args(argv)

    conn = store.connect()
    try:
        rows = store.recent_runs(conn, limit=args.last, mode=args.mode)
    finally:
        conn.close()

    if not rows:
        print("no runs logged yet")
        return EXIT_OK

    for row in rows:
        flags = ",".join(json.loads(row["flags"] or "[]")) or "-"
        cost = f"${row['cost_usd']:.6f}" if row["cost_usd"] is not None else "n/a"
        print(
            f"{row['created_at']}  {row['client']:<6} {row['mode']:<11} "
            f"{row['changed_ratio']:>6.2f}  {cost:>10}  {flags}"
        )
        print(f"    in : {_one_line(row['input'])}")
        print(f"    out: {_one_line(row['output'])}")
    return EXIT_OK


def _cmd_serve(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="slackchat serve")
    parser.parse_args(argv)
    from slackchat.server.app import serve

    return serve()


def _one_line(text: str, width: int = 100) -> str:
    collapsed = " ".join(text.split())
    return collapsed if len(collapsed) <= width else collapsed[: width - 1] + "…"


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    args = list(sys.argv[1:] if argv is None else argv)

    if args and args[0] in SUBCOMMANDS:
        command, rest = args[0], args[1:]
        if command == "detect":
            return _cmd_detect(rest)
        if command == "log":
            return _cmd_log(rest)
        if command == "serve":
            return _cmd_serve(rest)
        raise AssertionError(f"unrouted subcommand {command!r}")

    parsed = _oneshot_parser().parse_args(args)

    if parsed.text is not None:
        return _run_oneshot(parsed.text, raw=parsed.raw)

    if not _stdin_is_tty():
        return _run_oneshot(_read_stdin().strip("\n"), raw=parsed.raw)

    service = build_service()
    return run_session(
        service,
        read_line=input,
        write=lambda chunk: print(chunk, end=""),
        color=_stdout_is_tty(),
        copy_fn=copy_to_clipboard if _stdout_is_tty() else (lambda _text: False),
    )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
