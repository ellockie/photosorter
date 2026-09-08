"""Live progress for stages that take long enough to look hung.

A stage that walks tens of thousands of files is indistinguishable, from
outside, from a stage that has deadlocked: the dashboard node sits on "active"
and nothing else happens. This module is the answer to "what is it doing and
how much longer" -- a counter a stage advances as it works, which publishes a
structured record the dashboard renders as a bar, and drips a throttled line
into the run log so the console transcript says the same thing.

Two rates are tracked because the two questions differ. Item rate ("1,240
files/s") answers how fast the loop is turning; byte rate ("212 MB/s") answers
whether the bottleneck is the disk, which is what a hashing or copying stage is
actually limited by. A stage reports whichever it can measure, or both.

The ETA is deliberately naive -- remaining / average rate so far. It is a
progress indicator, not a promise, and a stage whose per-item cost varies (a
folder of 40 MB RAWs after a folder of 2 MB JPEGs) will see it move. That is
still far better than no number at all.

Nothing here raises: a reporter is instrumentation wrapped around real work,
and instrumentation must never be the reason a run dies.
"""

import time


# How often the structured record is refreshed for the dashboard. Fast enough
# to look live, slow enough that a tight loop is not dominated by bookkeeping.
PUBLISH_INTERVAL_SECONDS = 0.4
# How often a human-readable line is added to the run log. Much slower: the log
# is a transcript to read afterwards, not a progress bar.
LOG_INTERVAL_SECONDS = 5.0
# Below this many items, a stage is over before a progress bar would help.
MIN_ITEMS_WORTH_REPORTING = 25


def format_count(value) -> str:
    """12345 -> '12,345'.

    Thousands separators, because 120000 and 12000 are the same shape at a
    glance and a factor of ten apart.
    """
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return str(value)


def format_bytes(value) -> str:
    """Bytes as the unit a person would say out loud."""
    try:
        size = float(value)
    except (TypeError, ValueError):
        return str(value)
    for unit in ("B", "KB", "MB", "GB"):
        if abs(size) < 1024:
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def format_duration(seconds) -> str:
    """Seconds as '42s', '3m 20s', '1h 04m'. Never '0:00:03.418271'."""
    try:
        total = max(0.0, float(seconds))
    except (TypeError, ValueError):
        return "?"
    if total < 1:
        return "<1s"
    if total < 60:
        return f"{total:.0f}s"
    minutes, secs = divmod(int(total), 60)
    if minutes < 60:
        return f"{minutes}m {secs:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}m"


def format_rate(per_second, unit: str = "files") -> str:
    if not per_second or per_second <= 0:
        return ""
    if per_second >= 10:
        return f"{per_second:,.0f} {unit}/s"
    if per_second >= 1:
        return f"{per_second:.1f} {unit}/s"
    return f"{per_second:.2f} {unit}/s"


class StageProgress:
    """A counter one stage advances, published for the UI and the log.

    ``total`` may be unknown at construction (a stage often has to walk the
    tree before it knows how big the tree is); call ``set_total`` once it is,
    and the bar switches from an open-ended count to a real percentage.
    """

    def __init__(self, context, stage_id: str, activity: str,
                 total: int | None = None, unit: str = "files",
                 total_bytes: int | None = None,
                 log_interval_seconds: float = LOG_INTERVAL_SECONDS,
                 publish_interval_seconds: float = PUBLISH_INTERVAL_SECONDS,
                 min_items: int = MIN_ITEMS_WORTH_REPORTING):
        self.context = context
        self.stage_id = stage_id
        # What the stage is doing right now, in words: "Hashing archive files",
        # "Reading EXIF sidecars". The qualitative half of the report.
        self.activity = activity
        self.unit = unit
        self.total = total
        self.total_bytes = total_bytes
        self.done = 0
        self.bytes_done = 0
        self.errors = 0
        self.note = ""
        self.started_at = time.monotonic()
        self._log_interval = log_interval_seconds
        self._publish_interval = publish_interval_seconds
        self._min_items = min_items
        self._last_publish = 0.0
        self._last_log = self.started_at
        self.publish(force=True)

    # -- the numbers ------------------------------------------------------

    @property
    def elapsed(self) -> float:
        return max(1e-9, time.monotonic() - self.started_at)

    @property
    def item_rate(self) -> float:
        return self.done / self.elapsed

    @property
    def byte_rate(self) -> float:
        return self.bytes_done / self.elapsed

    @property
    def fraction(self) -> float | None:
        if not self.total:
            return None
        return min(1.0, self.done / self.total)

    @property
    def eta_seconds(self) -> float | None:
        """Remaining work at the average rate so far.

        By bytes where the work is byte-bound (hashing, copying) and by items
        otherwise -- a hashing stage's remaining time depends on how big the
        files left are, not how many.
        """
        if self.total_bytes and self.bytes_done:
            remaining = max(0, self.total_bytes - self.bytes_done)
            return remaining / self.byte_rate if self.byte_rate > 0 else None
        if self.total and self.done:
            remaining = max(0, self.total - self.done)
            return remaining / self.item_rate if self.item_rate > 0 else None
        return None

    # -- driving it -------------------------------------------------------

    def set_total(self, total: int | None = None, total_bytes: int | None = None) -> None:
        if total is not None:
            self.total = total
        if total_bytes is not None:
            self.total_bytes = total_bytes
        self.publish(force=True)

    def set_activity(self, activity: str, note: str = "") -> None:
        self.activity = activity
        self.note = note
        self.publish(force=True)

    def advance(self, count: int = 1, size_bytes: int = 0, note: str | None = None,
                errors: int = 0) -> None:
        self.done += count
        self.bytes_done += size_bytes
        self.errors += errors
        if note is not None:
            self.note = note
        self.publish()
        self.maybe_log()

    # -- reporting --------------------------------------------------------

    def summary(self) -> str:
        """One line: what, how far, how fast, how much longer."""
        parts = [self.activity]
        if self.total:
            parts.append(
                f"{format_count(self.done)}/{format_count(self.total)} {self.unit}"
                f" ({(self.fraction or 0) * 100:.0f}%)"
            )
        else:
            parts.append(f"{format_count(self.done)} {self.unit}")
        if self.total_bytes:
            parts.append(f"{format_bytes(self.bytes_done)} of {format_bytes(self.total_bytes)}")
        elif self.bytes_done:
            parts.append(format_bytes(self.bytes_done))
        rate = self._rate_text()
        if rate:
            parts.append(rate)
        eta = self.eta_seconds
        if eta is not None and self.done:
            parts.append(f"ETA {format_duration(eta)}")
        if self.errors:
            parts.append(f"{format_count(self.errors)} error(s)")
        if self.note:
            parts.append(self.note)
        return " | ".join(part for part in parts if part)

    def _rate_text(self) -> str:
        if self.bytes_done:
            return format_rate(self.byte_rate / 1024 / 1024, "MB")
        return format_rate(self.item_rate, self.unit)

    def record(self) -> dict:
        return {
            "activity": self.activity,
            "note": self.note,
            "unit": self.unit,
            "done": self.done,
            "total": self.total,
            "fraction": self.fraction,
            "bytes_done": self.bytes_done,
            "total_bytes": self.total_bytes,
            "errors": self.errors,
            "elapsed_seconds": self.elapsed,
            "item_rate": self.item_rate,
            "byte_rate": self.byte_rate,
            "eta_seconds": self.eta_seconds,
            "summary": self.summary(),
            "finished": False,
        }

    def publish(self, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - self._last_publish < self._publish_interval:
            return
        self._last_publish = now
        setter = getattr(self.context, "set_stage_progress", None)
        if setter:
            setter(self.stage_id, self.record())

    def maybe_log(self) -> None:
        """Drip a line into the run log, but only for work big enough to need
        one -- a 12-file stage should not narrate itself."""
        if self.total is not None and self.total < self._min_items:
            return
        now = time.monotonic()
        if now - self._last_log < self._log_interval:
            return
        self._last_log = now
        self.context.log(f"  ... {self.summary()}")

    def finish(self, note: str = "") -> str:
        """Close the report and return the line describing the whole span."""
        if note:
            self.note = note
        line = (
            f"{self.activity}: {format_count(self.done)} {self.unit}"
            + (f" ({format_bytes(self.bytes_done)})" if self.bytes_done else "")
            + f" in {format_duration(self.elapsed)}"
        )
        rate = self._rate_text()
        if rate:
            line += f" at {rate}"
        if self.errors:
            line += f", {format_count(self.errors)} error(s)"
        if self.note:
            line += f" -- {self.note}"
        record = self.record()
        record["finished"] = True
        record["summary"] = line
        setter = getattr(self.context, "set_stage_progress", None)
        if setter:
            setter(self.stage_id, record)
        return line
