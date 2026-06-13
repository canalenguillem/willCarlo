"""Importación de datos semilla desde CSV. Port de Services/CsvImportService.cs.

Lee los 4 archivos (grupos, FIFA, Elo, resultados históricos), normaliza nombres
a ids estables, deduplica resultados y genera los fixtures round-robin de cada
grupo. Es idempotente: vuelve a poblar las tablas desde cero.
"""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import os

from sqlalchemy import delete
from sqlalchemy.orm import Session

from .config import settings
from .models import Fixture, Group, MatchResult, Rating, RatingType, Team
from .team_names import canonical_name, to_id


def _path(filename: str) -> str:
    return os.path.join(settings.data_dir, filename)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def needs_import(db: Session) -> bool:
    return (
        db.query(Group).first() is None
        or db.query(Team).first() is None
        or db.query(Fixture).first() is None
        or db.query(MatchResult).first() is None
        or db.query(Rating).first() is None
    )


def import_all(db: Session) -> dict:
    # Limpia todo y reconstruye desde los CSV. El registro evita insertar el
    # mismo equipo dos veces dentro de la misma transacción (un equipo puede
    # aparecer en grupos, ratings y resultados a la vez).
    db.execute(delete(Group))
    db.execute(delete(Rating))
    db.execute(delete(MatchResult))
    db.execute(delete(Fixture))
    db.execute(delete(Team))
    db.flush()
    seen: set[str] = set()
    _import_groups(db, seen)
    _import_ratings(db, seen)
    _import_historical_results(db, seen)
    db.flush()
    _generate_fixtures(db)
    db.commit()
    return {
        "groups": db.query(Group).count(),
        "teams": db.query(Team).count(),
        "ratings": db.query(Rating).count(),
        "results": db.query(MatchResult).count(),
        "fixtures": db.query(Fixture).count(),
    }


def _upsert_team(db: Session, seen: set[str], name: str, source: str) -> str:
    canonical = canonical_name(name)
    team_id = to_id(canonical)
    if team_id not in seen:
        db.add(Team(id=team_id, name=canonical, source=source))
        seen.add(team_id)
    return team_id


def _import_groups(db: Session, seen: set[str]) -> None:
    rows = list(_read_csv("wc2026_groups.csv"))
    grouped: dict[str, list[str]] = {}
    for row in rows:
        team_id = _upsert_team(db, seen, row["team"], "wc2026_groups.csv")
        grouped.setdefault(row["group"].strip(), []).append(team_id)
    for name in sorted(grouped):
        db.add(Group(name=name, team_ids=grouped[name], source="wc2026_groups.csv"))


def _import_ratings(db: Session, seen: set[str]) -> None:
    now = dt.datetime.utcnow()

    for row in _read_csv("elo_snapshot.csv"):
        try:
            elo = float(row["elo_rating"])
        except (ValueError, KeyError):
            continue
        team_id = _upsert_team(db, seen, row["team"], "elo_snapshot.csv")
        db.add(Rating(team_id=team_id, type=RatingType.Elo, value=elo, as_of=now, source="elo_snapshot.csv"))

    for row in _read_csv("fifa_rankings.csv"):
        try:
            points = float(row["points"])
        except (ValueError, KeyError):
            continue
        team_id = _upsert_team(db, seen, row["team"], "fifa_rankings.csv")
        db.add(Rating(team_id=team_id, type=RatingType.Fifa, value=points, as_of=now, source="fifa_rankings.csv"))


def _import_historical_results(db: Session, seen: set[str]) -> None:
    seen_results: set[str] = set()
    batch = []
    for row in _read_csv("historical_results.csv"):
        try:
            date = dt.datetime.fromisoformat(row["date"])
            home_score = int(row["home_score"])
            away_score = int(row["away_score"])
        except (ValueError, KeyError):
            continue
        home_id = to_id(row["home_team"])
        away_id = to_id(row["away_team"])
        tournament = row.get("tournament", "")
        result_id = _sha256(f"{home_id}-{away_id}-{date.isoformat()}-{tournament}-{home_score}-{away_score}")
        if result_id in seen_results:
            continue
        seen_results.add(result_id)
        _upsert_team(db, seen, row["home_team"], "historical_results.csv")
        _upsert_team(db, seen, row["away_team"], "historical_results.csv")
        batch.append(MatchResult(
            id=result_id, home_team_id=home_id, away_team_id=away_id,
            home_goals=home_score, away_goals=away_score, date=date,
            tournament=tournament, neutral=str(row.get("neutral", "")).strip().lower() == "true",
            source="historical_results.csv",
        ))
        if len(batch) >= 1000:
            db.add_all(batch)
            db.flush()
            batch = []
    if batch:
        db.add_all(batch)
        db.flush()


def _generate_fixtures(db: Session) -> None:
    groups = db.query(Group).order_by(Group.name).all()
    for group in groups:
        ids = group.team_ids
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                db.add(Fixture(
                    id=Fixture.generate_id(group.name, ids[i], ids[j]),
                    group=group.name,
                    home_team_id=ids[i],
                    away_team_id=ids[j],
                    neutral_venue=True,
                    source="derivado de wc2026_groups.csv",
                ))


def _read_csv(filename: str):
    with open(_path(filename), newline="", encoding="utf-8-sig") as fh:
        yield from csv.DictReader(fh)
