"""Tiny env-var readers with typed defaults, used by settings and services."""
import os


def env_str(key: str, default: str = "") -> str:
    value = os.environ.get(key)
    return value.strip() if value not in (None, "") else default


def env_bool(key: str, default: bool = False) -> bool:
    value = os.environ.get(key)
    if value in (None, ""):
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def env_int(key: str, default: int = 0) -> int:
    value = os.environ.get(key)
    if value in (None, ""):
        return default
    try:
        return int(value)
    except ValueError:
        return default


def env_list(key: str, default=None, separator: str = ",") -> list:
    value = os.environ.get(key)
    if value in (None, ""):
        return list(default or [])
    return [item.strip() for item in value.split(separator) if item.strip()]
