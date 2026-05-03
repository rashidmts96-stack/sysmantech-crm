import os
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


DEFAULT_APP_TIMEZONE_NAME = "Asia/Kolkata"
DEFAULT_APP_TIMEZONE_OFFSET_MINUTES = 330
DEFAULT_DISPLAY_DATETIME_FORMAT = "%d/%m/%Y %H:%M"
DEFAULT_DISPLAY_DATE_FORMAT = "%d/%m/%Y"


def get_app_timezone_name():
    configured_name = str(os.getenv("APP_TIMEZONE") or "").strip()
    return configured_name or DEFAULT_APP_TIMEZONE_NAME


def get_app_timezone_offset_minutes():
    configured_offset = str(os.getenv("APP_TIMEZONE_OFFSET_MINUTES") or "").strip()
    if configured_offset:
        try:
            return int(configured_offset)
        except ValueError:
            pass

    if get_app_timezone_name() == DEFAULT_APP_TIMEZONE_NAME:
        return DEFAULT_APP_TIMEZONE_OFFSET_MINUTES
    return 0


def get_app_timezone():
    timezone_name = get_app_timezone_name()
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        return timezone(timedelta(minutes=get_app_timezone_offset_minutes()), timezone_name or None)


def business_now():
    return datetime.now(get_app_timezone())


def business_now_naive():
    return business_now().replace(tzinfo=None)


def normalize_display_datetime(value):
    if not value:
        return None

    if isinstance(value, datetime):
        normalized_value = value
    elif isinstance(value, date):
        normalized_value = datetime.combine(value, time.min)
    else:
        text_value = str(value or "").strip()
        if not text_value:
            return None
        if text_value.endswith("Z"):
            text_value = text_value[:-1] + "+00:00"
        try:
            normalized_value = datetime.fromisoformat(text_value)
        except ValueError:
            return None

    if normalized_value.tzinfo is not None:
        normalized_value = normalized_value.astimezone(get_app_timezone()).replace(tzinfo=None)
    return normalized_value


def format_datetime_display(value):
    normalized_value = normalize_display_datetime(value)
    if not normalized_value:
        return ""
    return normalized_value.strftime(DEFAULT_DISPLAY_DATETIME_FORMAT)


def format_date_display(value):
    if not value:
        return ""

    if isinstance(value, datetime):
        normalized_value = normalize_display_datetime(value)
        return normalized_value.strftime(DEFAULT_DISPLAY_DATE_FORMAT) if normalized_value else ""

    if isinstance(value, date):
        return value.strftime(DEFAULT_DISPLAY_DATE_FORMAT)

    text_value = str(value or "").strip()
    if not text_value:
        return ""

    normalized_value = normalize_display_datetime(text_value)
    if normalized_value:
        return normalized_value.strftime(DEFAULT_DISPLAY_DATE_FORMAT)
    return text_value


def mysql_session_timezone_value():
    offset = business_now().utcoffset() or timedelta(0)
    total_minutes = int(offset.total_seconds() // 60)
    sign = "+" if total_minutes >= 0 else "-"
    absolute_minutes = abs(total_minutes)
    hours, minutes = divmod(absolute_minutes, 60)
    return f"{sign}{hours:02d}:{minutes:02d}"
