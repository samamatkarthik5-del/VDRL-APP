from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation


def clean_cell(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return re.sub(r"\s+", " ", str(value).replace("\x00", " ")).strip()


def normalise_header(value: object) -> str:
    text = clean_cell(value).upper()
    text = text.replace("&", " AND ")
    text = re.sub(r"[^A-Z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def to_decimal(value: object) -> Decimal | None:
    text = clean_cell(value).replace(",", "")
    if not text:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        match = re.search(r"[-+]?\d+(?:\.\d+)?", text)
        if not match:
            return None
        try:
            return Decimal(match.group(0))
        except InvalidOperation:
            return None


def parse_temperature_range(value: object) -> tuple[Decimal | None, Decimal | None]:
    text = clean_cell(value).replace("−", "-").replace("–", "-")
    numbers = re.findall(r"[-+]?\d+(?:\.\d+)?", text)
    if not numbers:
        return None, None
    decimals = [Decimal(number) for number in numbers]
    if len(decimals) == 1:
        return decimals[0], decimals[0]
    return min(decimals[0], decimals[1]), max(decimals[0], decimals[1])


def append_text(existing: str, incoming: str) -> str:
    incoming = clean_cell(incoming)
    if not incoming:
        return existing
    if not existing:
        return incoming
    if incoming in existing:
        return existing
    return f"{existing}\n{incoming}"
