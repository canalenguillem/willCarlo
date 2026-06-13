"""API de WillCarlo (FastAPI). Refleja las pantallas del original:

  GET  /api/teams                  lista de equipos
  GET  /api/groups                 grupos del Mundial 2026
  GET  /api/matches                fixtures de fase de grupos (+ resultado si hay)
  POST /api/lab                    compara dos equipos a través de toda la escalera
  POST /api/tournament/run         corre la simulación Montecarlo
  POST /api/matches/{id}/result    carga un resultado real
  POST /api/import                 reimporta los CSV semilla
"""
from __future__ import annotations

import time

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session

from . import csv_import, real_bracket, repository
from .config import settings
from .models import (
    Fixture,
    Group,
    KnockoutResult,
    MatchResult,
    PredictionSnapshot,
    RatingType,
    SessionLocal,
    Team,
    init_db,
)
from .predictors import MatchContext, MatchPrediction, TeamRef, build_ladder, select_final

app = FastAPI(title="WillCarlo", description="Predicción del Mundial 2026", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.on_event("startup")
def startup() -> None:
    init_db()
    db = SessionLocal()
    try:
        if csv_import.needs_import(db):
            csv_import.import_all(db)
    finally:
        db.close()


# --------------------------------------------------------------------------- #
# Serialización
# --------------------------------------------------------------------------- #
def _prediction_dict(p: MatchPrediction) -> dict:
    return {
        "predictor_name": p.predictor_name,
        "predictor_priority": p.predictor_priority,
        "outcome": p.outcome.as_dict(),
        "top_pick": p.outcome.top_pick,
        "expected_home_goals": p.expected_home_goals,
        "expected_away_goals": p.expected_away_goals,
        "most_likely_score": list(p.most_likely_score) if p.most_likely_score else None,
        "explanation": p.explanation,
        "drivers": p.drivers,
        "features_used": p.features_used,
        "features_missing": p.features_missing,
        "sources": p.sources,
        "degraded": p.degraded,
    }


# --------------------------------------------------------------------------- #
# Endpoints de datos
# --------------------------------------------------------------------------- #
@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/teams")
def teams(db: Session = Depends(get_db)):
    return [
        {"id": t.id, "name": t.name}
        for t in db.query(Team).order_by(Team.name).all()
    ]


@app.get("/api/groups")
def groups(db: Session = Depends(get_db)):
    names = repository.team_names(db)
    return [
        {
            "name": g.name,
            "teams": [{"id": tid, "name": names.get(tid, tid)} for tid in g.team_ids],
        }
        for g in db.query(Group).order_by(Group.name).all()
    ]


@app.get("/api/matches")
def matches(db: Session = Depends(get_db)):
    names = repository.team_names(db)
    out = []
    # Ordenado por grupo y, dentro de cada grupo, por fecha de juego (sin fecha al final).
    fixtures_q = db.query(Fixture).order_by(
        Fixture.group, Fixture.kickoff_utc.is_(None), Fixture.kickoff_utc, Fixture.id
    )
    for f in fixtures_q.all():
        out.append({
            "id": f.id,
            "group": f.group,
            "home": {"id": f.home_team_id, "name": names.get(f.home_team_id, f.home_team_id)},
            "away": {"id": f.away_team_id, "name": names.get(f.away_team_id, f.away_team_id)},
            "is_played": f.is_played,
            "home_goals": f.home_goals,
            "away_goals": f.away_goals,
            "status": f.status,
        })
    return out


@app.get("/api/matches/predictions")
def match_predictions(db: Session = Depends(get_db)):
    """Pronóstico del oráculo (cancha neutral) para cada partido de grupos:
    probabilidades 1-X-2 y marcador/goles esperados. La escalera se arma una vez."""
    ctx = repository.build_prediction_context(db)
    out = []
    for f in db.query(Fixture).all():
        p = ctx.predict_pair(f.home_team_id, f.away_team_id)
        out.append({
            "id": f.id,
            "home_win": p.outcome.home_win,
            "draw": p.outcome.draw,
            "away_win": p.outcome.away_win,
            "expected_home_goals": p.expected_home_goals,
            "expected_away_goals": p.expected_away_goals,
            "most_likely_score": list(p.most_likely_score) if p.most_likely_score else None,
        })
    return out


# --------------------------------------------------------------------------- #
# Lab: comparar dos equipos en toda la escalera
# --------------------------------------------------------------------------- #
class LabRequest(BaseModel):
    home_id: str
    away_id: str
    neutral_venue: bool = True


@app.post("/api/lab")
def lab(req: LabRequest, db: Session = Depends(get_db)):
    names = repository.team_names(db)
    if req.home_id not in names or req.away_id not in names:
        raise HTTPException(status_code=404, detail="Equipo no encontrado.")

    elo = repository.latest_ratings(db, RatingType.Elo)
    fifa = repository.latest_ratings(db, RatingType.Fifa)
    recent = repository.recent_results_by_team(db, settings.recent_result_count)
    results = repository.load_all_results(db)
    ladder = build_ladder(results, settings.goal_model_years_window)

    ctx = MatchContext(
        fixture_id=f"lab:{req.home_id}:{req.away_id}",
        home_team=TeamRef(req.home_id, names[req.home_id]),
        away_team=TeamRef(req.away_id, names[req.away_id]),
        neutral_venue=req.neutral_venue,
        home_elo=elo.get(req.home_id),
        away_elo=elo.get(req.away_id),
        home_fifa=fifa.get(req.home_id),
        away_fifa=fifa.get(req.away_id),
        home_recent=recent.get(req.home_id, []),
        away_recent=recent.get(req.away_id, []),
    )
    predictions = [p.predict(ctx) for p in ladder]
    final = select_final(predictions)
    return {
        "home": {"id": req.home_id, "name": names[req.home_id]},
        "away": {"id": req.away_id, "name": names[req.away_id]},
        "ladder": [_prediction_dict(p) for p in predictions],
        "final": _prediction_dict(final),
    }


# --------------------------------------------------------------------------- #
# Tournament: simulación Montecarlo
# --------------------------------------------------------------------------- #
class TournamentRequest(BaseModel):
    simulations: int | None = None
    seed: int | None = None
    save_snapshot: bool = True


@app.post("/api/tournament/run")
def tournament_run(req: TournamentRequest, db: Session = Depends(get_db)):
    from .simulation import run_simulation

    n = req.simulations or settings.simulation_count
    seed = req.seed if req.seed is not None else settings.simulation_seed
    names = repository.team_names(db)

    data = repository.build_simulation_input(db)
    started = time.perf_counter()
    projection = run_simulation(data, n, seed)
    elapsed_ms = round((time.perf_counter() - started) * 1000)

    payload = {
        "simulations": n,
        "seed": seed,
        "elapsed_ms": elapsed_ms,
        "teams": [
            {
                "team_id": t.team_id,
                "name": names.get(t.team_id, t.team_id),
                "group": t.group,
                "win_group": t.win_group,
                "qualify": t.qualify,
                "reach_round_of_16": t.reach_round_of_16,
                "reach_quarter_final": t.reach_quarter_final,
                "reach_semi_final": t.reach_semi_final,
                "reach_final": t.reach_final,
                "win_tournament": t.win_tournament,
                "expected_group_points": t.expected_group_points,
            }
            for t in projection
        ],
    }

    if req.save_snapshot:
        db.add(PredictionSnapshot(kind="tournament", payload=payload))
        db.commit()
    return payload


# --------------------------------------------------------------------------- #
# Cuadro jugado: una sola corrida del torneo
# --------------------------------------------------------------------------- #
class LikelyBracketRequest(BaseModel):
    simulations: int | None = None
    seed: int | None = None


@app.post("/api/tournament/bracket/likely")
def tournament_bracket_likely(req: LikelyBracketRequest, db: Session = Depends(get_db)):
    """Cuadro más probable (no una tirada): favorito en cada llave, con su probabilidad."""
    from .simulation import most_likely_bracket

    n = req.simulations or settings.simulation_count
    data = repository.build_simulation_input(db)
    names = repository.team_names(db)
    started = time.perf_counter()
    res = most_likely_bracket(data, n, req.seed, names)
    res["elapsed_ms"] = round((time.perf_counter() - started) * 1000)
    return res


class BracketRequest(BaseModel):
    seed: int | None = None  # opcional; omitir => cuadro nuevo (aleatorio) en cada llamada


@app.post("/api/tournament/bracket")
def tournament_bracket(req: BracketRequest, db: Session = Depends(get_db)):
    """Juega un único torneo y devuelve el cuadro completo: posiciones de cada grupo
    y, por cada cruce de eliminación, equipos, marcador, ganador y si hubo penales."""
    from .simulation import simulate_one_bracket

    names = repository.team_names(db)
    data = repository.build_simulation_input(db)
    started = time.perf_counter()
    bracket = simulate_one_bracket(data, req.seed, names)
    bracket["elapsed_ms"] = round((time.perf_counter() - started) * 1000)
    return bracket


# --------------------------------------------------------------------------- #
# Cargar resultado real de un partido de grupos
# --------------------------------------------------------------------------- #
class ResultRequest(BaseModel):
    home_goals: int
    away_goals: int


@app.post("/api/matches/{fixture_id}/result")
def set_result(fixture_id: str, req: ResultRequest, db: Session = Depends(get_db)):
    fixture = db.get(Fixture, fixture_id)
    if fixture is None:
        raise HTTPException(status_code=404, detail="Partido no encontrado.")
    fixture.home_goals = req.home_goals
    fixture.away_goals = req.away_goals
    fixture.is_played = True
    db.commit()
    return {"id": fixture_id, "home_goals": req.home_goals, "away_goals": req.away_goals, "is_played": True}


# --------------------------------------------------------------------------- #
# Cuadro real: posiciones reales + eliminación cargada a mano
# --------------------------------------------------------------------------- #
def _real_bracket_state(db: Session) -> dict:
    fifa = repository.latest_ratings(db, RatingType.Fifa)
    names = repository.team_names(db)
    return real_bracket.real_bracket_state(db, fifa, names)


@app.get("/api/bracket/real")
def bracket_real(db: Session = Depends(get_db)):
    return _real_bracket_state(db)


class KnockoutResultRequest(BaseModel):
    home_goals: int
    away_goals: int
    penalty_winner: str | None = None  # "home" | "away" | None


@app.post("/api/knockout/{tie_id}/result")
def set_knockout_result(tie_id: int, req: KnockoutResultRequest, db: Session = Depends(get_db)):
    if tie_id not in real_bracket.ALL_TIES:
        raise HTTPException(status_code=404, detail="Llave inexistente en el cuadro.")
    if req.home_goals < 0 or req.away_goals < 0:
        raise HTTPException(status_code=400, detail="Los goles no pueden ser negativos.")
    if req.home_goals == req.away_goals:
        if req.penalty_winner not in ("home", "away"):
            raise HTTPException(
                status_code=400,
                detail="Empate: indicá quién gana por penales (penalty_winner = 'home' o 'away').",
            )
    elif req.penalty_winner is not None:
        raise HTTPException(status_code=400, detail="Solo hay penales cuando el marcador es empate.")

    if not real_bracket.tie_is_playable(_real_bracket_state(db), tie_id):
        raise HTTPException(
            status_code=409,
            detail="Esta llave todavía no tiene definidos ambos equipos.",
        )

    penalty_winner = req.penalty_winner if req.home_goals == req.away_goals else None
    row = db.get(KnockoutResult, tie_id)
    if row is None:
        row = KnockoutResult(tie_id=tie_id)
        db.add(row)
    row.home_goals = req.home_goals
    row.away_goals = req.away_goals
    row.penalty_winner = penalty_winner
    db.commit()
    return _real_bracket_state(db)


@app.delete("/api/knockout/{tie_id}/result")
def clear_knockout_result(tie_id: int, db: Session = Depends(get_db)):
    row = db.get(KnockoutResult, tie_id)
    if row is not None:
        db.delete(row)
        db.commit()
    return _real_bracket_state(db)


class GroupSimRequest(BaseModel):
    simulations: int | None = None
    seed: int | None = None


@app.post("/api/groups/simulate")
def groups_simulate(req: GroupSimRequest, db: Session = Depends(get_db)):
    """Montecarlo por grupo: proyecta la clasificación final fijando lo ya jugado."""
    from .simulation import simulate_group_positions

    from . import bracket as brk

    n = req.simulations or settings.simulation_count
    data = repository.build_simulation_input(db)
    names = repository.team_names(db)
    result = simulate_group_positions(data, n, req.seed, names)

    routes = brk.group_routes()  # a qué cruce de 16avos va el 1º/2º de cada grupo
    for g in result["groups"]:
        g["routes"] = routes.get(g["name"], {})
    return result


@app.post("/api/results/refresh")
def refresh_results(db: Session = Depends(get_db)):
    """Auto-carga resultados reales (finalizados + en vivo) desde la fuente pública."""
    from . import live_results

    try:
        return live_results.refresh_group_results(db)
    except Exception as e:  # red caída, fuente cambiada, timeout...
        raise HTTPException(status_code=502, detail=f"No se pudo consultar la fuente de resultados: {e}")


@app.post("/api/import")
def reimport(db: Session = Depends(get_db)):
    return csv_import.import_all(db)
