"""Value formatting for terminal display.

Anything user-facing that contains words goes through `i18n.t()` so the whole
app switches language at once. Pure numbers and units (KB, MB, %) stay as-is.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from dtcleaner.i18n import t

_UNITS = ("B", "KB", "MB", "GB", "TB", "PB")


def human_bytes(size: int | float | None, precision: int = 1) -> str:
    """1536 -> '1.5 KB'. Base 1024, matching what Windows Explorer reports."""
    if size is None:
        return "--"
    value = float(size)
    negative = value < 0
    value = abs(value)
    idx = 0
    while value >= 1024 and idx < len(_UNITS) - 1:
        value /= 1024
        idx += 1
    digits = 0 if idx == 0 else precision
    text = f"{value:.{digits}f} {_UNITS[idx]}"
    return f"-{text}" if negative else text


def human_duration(seconds: float | None) -> str:
    if seconds is None:
        return "--"
    if seconds < 1:
        return f"{seconds * 1000:.0f}ms"
    if seconds < 60:
        return f"{seconds:.1f}s"
    delta = timedelta(seconds=int(seconds))
    hours, rem = divmod(delta.seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if delta.days or hours:
        return f"{delta.days * 24 + hours}h {minutes}m"
    return f"{minutes}m {secs}s"


def human_date(value: datetime | None) -> str:
    if value is None:
        return "--"
    return value.strftime("%Y-%m-%d %H:%M")


def relative_age(value: datetime | None, now: datetime | None = None) -> str:
    """"3 days ago" -- helps the user judge whether an artifact still matters."""
    if value is None:
        return "--"
    now = now or datetime.now(tz=value.tzinfo)
    delta = now - value
    days = delta.days
    if days < 0:
        return t("time.future")
    if days == 0:
        hours = delta.seconds // 3600
        return t("time.now") if hours == 0 else t("time.hours_ago", hours=hours)
    if days == 1:
        return t("time.yesterday")
    if days < 30:
        return t("time.days_ago", days=days)
    if days < 365:
        return t("time.months_ago", months=days // 30)
    return t("time.years_ago", years=days // 365)


def percent(part: float, total: float) -> str:
    if not total:
        return "0%"
    return f"{(part / total) * 100:.0f}%"


def bar(part: float, total: float, width: int = 20, fill: str = "█", empty: str = "░") -> str:
    """Simple gauge for use inside Rich tables and panels."""
    if total <= 0:
        return empty * width
    ratio = max(0.0, min(1.0, part / total))
    filled = round(ratio * width)
    return fill * filled + empty * (width - filled)
