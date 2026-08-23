"""The interactive session. A blank line submits; ``/exit`` leaves at once."""

from __future__ import annotations

from collections.abc import Callable

from slackchat.cli.banner import banner
from slackchat.cli.render import render_result
from slackchat.core.types import EmptyInputError
from slackchat.service import Service

PROMPT = "> "
CONTINUATION = "... "
EXIT_WORDS = frozenset({"/exit", "/quit"})


def run_session(
    service: Service,
    *,
    read_line: Callable[[str], str],
    write: Callable[[str], None],
    color: bool,
    copy_fn: Callable[[str], bool],
) -> int:
    """Read multi-line turns until EOF, Ctrl+C, or an exit word.

    A blank line submits the buffer, which is what lets a multi-line paste
    arrive as one input instead of being chopped into a run per line.
    """
    write(banner(color))
    buffer: list[str] = []

    while True:
        prompt = CONTINUATION if buffer else PROMPT
        try:
            line = read_line(prompt)
        except (EOFError, KeyboardInterrupt):
            write("\n")
            return 0

        if line.strip() in EXIT_WORDS:
            return 0

        if line.strip() == "" and not buffer:
            continue  # nothing typed yet: silently re-prompt

        if line.strip() != "" or not buffer:
            buffer.append(line)
            continue

        text = "\n".join(buffer)
        buffer = []
        _handle_turn(service, text, write=write, color=color, copy_fn=copy_fn)


def _handle_turn(
    service: Service,
    text: str,
    *,
    write: Callable[[str], None],
    color: bool,
    copy_fn: Callable[[str], bool],
) -> None:
    try:
        result = service.run(text, client="cli")
    except EmptyInputError:
        return

    write(render_result(result, color=color))
    if result.error:
        return
    if service.config.cli.auto_copy and result.output and copy_fn(result.output):
        write("(copied to clipboard)\n")
