"""Cuadro REAL del torneo a partir de resultados cargados a mano.

A diferencia de simulation.py (que samplea marcadores), aquí las posiciones de
grupo salen de los `Fixture` jugados y el cuadro se resuelve con esos resultados
más los marcadores de eliminación guardados en `KnockoutResult`. El estado es
parcial: un slot queda en `None` mientras no se conozca el equipo que lo ocupa.

Reutiliza la matemática del Montecarlo (mismos desempates): `GroupTable`,
`rank_best_thirds`, `_slot_label`, y el cuadro oficial de `bracket.py`.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from . import bracket as brk
from .bracket import SlotKind
from .models import Fixture, Group, KnockoutResult
from .simulation import GroupTable, SimulatedMatch, _slot_label, rank_best_thirds

# Todas las llaves del cuadro, indexadas por id (la numeración no es contigua: la
# final es 104). Sirve para validar tie_id y para recorrer el cuadro.
ALL_TIES: dict[int, brk.BracketTie] = {
    t.id: t
    for t in [*brk.ROUND_OF_32, *brk.ROUND_OF_16, *brk.QUARTER_FINALS, *brk.SEMI_FINALS, brk.FINAL]
}


def _expected_matches(n: int) -> int:
    return n * (n - 1) // 2


def build_group_tables(db: Session, fifa: dict[str, float]) -> dict[str, GroupTable]:
    """Una GroupTable por grupo, alimentada solo con los fixtures jugados.

    Respeta la orientación home=team_a (importa para el desempate head-to-head)."""
    fixtures_by_group: dict[str, list[Fixture]] = {}
    for f in db.query(Fixture).all():
        fixtures_by_group.setdefault(f.group, []).append(f)

    tables: dict[str, GroupTable] = {}
    for g in db.query(Group).order_by(Group.name).all():
        table = GroupTable(g.name, list(g.team_ids), fifa)
        for f in fixtures_by_group.get(g.name, []):
            if f.is_played and f.home_goals is not None and f.away_goals is not None:
                table.add_match(
                    SimulatedMatch(g.name, f.home_team_id, f.away_team_id, f.home_goals, f.away_goals)
                )
        tables[g.name] = table
    return tables


def group_is_complete(table: GroupTable) -> bool:
    return len(table.matches) == _expected_matches(len(table.standings))


def _slot(team_id: str | None, label: str, names: dict[str, str]) -> dict:
    return {"team_id": team_id, "name": names.get(team_id) if team_id else None, "label": label}


def real_bracket_state(db: Session, fifa: dict[str, float], names: dict[str, str]) -> dict:
    """Estado completo del cuadro real: tablas de grupos + eliminación resuelta."""
    tables = build_group_tables(db, fifa)
    ranked_by_group = {name: t.rank() for name, t in tables.items()}
    complete = {name: group_is_complete(t) for name, t in tables.items()}
    all_complete = all(complete.values())

    groups_out = [
        {
            "name": name,
            "complete": complete[name],
            "standings": [
                {
                    "position": i + 1,
                    "team_id": s.team_id,
                    "name": names.get(s.team_id, s.team_id),
                    "points": s.points,
                    "goals_for": s.goals_for,
                    "goals_against": s.goals_against,
                    "goal_diff": s.goal_diff,
                }
                for i, s in enumerate(ranked_by_group[name])
            ],
        }
        for name in sorted(tables)
    ]

    # Slots de grupo: solo para grupos completos.
    group_slots: dict[str, tuple[str, str, str]] = {}
    for name, ranked in ranked_by_group.items():
        if complete[name] and len(ranked) >= 3:
            group_slots[name] = (ranked[0].team_id, ranked[1].team_id, ranked[2].team_id)

    # Terceros: la asignación oficial exige los 8 (los 12 grupos completos).
    third_assignments: dict[int, str] = {}
    third_by_group: dict[str, str] = {}
    if all_complete:
        thirds = [ranked_by_group[name][2] for name in ranked_by_group if len(ranked_by_group[name]) >= 3]
        best = rank_best_thirds(thirds, fifa)[:8]
        third_assignments = brk.assign_third_place_groups([t.group for t in best])
        third_by_group = {t.group.upper(): t.team_id for t in best}

    ko_rows = {r.tie_id: r for r in db.query(KnockoutResult).all()}
    winners: dict[int, str] = {}

    def resolve(tie: brk.BracketTie, slot: brk.BracketSlot) -> str | None:
        if slot.kind == SlotKind.GROUP_WINNER:
            gs = group_slots.get(slot.group)
            return gs[0] if gs else None
        if slot.kind == SlotKind.GROUP_RUNNER_UP:
            gs = group_slots.get(slot.group)
            return gs[1] if gs else None
        if slot.kind == SlotKind.GROUP_THIRD:
            grp = third_assignments.get(tie.id)
            return third_by_group.get(grp.upper()) if grp else None
        if slot.kind == SlotKind.WINNER_OF_TIE:
            return winners.get(slot.tie_id)
        return None

    def tie_state(tie: brk.BracketTie) -> dict:
        home_id = resolve(tie, tie.home)
        away_id = resolve(tie, tie.away)
        playable = home_id is not None and away_id is not None
        row = ko_rows.get(tie.id)

        winner_id: str | None = None
        if playable and row is not None:
            if row.home_goals > row.away_goals:
                winner_id = home_id
            elif row.away_goals > row.home_goals:
                winner_id = away_id
            elif row.penalty_winner == "home":
                winner_id = home_id
            elif row.penalty_winner == "away":
                winner_id = away_id
        if winner_id is not None:
            winners[tie.id] = winner_id

        return {
            "tie_id": tie.id,
            "stage": tie.stage,
            "home": _slot(home_id, _slot_label(tie, tie.home, third_assignments), names),
            "away": _slot(away_id, _slot_label(tie, tie.away, third_assignments), names),
            "playable": playable,
            "home_goals": row.home_goals if row else None,
            "away_goals": row.away_goals if row else None,
            "penalty_winner": row.penalty_winner if row else None,
            "winner_id": winner_id,
            "winner_name": names.get(winner_id) if winner_id else None,
        }

    # El orden importa: cada ronda debe resolverse después de la anterior para que
    # los WINNER_OF_TIE encuentren al ganador ya calculado.
    knockout = {
        "round_of_32": [tie_state(t) for t in brk.ROUND_OF_32],
        "round_of_16": [tie_state(t) for t in brk.ROUND_OF_16],
        "quarter_finals": [tie_state(t) for t in brk.QUARTER_FINALS],
        "semi_finals": [tie_state(t) for t in brk.SEMI_FINALS],
        "final": tie_state(brk.FINAL),
    }
    champion_id = winners.get(brk.FINAL.id)
    return {
        "groups_complete": all_complete,
        "groups": groups_out,
        "knockout": knockout,
        "champion": ({"team_id": champion_id, "name": names.get(champion_id, champion_id)} if champion_id else None),
    }


def tie_is_playable(state: dict, tie_id: int) -> bool:
    """Busca una tie en el estado ya calculado y dice si admite carga de marcador."""
    ko = state["knockout"]
    for tie in [*ko["round_of_32"], *ko["round_of_16"], *ko["quarter_finals"], *ko["semi_finals"], ko["final"]]:
        if tie["tie_id"] == tie_id:
            return bool(tie["playable"])
    return False
