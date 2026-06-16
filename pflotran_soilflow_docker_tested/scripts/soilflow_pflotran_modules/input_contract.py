from __future__ import annotations

from typing import Any


def as_float(value: Any, default: float | None = None) -> float:
    if value is None or value == "":
        if default is None:
            raise ValueError("Пустое значение нельзя преобразовать в float")
        return float(default)
    if isinstance(value, str):
        value = value.replace(",", ".").strip()
    return float(value)


def as_int(value: Any, default: int | None = None) -> int:
    if value is None or value == "":
        if default is None:
            raise ValueError("Пустое значение нельзя преобразовать в int")
        return int(default)
    return int(float(value))


def as_bool(value: Any, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"true", "1", "yes", "y", "да", "истина", "вкл"}


def optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return as_float(value)


def clean_key(value: Any) -> str:
    return str(value).strip()


def pf_float(value: float) -> str:
    """Формат числа для PFLOTRAN/Fortran parser с d-экспонентой."""
    if abs(value) == 0:
        return "0.d0"
    return f"{value:.12e}".replace("e", "d")

