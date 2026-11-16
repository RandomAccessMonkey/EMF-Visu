"""Localized text carried by engine metadata (English and Hungarian)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class LocalizedText(BaseModel):
    model_config = ConfigDict(extra="forbid")
    en: str
    hu: str


def L(en: str, hu: str) -> LocalizedText:  # noqa: N802 - short constructor used in data tables
    return LocalizedText(en=en, hu=hu)
