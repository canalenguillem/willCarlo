"""Cuadro oficial del Mundial 2026 (48 equipos, 12 grupos A-L).

Port de Services/Simulation/WorldCup2026Bracket.cs. Define los 16 cruces de
dieciseisavos (Round of 32) con sus slots (ganador/segundo/mejor tercero de un
grupo, o ganador de un cruce previo) y la asignación de los 8 mejores terceros a
las posiciones reservadas mediante backtracking.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


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


def assign_third_place_groups(qualified_third_groups: list[str]) -> dict[int, str]:
    """Asigna los 8 grupos con mejor tercero a los slots GROUP_THIRD del Round of 32.

    Igual que el original: ordena los slots por la cantidad de opciones disponibles
    (más restringidos primero) y resuelve por backtracking."""
    if len(qualified_third_groups) != 8:
        raise ValueError(
            f"El cuadro 2026 requiere exactamente ocho grupos con terceros clasificados, "
            f"pero recibió {len(qualified_third_groups)}."
        )
    qualified = {g.upper() for g in qualified_third_groups}

    third_slots = []
    for tie in ROUND_OF_32:
        opts = None
        if tie.home.kind == SlotKind.GROUP_THIRD:
            opts = tie.home.third_options
        elif tie.away.kind == SlotKind.GROUP_THIRD:
            opts = tie.away.third_options
        if opts is not None:
            third_slots.append((tie.id, list(opts)))

    third_slots.sort(key=lambda s: (sum(1 for g in s[1] if g.upper() in qualified), s[0]))

    assigned: dict[int, str] = {}
    used: set[str] = set()

    def group_order(g: str) -> int:
        return ord(g[0]) - ord("A") if g else 10**9

    def try_assign(index: int) -> bool:
        if index == len(third_slots):
            return True
        tie_id, options = third_slots[index]
        for group in sorted((g for g in options if g.upper() in qualified), key=group_order):
            if group.upper() in used:
                continue
            assigned[tie_id] = group
            used.add(group.upper())
            if try_assign(index + 1):
                return True
            del assigned[tie_id]
            used.discard(group.upper())
        return False

    if not try_assign(0):
        raise ValueError(
            f"No se pudieron asignar los grupos de terceros {sorted(qualified_third_groups)} "
            f"a los cruces oficiales de 2026."
        )
    return assigned


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
