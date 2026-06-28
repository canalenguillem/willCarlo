"""Cuadro oficial del Mundial 2026 (48 equipos, 12 grupos A-L).

Port de Services/Simulation/WorldCup2026Bracket.cs. Define los 16 cruces de
dieciseisavos (Round of 32) con sus slots (ganador/segundo/mejor tercero de un
grupo, o ganador de un cruce previo) y la asignación de los 8 mejores terceros a
las posiciones reservadas mediante backtracking.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class SlotKind(Enum):
    GROUP_WINNER = "GroupWinner"
    GROUP_RUNNER_UP = "GroupRunnerUp"
    GROUP_THIRD = "GroupThird"
    WINNER_OF_TIE = "WinnerOfTie"


@dataclass(frozen=True)
class BracketSlot:
    kind: SlotKind
    group: str | None = None
    tie_id: int | None = None
    third_options: tuple[str, ...] = ()


@dataclass(frozen=True)
class BracketTie:
    id: int
    stage: str
    home: BracketSlot
    away: BracketSlot


def _winner(group: str) -> BracketSlot:
    return BracketSlot(SlotKind.GROUP_WINNER, group=group)


def _runner_up(group: str) -> BracketSlot:
    return BracketSlot(SlotKind.GROUP_RUNNER_UP, group=group)


def _third(*groups: str) -> BracketSlot:
    return BracketSlot(SlotKind.GROUP_THIRD, third_options=tuple(groups))


def _winner_of(tie_id: int) -> BracketSlot:
    return BracketSlot(SlotKind.WINNER_OF_TIE, tie_id=tie_id)


ROUND_OF_32: list[BracketTie] = [
    BracketTie(73, "RoundOf32", _runner_up("A"), _runner_up("B")),
    BracketTie(74, "RoundOf32", _winner("E"), _third("A", "B", "C", "D", "F")),
    BracketTie(75, "RoundOf32", _winner("F"), _runner_up("C")),
    BracketTie(76, "RoundOf32", _winner("C"), _runner_up("F")),
    BracketTie(77, "RoundOf32", _winner("I"), _third("C", "D", "F", "G", "H")),
    BracketTie(78, "RoundOf32", _runner_up("E"), _runner_up("I")),
    BracketTie(79, "RoundOf32", _winner("A"), _third("C", "E", "F", "H", "I")),
    BracketTie(80, "RoundOf32", _winner("L"), _third("E", "H", "I", "J", "K")),
    BracketTie(81, "RoundOf32", _winner("D"), _third("B", "E", "F", "I", "J")),
    BracketTie(82, "RoundOf32", _winner("G"), _third("A", "E", "H", "I", "J")),
    BracketTie(83, "RoundOf32", _runner_up("K"), _runner_up("L")),
    BracketTie(84, "RoundOf32", _winner("H"), _runner_up("J")),
    BracketTie(85, "RoundOf32", _winner("B"), _third("E", "F", "G", "I", "J")),
    BracketTie(86, "RoundOf32", _winner("J"), _runner_up("H")),
    BracketTie(87, "RoundOf32", _winner("K"), _third("D", "E", "I", "J", "L")),
    BracketTie(88, "RoundOf32", _runner_up("D"), _runner_up("G")),
]

ROUND_OF_16: list[BracketTie] = [
    BracketTie(89, "RoundOf16", _winner_of(74), _winner_of(77)),
    BracketTie(90, "RoundOf16", _winner_of(73), _winner_of(75)),
    BracketTie(91, "RoundOf16", _winner_of(76), _winner_of(78)),
    BracketTie(92, "RoundOf16", _winner_of(79), _winner_of(80)),
    BracketTie(93, "RoundOf16", _winner_of(83), _winner_of(84)),
    BracketTie(94, "RoundOf16", _winner_of(81), _winner_of(82)),
    BracketTie(95, "RoundOf16", _winner_of(86), _winner_of(88)),
    BracketTie(96, "RoundOf16", _winner_of(85), _winner_of(87)),
]

QUARTER_FINALS: list[BracketTie] = [
    BracketTie(97, "QuarterFinal", _winner_of(89), _winner_of(90)),
    BracketTie(98, "QuarterFinal", _winner_of(93), _winner_of(94)),
    BracketTie(99, "QuarterFinal", _winner_of(91), _winner_of(92)),
    BracketTie(100, "QuarterFinal", _winner_of(95), _winner_of(96)),
]

SEMI_FINALS: list[BracketTie] = [
    BracketTie(101, "SemiFinal", _winner_of(97), _winner_of(98)),
    BracketTie(102, "SemiFinal", _winner_of(99), _winner_of(100)),
]

FINAL = BracketTie(104, "Final", _winner_of(101), _winner_of(102))


# Tabla OFICIAL de asignación de terceros de FIFA (Annexe C de las Regulations 2026):
# las 495 combinaciones posibles de 8 grupos-tercero y a qué llave va cada uno.
# Reproducción verificada contra el PDF oficial (dw-football/wc2026-bracket).
# Formato: clave = 8 letras de grupo ordenadas (p.ej. "BDEFIJKL"); valor = {"1X": grupo},
# donde 1X es el ganador de grupo que enfrenta a ese tercero.
_THIRD_ALLOCATION: dict[str, dict[str, str]] = json.loads(
    (Path(__file__).parent / "third_place_allocation.json").read_text(encoding="utf-8")
)

# Ganador de grupo (1X) -> id de la llave de dieciseisavos donde juega contra un tercero.
_WINNER_POS_TO_TIE: dict[str, int] = {
    "1A": 79, "1B": 85, "1D": 81, "1E": 74, "1G": 82, "1I": 77, "1K": 87, "1L": 80,
}


def assign_third_place_groups(qualified_third_groups: list[str]) -> dict[int, str]:
    """Asigna los 8 grupos con mejor tercero a los slots GROUP_THIRD del Round of 32
    según la tabla OFICIAL de FIFA (no por backtracking, que daba una asignación válida
    pero distinta a la de FIFA).

    Devuelve {tie_id: letra_de_grupo} para las 8 llaves que llevan un tercero."""
    if len(qualified_third_groups) != 8:
        raise ValueError(
            f"El cuadro 2026 requiere exactamente ocho grupos con terceros clasificados, "
            f"pero recibió {len(qualified_third_groups)}."
        )
    key = "".join(sorted(g.upper() for g in qualified_third_groups))
    row = _THIRD_ALLOCATION.get(key)
    if row is None:
        raise ValueError(
            f"Combinación de grupos-tercero no reconocida en la tabla oficial de FIFA: {key}."
        )
    return {_WINNER_POS_TO_TIE[winner_pos]: group.upper() for winner_pos, group in row.items()}


def _opponent_label(slot: BracketSlot) -> str:
    if slot.kind == SlotKind.GROUP_WINNER:
        return f"1º {slot.group}"
    if slot.kind == SlotKind.GROUP_RUNNER_UP:
        return f"2º {slot.group}"
    if slot.kind == SlotKind.GROUP_THIRD:
        return "3º (" + "/".join(slot.third_options) + ")"
    return "?"


def group_routes() -> dict[str, dict]:
    """Para cada grupo, a qué cruce de dieciseisavos va su 1º y su 2º, y contra qué
    rival (etiqueta de posición). Estructura estática del cuadro oficial 2026."""
    routes: dict[str, dict] = {}
    for tie in ROUND_OF_32:
        for slot, other in ((tie.home, tie.away), (tie.away, tie.home)):
            if slot.kind == SlotKind.GROUP_WINNER:
                routes.setdefault(slot.group, {})["first"] = {"tie_id": tie.id, "opponent": _opponent_label(other)}
            elif slot.kind == SlotKind.GROUP_RUNNER_UP:
                routes.setdefault(slot.group, {})["second"] = {"tie_id": tie.id, "opponent": _opponent_label(other)}
    return routes
