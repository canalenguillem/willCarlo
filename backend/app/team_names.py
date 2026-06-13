"""Normalización de nombres de equipos. Port de Helpers/TeamNameNormalizer.cs.

Convierte nombres en distintas grafías a una forma canónica y a un id slug
estable (p. ej. "Türkiye" -> "Turkey" -> "turkey") para poder cruzar las
distintas fuentes (grupos, FIFA, Elo, resultados históricos).
"""
from __future__ import annotations

import re
import unicodedata

_ALIASES: dict[str, str] = {
    "usa": "United States",
    "u.s.a": "United States",
    "usmnt": "United States",
    "united states of america": "United States",
    "bosnia": "Bosnia and Herzegovina",
    "bosnia herzegovina": "Bosnia and Herzegovina",
    "korea republic": "South Korea",
    "republic of korea": "South Korea",
    "south korea": "South Korea",
    "turkiye": "Turkey",
    "czech republic": "Czechia",
    "cote d'ivoire": "Ivory Coast",
    "dr congo": "Congo DR",
    "congo dr": "Congo DR",
    "iran": "Iran",
    "ir iran": "Iran",
}


def _remove_diacritics(text: str) -> str:
    normalized = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")


def canonical_name(name: str) -> str:
    cleaned = re.sub(r"\s+", " ", name.strip())
    key = _remove_diacritics(cleaned).lower()
    return _ALIASES.get(key, cleaned)


def to_id(name: str) -> str:
    canonical = canonical_name(name)
    ascii_name = _remove_diacritics(canonical).lower()
    ascii_name = re.sub(r"[^a-z0-9]+", "-", ascii_name).strip("-")
    return ascii_name
