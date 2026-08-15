"""Timezone helpers for SI-KAPAL.

Architecture:
- UTC is the universal instant used for technical timestamps.
- Academic/school schedule logic always follows WIT (Asia/Jayapura).
- The client may convert a WIT schedule to the device's local timezone only
  for presentation; it must not change the schedule's meaning.
"""

from datetime import datetime
from zoneinfo import ZoneInfo
import os

UTC = ZoneInfo("UTC")
DEFAULT_SCHOOL_TIMEZONE = "Asia/Jayapura"


def school_timezone_name() -> str:
    """Return a valid configured school timezone, defaulting safely to WIT."""
    value = (os.getenv("SCHOOL_TIMEZONE") or DEFAULT_SCHOOL_TIMEZONE).strip()
    value = value or DEFAULT_SCHOOL_TIMEZONE
    try:
        ZoneInfo(value)
        return value
    except Exception:
        return DEFAULT_SCHOOL_TIMEZONE


def school_timezone() -> ZoneInfo:
    """Return the validated school timezone."""
    return ZoneInfo(school_timezone_name())


def utc_now() -> datetime:
    """Timezone-aware current UTC instant."""
    return datetime.now(UTC)


def utc_now_naive() -> datetime:
    """Naive UTC for legacy MySQL DATETIME columns without timezone metadata."""
    return utc_now().replace(tzinfo=None)


def school_now() -> datetime:
    """Current instant represented in the school's timezone (WIT by default)."""
    return utc_now().astimezone(school_timezone())


def school_now_naive() -> datetime:
    """Naive school-local datetime for legacy columns that store local clock values."""
    return school_now().replace(tzinfo=None)


def school_today():
    """Current calendar date according to the school timezone."""
    return school_now().date()


def timezone_metadata() -> dict:
    """Small metadata payload clients may expose for schedule presentation."""
    tz = school_timezone()
    now = school_now()
    offset = now.utcoffset()
    offset_minutes = int(offset.total_seconds() // 60) if offset else 0
    return {
        "school_timezone": school_timezone_name(),
        "school_timezone_label": "WIT" if school_timezone_name() == "Asia/Jayapura" else school_timezone_name(),
        "school_utc_offset_minutes": offset_minutes,
    }
