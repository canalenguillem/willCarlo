"""Carga datos de la base y arma los contextos que consumen los predictores.

Equivale a la parte de PredictionService/SimulationPredictionContext que lee de EF
Core: ratings más recientes por equipo, resultados recientes y la escalera entrenada.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from .config import settings
from .models import Group, MatchResult, Rating, RatingType, Team
from .predictors import ResultRef, build_ladder
from .simulation import SimulationInput, SimulationPredictionContext


def _to_result_ref(r: MatchResult) -> ResultRef:
    return ResultRef(r.home_team_id, r.away_team_id, r.home_goals, r.away_goals, r.date)


def load_all_results(db: Session) -> list[ResultRef]:
    return [_to_result_ref(r) for r in db.query(MatchResult).all()]


def latest_ratings(db: Session, rating_type: RatingType) -> dict[str, float]:
    """Último valor por equipo para un tipo de rating (mayor as_of gana)."""
    rows = db.query(Rating).filter(Rating.type == rating_type).order_by(Rating.as_of).all()
    out: dict[str, float] = {}
    for r in rows:
        out[r.team_id] = r.value  # el orden ascendente deja el más reciente al final
    return out


def recent_results_by_team(db: Session, n: int) -> dict[str, list[ResultRef]]:
    by_team: dict[str, list[MatchResult]] = {}
    for r in db.query(MatchResult).order_by(MatchResult.date.desc()).all():
        by_team.setdefault(r.home_team_id, []).append(r)
        by_team.setdefault(r.away_team_id, []).append(r)
    return {tid: [_to_result_ref(x) for x in rows[:n]] for tid, rows in by_team.items()}


def team_names(db: Session) -> dict[str, str]:
    return {t.id: t.name for t in db.query(Team).all()}


def build_prediction_context(db: Session) -> SimulationPredictionContext:
    """Arma la escalera entrenada una sola vez para predecir cualquier par en cancha
    neutral (mismo contexto que usa el Montecarlo). Reutilizable para pronosticar
    todos los fixtures sin recomputar la escalera por partido."""
    teams = team_names(db)
    elo = latest_ratings(db, RatingType.Elo)
    fifa = latest_ratings(db, RatingType.Fifa)
    recent = recent_results_by_team(db, settings.recent_result_count)
    results = load_all_results(db)
    ladder = build_ladder(results, settings.goal_model_years_window)
    return SimulationPredictionContext(teams, elo, fifa, recent, ladder)


def build_simulation_input(db: Session) -> SimulationInput:
    teams = team_names(db)
    elo = latest_ratings(db, RatingType.Elo)
    fifa = latest_ratings(db, RatingType.Fifa)
    recent = recent_results_by_team(db, settings.recent_result_count)
    results = load_all_results(db)
    ladder = build_ladder(results, settings.goal_model_years_window)
    context = SimulationPredictionContext(teams, elo, fifa, recent, ladder)

    groups = [(g.name, list(g.team_ids)) for g in db.query(Group).order_by(Group.name).all()]

    known: dict[tuple[str, str, str], tuple[int, int]] = {}
    from .models import Fixture  # local import to avoid cycle at module load
    for f in db.query(Fixture).filter(Fixture.is_played.is_(True)).all():
        if f.home_goals is not None and f.away_goals is not None:
            known[(f.group, f.home_team_id, f.away_team_id)] = (f.home_goals, f.away_goals)

    # Ganadores de eliminación ya definidos (para fijarlos en la simulación).
    from . import real_bracket  # local import: real_bracket -> simulation, no ciclo
    state = real_bracket.real_bracket_state(db, fifa, teams)
    known_knockout: dict[int, str] = {}
    for value in state["knockout"].values():
        ties = value if isinstance(value, list) else [value]
        for t in ties:
            if t["winner_id"]:
                known_knockout[t["tie_id"]] = t["winner_id"]

    return SimulationInput(
        groups=groups,
        fifa_points=fifa,
        known_group_scores=known,
        context=context,
        known_knockout=known_knockout,
    )
