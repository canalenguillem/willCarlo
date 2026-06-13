"""Modelos ORM (SQLAlchemy / MariaDB). Port de Models/* + DAL/OloraculoDbContext.cs.

El esquema sigue al de EF Core. La lista de team_ids de un grupo se guarda como
JSON (igual que la conversión a JSON del DbContext original).
"""
from __future__ import annotations

import datetime as dt
import enum

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    Float,
    Integer,
    String,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from .config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, future=True)


class Base(DeclarativeBase):
    pass


class RatingType(str, enum.Enum):
    Fifa = "Fifa"
    Elo = "Elo"


class Team(Base):
    __tablename__ = "teams"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    source: Mapped[str | None] = mapped_column(String(128), nullable=True)


class Group(Base):
    __tablename__ = "groups"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(8), unique=True, index=True)
    team_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    source: Mapped[str | None] = mapped_column(String(128), nullable=True)


class Fixture(Base):
    __tablename__ = "fixtures"
    id: Mapped[str] = mapped_column(String(160), primary_key=True)
    group: Mapped[str] = mapped_column(String(8), default="", index=True)
    home_team_id: Mapped[str] = mapped_column(String(64))
    away_team_id: Mapped[str] = mapped_column(String(64))
    kickoff_utc: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    venue: Mapped[str | None] = mapped_column(String(128), nullable=True)
    city: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    neutral_venue: Mapped[bool] = mapped_column(Boolean, default=True)
    is_played: Mapped[bool] = mapped_column(Boolean, default=False)
    home_goals: Mapped[int | None] = mapped_column(Integer, nullable=True)
    away_goals: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source: Mapped[str] = mapped_column(String(128), default="derived")

    @staticmethod
    def generate_id(group: str, home_team_id: str, away_team_id: str) -> str:
        return f"grp:{group}:{home_team_id}:{away_team_id}"


class MatchResult(Base):
    __tablename__ = "results"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    home_team_id: Mapped[str] = mapped_column(String(64), index=True)
    away_team_id: Mapped[str] = mapped_column(String(64), index=True)
    home_goals: Mapped[int] = mapped_column(Integer)
    away_goals: Mapped[int] = mapped_column(Integer)
    date: Mapped[dt.datetime] = mapped_column(DateTime, index=True)
    tournament: Mapped[str] = mapped_column(String(128), default="")
    neutral: Mapped[bool] = mapped_column(Boolean, default=False)
    source: Mapped[str] = mapped_column(String(128), default="")


class Rating(Base):
    __tablename__ = "ratings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    team_id: Mapped[str] = mapped_column(String(64), index=True)
    type: Mapped[RatingType] = mapped_column(Enum(RatingType), index=True)
    value: Mapped[float] = mapped_column(Float)
    as_of: Mapped[dt.datetime] = mapped_column(DateTime)
    source: Mapped[str] = mapped_column(String(256), default="")


class FixtureContext(Base):
    __tablename__ = "fixture_contexts"
    fixture_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    unavailable_home_players: Mapped[int] = mapped_column(Integer, default=0)
    unavailable_away_players: Mapped[int] = mapped_column(Integer, default=0)
    unavailable_home_attack_impact: Mapped[float] = mapped_column(Float, default=0.0)
    unavailable_home_defense_impact: Mapped[float] = mapped_column(Float, default=0.0)
    unavailable_away_attack_impact: Mapped[float] = mapped_column(Float, default=0.0)
    unavailable_away_defense_impact: Mapped[float] = mapped_column(Float, default=0.0)
    has_lineups: Mapped[bool] = mapped_column(Boolean, default=False)
    has_odds: Mapped[bool] = mapped_column(Boolean, default=False)
    has_availability_news: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str] = mapped_column(String(512), default="")
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)


class KnockoutResult(Base):
    __tablename__ = "knockout_results"
    tie_id: Mapped[int] = mapped_column(Integer, primary_key=True)  # 73..104, sin autoincrement
    home_goals: Mapped[int] = mapped_column(Integer)
    away_goals: Mapped[int] = mapped_column(Integer)
    penalty_winner: Mapped[str | None] = mapped_column(String(8), nullable=True)  # "home"|"away"|None


class PredictionSnapshot(Base):
    __tablename__ = "snapshots"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)  # "match" | "tournament"
    fixture_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    batch_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow, index=True)


def init_db() -> None:
    Base.metadata.create_all(engine)
