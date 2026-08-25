"""The interactive session. A blank line submits; ``/exit`` leaves at once."""

from __future__ import annotations

from collections.abc import Callable

from slackchat.cli.banner import banner
from slackchat.cli.render import render_result
from slackchat.core.types import EmptyInputError
from slackchat.service import Service

PROMPT = "> "
CONTINUATION = ""
PENDING_SUBMIT = "(blank line to send) "
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

    Two consecutive blank lines submit the buffer. A single blank line is
    kept as a paragraph break instead, so pasting text that has blank lines
    between paragraphs arrives as one input rather than being chopped into
    a run per paragraph. The prompt switches to ``PENDING_SUBMIT`` for that
    second line so the wait for it doesn't look like an unexplained hang.
    """
    write(banner(color))
    buffer: list[str] = []
    pending_blank = False

    while True:
        if pending_blank:
            prompt = PENDING_SUBMIT
        elif buffer:
            prompt = CONTINUATION
        else:
            prompt = PROMPT
        try:
            line = read_line(prompt)
        except EOFError, KeyboardInterrupt:
            write("\n")
            return 0

        if line.strip() in EXIT_WORDS:
            return 0

        if line.strip() != "":
            if pending_blank:
                buffer.append("")  # confirmed paragraph break, not a submit
                pending_blank = False
            buffer.append(line)
            continue

        if not buffer:
            continue  # nothing typed yet: silently re-prompt

        if not pending_blank:
            pending_blank = True  # could be a paragraph break or a submit
            continue

        text = "\n".join(buffer)
        buffer = []
        pending_blank = False
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
