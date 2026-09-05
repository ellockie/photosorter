"""Console banners marking the boundary of every pipeline stage.

A run's terminal transcript has to be a complete record of what ran: every
stage names itself on the way in, and names itself again on the way out with
how it ended. That second line is the one that matters — without it a stage
that dies quietly is indistinguishable from one that never started.

The orchestrator emits these, never the stages themselves, so a new stage
cannot forget to announce itself and a failing one cannot skip its exit line.

Formatting stays plain text; colour is applied only at print time, so anything
capturing the banners (tests, log files) gets clean strings.
"""

try:
    from src.utils.colorise import Colorise
except Exception:  # colorama absent — plain text still has to work
    Colorise = None


# Outcome label -> Colorise method name.
OUTCOME_COLOURS = {
    "COMPLETE": "green",
    "FAILED": "red",
    "PAUSED": "yellow",
    "ABORTED": "red",
}
START_COLOUR = "blue"

# Widest outcome label, so the stage names line up in a column.
_LABEL_WIDTH = max(len(label) for label in OUTCOME_COLOURS)


def paint(text: str, colour: str | None) -> str:
    if Colorise is None or colour is None:
        return text
    painter = getattr(Colorise, colour, None)
    return painter(text) if painter else text


def _prefix(index: int, total: int) -> str:
    width = len(str(total))
    return f"STAGE {index:>{width}}/{total}"


def format_start(index: int, total: int, stage_id: str, display_name: str) -> str:
    return f">> {_prefix(index, total)}  {'START':<{_LABEL_WIDTH}}  {display_name}  [{stage_id}]"


def format_end(index: int, total: int, stage_id: str, display_name: str,
               outcome: str, seconds: float, detail: str = "") -> str:
    line = (
        f"<< {_prefix(index, total)}  {outcome:<{_LABEL_WIDTH}}  "
        f"{display_name}  [{stage_id}]  ({seconds:.1f}s)"
    )
    return f"{line}  {detail}" if detail else line


def announce_to_console(message: str) -> None:
    """Default sink: colour by outcome and print, unbuffered.

    Unbuffered because the dashboard runs the pipeline in a background thread
    while uvicorn holds the same stdout; a buffered banner can otherwise appear
    long after the stage it describes.
    """
    colour = START_COLOUR if message.startswith(">>") else None
    for label, candidate in OUTCOME_COLOURS.items():
        if f"  {label:<{_LABEL_WIDTH}}  " in message:
            colour = candidate
            break
    print(paint(message, colour), flush=True)
