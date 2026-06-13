"""Escalera de modelos + selector final. Port de Predictors/*.

Cada predictor recibe un MatchContext y devuelve una MatchPrediction. El selector
final elige el escalón usable más alto y aplica una calibración Elo/FIFA cuando
ambos rankings coinciden contra el modelo elegido.

Niveles (prioridad):
  0 NullModel               probabilidad uniforme
  1 FifaRankingModel        puntos FIFA
  2 EloModel                rating Elo
  3 RecentFormModel         Elo + forma reciente
  4 GoalModel               Poisson de goles (ataque/defensa ajustados por rival)
  5 GoalPlusRecentContext   modelo de goles + disponibilidad de jugadores
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional, Protocol

from . import probability as prob
from .probability import OutcomeProbabilities, ScorelineDistribution


# --------------------------------------------------------------------------- #
# Estructuras de contexto y predicción (port de Models/MatchContext, MatchPrediction)
# --------------------------------------------------------------------------- #
@dataclass
class TeamRef:
    id: str
    name: str


@dataclass
class ResultRef:
    home_team_id: str
    away_team_id: str
    home_goals: int
    away_goals: int
    date: object  # datetime


@dataclass
class ContextSignals:
    unavailable_home_players: int = 0
    unavailable_away_players: int = 0
    unavailable_home_attack_impact: float = 0.0
    unavailable_home_defense_impact: float = 0.0
    unavailable_away_attack_impact: float = 0.0
    unavailable_away_defense_impact: float = 0.0
    has_lineups: bool = False
    has_odds: bool = False
    has_availability_news: bool = False


@dataclass
class MatchContext:
    fixture_id: str
    home_team: TeamRef
    away_team: TeamRef
    neutral_venue: bool = True
    home_elo: Optional[float] = None
    away_elo: Optional[float] = None
    home_fifa: Optional[float] = None
    away_fifa: Optional[float] = None
    home_recent: list[ResultRef] = field(default_factory=list)
    away_recent: list[ResultRef] = field(default_factory=list)
    fixture_context: Optional[ContextSignals] = None

    @property
    def home_team_id(self) -> str:
        return self.home_team.id

    @property
    def away_team_id(self) -> str:
        return self.away_team.id


@dataclass
class MatchPrediction:
    predictor_name: str
    predictor_priority: int
    fixture_id: str
    home_team_id: str
    away_team_id: str
    outcome: OutcomeProbabilities = field(default_factory=OutcomeProbabilities.uniform)
    expected_home_goals: Optional[float] = None
    expected_away_goals: Optional[float] = None
    scoreline: Optional[ScorelineDistribution] = None
    most_likely_score: Optional[tuple[int, int]] = None
    explanation: str = ""
    drivers: list[str] = field(default_factory=list)
    features_used: list[str] = field(default_factory=list)
    features_missing: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    degraded: bool = False


class Predictor(Protocol):
    name: str
    priority: int

    def predict(self, context: MatchContext) -> MatchPrediction: ...


# --------------------------------------------------------------------------- #
# 0 — NullModel
# --------------------------------------------------------------------------- #
class NullModel:
    name = "Modelo base"
    priority = 0

    def predict(self, ctx: MatchContext) -> MatchPrediction:
        return MatchPrediction(
            predictor_name=self.name,
            predictor_priority=self.priority,
            fixture_id=ctx.fixture_id,
            home_team_id=ctx.home_team_id,
            away_team_id=ctx.away_team_id,
            outcome=OutcomeProbabilities.uniform(),
            explanation="Probabilidad uniforme sin señales adicionales.",
            degraded=False,
        )


# --------------------------------------------------------------------------- #
# 1 — FifaRankingModel
# --------------------------------------------------------------------------- #
class FifaRankingModel:
    name = "Ranking FIFA"
    priority = 1

    def predict(self, ctx: MatchContext) -> MatchPrediction:
        if ctx.home_fifa is None or ctx.away_fifa is None:
            return MatchPrediction(
                self.name, self.priority, ctx.fixture_id, ctx.home_team_id, ctx.away_team_id,
                outcome=OutcomeProbabilities.uniform(),
                explanation="Faltan datos de ranking FIFA para uno o ambos equipos.",
                degraded=True,
            )
        diff = ctx.home_fifa - ctx.away_fifa
        expected = prob.elo_expectation(ctx.home_fifa, ctx.away_fifa)
        outcome = prob.outcome_from_expectation(expected, diff)
        return MatchPrediction(
            self.name, self.priority, ctx.fixture_id, ctx.home_team_id, ctx.away_team_id,
            outcome=outcome,
            explanation=f"Basado en puntos de ranking FIFA: {ctx.home_team.name} {ctx.home_fifa:.0f}, "
                        f"{ctx.away_team.name} {ctx.away_fifa:.0f}.",
            drivers=[f"Diferencia de puntos FIFA: {diff:+.0f}"],
            features_used=["Puntos FIFA del equipo A", "Puntos FIFA del equipo B"],
            sources=["fifa_rankings"],
            degraded=False,
        )


# --------------------------------------------------------------------------- #
# 2 — EloModel
# --------------------------------------------------------------------------- #
class EloModel:
    name = "Elo"
    priority = 2

    def predict(self, ctx: MatchContext) -> MatchPrediction:
        if ctx.home_elo is None or ctx.away_elo is None:
            return MatchPrediction(
                self.name, self.priority, ctx.fixture_id, ctx.home_team_id, ctx.away_team_id,
                outcome=OutcomeProbabilities.uniform(),
                explanation="Faltan ratings Elo para uno o ambos equipos.",
                degraded=True,
            )
        expected = prob.elo_expectation(ctx.home_elo, ctx.away_elo)
        diff = ctx.home_elo - ctx.away_elo
        outcome = prob.outcome_from_expectation(expected, diff)
        return MatchPrediction(
            self.name, self.priority, ctx.fixture_id, ctx.home_team_id, ctx.away_team_id,
            outcome=outcome,
            explanation=f"Basado en Elo {ctx.home_elo:.0f} para {ctx.home_team.name} "
                        f"y {ctx.away_elo:.0f} para {ctx.away_team.name}.",
            drivers=[f"Diferencia Elo: {diff:+.0f}"],
            features_used=["Elo del equipo A", "Elo del equipo B"],
            sources=["elo_ratings"],
            degraded=False,
        )


# --------------------------------------------------------------------------- #
# 3 — RecentFormModel
# --------------------------------------------------------------------------- #
class RecentFormModel:
    name = "Forma reciente"
    priority = 3

    def predict(self, ctx: MatchContext) -> MatchPrediction:
        if ctx.home_elo is None or ctx.away_elo is None:
            return MatchPrediction(
                self.name, self.priority, ctx.fixture_id, ctx.home_team_id, ctx.away_team_id,
                outcome=OutcomeProbabilities.uniform(),
                explanation="Se necesitan ratings Elo para ambos equipos para hacer esta predicción.",
                degraded=True,
            )
        home_delta = self.form_delta(ctx.home_recent, ctx.home_team_id)
        away_delta = self.form_delta(ctx.away_recent, ctx.away_team_id)
        home = ctx.home_elo + home_delta
        away = ctx.away_elo + away_delta
        expected = prob.elo_expectation(home, away)
        outcome = prob.outcome_from_expectation(expected, home - away)
        missing = len(ctx.home_recent) == 0 or len(ctx.away_recent) == 0
        return MatchPrediction(
            self.name, self.priority, ctx.fixture_id, ctx.home_team_id, ctx.away_team_id,
            outcome=outcome,
            explanation=f"Elo más forma reciente cuando está disponible: {ctx.home_team.name} delta {home_delta:.1f}, "
                        f"{ctx.away_team.name} delta {away_delta:.1f}.",
            drivers=["Resultados recientes"],
            features_used=["Resultados recientes", "Ratings Elo"],
            features_missing=["historial reciente para uno o ambos equipos"] if missing else [],
            sources=["elo_ratings", "historical_results"],
            degraded=missing,
        )

    @staticmethod
    def form_delta(recent: list[ResultRef], team_id: str) -> float:
        """Sesgo de recencia: pondera más los partidos recientes, mirando puntos y
        diferencia de gol. Decaimiento exponencial 0.8 por partido hacia atrás."""
        delta = 0.0
        weight = 1.0
        for m in sorted(recent, key=lambda r: r.date, reverse=True):
            goals_for = m.home_goals if m.home_team_id == team_id else m.away_goals
            goals_against = m.away_goals if m.home_team_id == team_id else m.home_goals
            points = 3 if goals_for > goals_against else 1 if goals_for == goals_against else 0
            gd = max(-3, min(3, goals_for - goals_against))
            delta += weight * ((points - 0.2) * 18 + gd * 8)
            weight *= 0.8
        return max(-100.0, min(100.0, delta))


# --------------------------------------------------------------------------- #
# 4 — GoalModel  (Poisson de goles con fuerzas ajustadas por rival)
# --------------------------------------------------------------------------- #
@dataclass
class GoalStrength:
    attack: float = 1.0
    defense_vulnerability: float = 1.0
    matches: int = 0


class GoalModel:
    name = "Modelo de goles (Poisson)"
    priority = 4

    DEFAULT_AVERAGE_GOALS = 1.25
    PRIOR_MATCHES = 2.0
    GOAL_SCALE = 1.10
    LOW_SCORE_RHO = -0.03
    HOME_ADVANTAGE_MULTIPLIER = 1.08
    MINIMUM_TEAM_MATCHES = 3
    ITERATIONS = 8

    def __init__(self, results: list[ResultRef], years_window: int = 8):
        self.years_window = years_window
        self.strengths, self.avg_goals, self.matches_used = self._fit(results, years_window)

    def expected_goals(self, ctx: MatchContext) -> tuple[float, float, bool]:
        home = self.strengths.get(ctx.home_team_id)
        away = self.strengths.get(ctx.away_team_id)
        has_home = home is not None
        has_away = away is not None
        home = home or GoalStrength()
        away = away or GoalStrength()
        degraded = (
            not has_home or not has_away
            or home.matches < self.MINIMUM_TEAM_MATCHES
            or away.matches < self.MINIMUM_TEAM_MATCHES
        )
        home_goals = self.avg_goals * home.attack * away.defense_vulnerability * self.GOAL_SCALE
        away_goals = self.avg_goals * away.attack * home.defense_vulnerability * self.GOAL_SCALE
        if not ctx.neutral_venue:
            home_goals *= self.HOME_ADVANTAGE_MULTIPLIER
        return (
            max(0.1, min(5.5, home_goals)),
            max(0.1, min(5.5, away_goals)),
            degraded,
        )

    def build_scoreline(self, home_goals: float, away_goals: float) -> ScorelineDistribution:
        return prob.poisson_scoreline(home_goals, away_goals, low_score_rho=self.LOW_SCORE_RHO)

    def predict(self, ctx: MatchContext) -> MatchPrediction:
        home_goals, away_goals, degraded = self.expected_goals(ctx)
        scoreline = self.build_scoreline(home_goals, away_goals)
        most_likely = scoreline.most_likely_scoreline()
        return MatchPrediction(
            self.name, self.priority, ctx.fixture_id, ctx.home_team_id, ctx.away_team_id,
            outcome=scoreline.to_outcome(),
            expected_home_goals=round(home_goals, 2),
            expected_away_goals=round(away_goals, 2),
            scoreline=scoreline,
            most_likely_score=most_likely,
            explanation=f"Goles esperados: {ctx.home_team.name} {home_goals:.2f} - {away_goals:.2f} "
                        f"{ctx.away_team.name}, ajustado con {self.matches_used} resultados históricos "
                        f"en una ventana de {self.years_window} años.",
            drivers=[f"Marcador más probable: {most_likely[0]}-{most_likely[1]}"],
            features_used=[
                "Fuerza de ataque ajustada por rival",
                "Vulnerabilidad defensiva ajustada por rival",
                "Grilla de marcadores Dixon-Coles",
            ],
            features_missing=["historial de goles suficiente para ambos equipos"] if degraded else [],
            sources=["historical_results"],
            degraded=degraded,
        )

    @classmethod
    def _fit(cls, results: list[ResultRef], years_window: int):
        if not results:
            return {}, cls.DEFAULT_AVERAGE_GOALS, 0

        latest = max(r.date for r in results)
        if years_window > 0:
            cutoff = latest.replace(year=latest.year - years_window)
            window = [r for r in results if r.date >= cutoff]
        else:
            window = list(results)
        if not window:
            window = list(results)

        teams = sorted({t for r in window for t in (r.home_team_id, r.away_team_id)})
        attacks = {t: 1.0 for t in teams}
        vulnerabilities = {t: 1.0 for t in teams}
        matches = {t: 0 for t in teams}
        for r in window:
            matches[r.home_team_id] += 1
            matches[r.away_team_id] += 1

        weighted: list[tuple[ResultRef, float]] = []
        for r in window:
            years_ago = max(0.0, (latest - r.date).days / 365.25)
            weighted.append((r, math.pow(0.75, years_ago)))

        total_weight = sum(w for _, w in weighted)
        if total_weight <= 0:
            avg = cls.DEFAULT_AVERAGE_GOALS
        else:
            avg = sum(w * (r.home_goals + r.away_goals) for r, w in weighted) / (2.0 * total_weight)
        avg = max(0.6, min(2.4, avg))

        def shrink(value: float, weight: float) -> float:
            return max(0.45, min(2.25, ((value * weight) + cls.PRIOR_MATCHES) / (weight + cls.PRIOR_MATCHES)))

        def normalize_mean(values: dict[str, float]) -> None:
            if not values:
                return
            mean = sum(values.values()) / len(values)
            if mean <= 0:
                return
            for k in values:
                values[k] /= mean

        for _ in range(cls.ITERATIONS):
            next_attacks: dict[str, float] = {}
            next_vuln: dict[str, float] = {}
            for team in teams:
                goals_for = attack_expected = goals_against = defense_expected = team_weight = 0.0
                for r, w in weighted:
                    if r.home_team_id == team:
                        goals_for += w * r.home_goals
                        attack_expected += w * avg * vulnerabilities[r.away_team_id]
                        goals_against += w * r.away_goals
                        defense_expected += w * avg * attacks[r.away_team_id]
                        team_weight += w
                    elif r.away_team_id == team:
                        goals_for += w * r.away_goals
                        attack_expected += w * avg * vulnerabilities[r.home_team_id]
                        goals_against += w * r.home_goals
                        defense_expected += w * avg * attacks[r.home_team_id]
                        team_weight += w
                raw_attack = 1.0 if attack_expected <= 0 else goals_for / attack_expected
                raw_vuln = 1.0 if defense_expected <= 0 else goals_against / defense_expected
                next_attacks[team] = shrink(raw_attack, team_weight)
                next_vuln[team] = shrink(raw_vuln, team_weight)
            normalize_mean(next_attacks)
            normalize_mean(next_vuln)
            attacks, vulnerabilities = next_attacks, next_vuln

        strengths = {
            t: GoalStrength(
                attack=max(0.45, min(2.25, attacks[t])),
                defense_vulnerability=max(0.45, min(2.25, vulnerabilities[t])),
                matches=matches[t],
            )
            for t in teams
        }
        return strengths, avg, len(window)


# --------------------------------------------------------------------------- #
# 5 — GoalPlusRecentContextModel
# --------------------------------------------------------------------------- #
class GoalPlusRecentContextModel:
    name = "Goles + contexto reciente"
    priority = 5

    def __init__(self, goal_model: GoalModel):
        self._goal_model = goal_model

    def predict(self, ctx: MatchContext) -> MatchPrediction:
        home_goals, away_goals, degraded_goal = self._goal_model.expected_goals(ctx)
        used = ["Modelo de goles"]
        missing: list[str] = []
        drivers: list[str] = []
        applied = False
        if degraded_goal:
            missing.append("datos requeridos por el modelo de goles")

        c = ctx.fixture_context
        if c is not None:
            role_aware = (
                c.unavailable_home_attack_impact > 0 or c.unavailable_home_defense_impact > 0
                or c.unavailable_away_attack_impact > 0 or c.unavailable_away_defense_impact > 0
            )
            if role_aware:
                home_goals *= max(0.82, 1.0 - c.unavailable_home_attack_impact)
                away_goals *= max(0.82, 1.0 - c.unavailable_away_attack_impact)
                home_goals *= 1.0 + c.unavailable_away_defense_impact
                away_goals *= 1.0 + c.unavailable_home_defense_impact
                used.append("Disponibilidad de jugadores")
                drivers.append("Impacto por rol aplicado según bajas.")
                applied = True
            elif c.unavailable_home_players > 0 or c.unavailable_away_players > 0:
                home_goals *= max(0.86, 1.0 - c.unavailable_home_players * 0.02)
                away_goals *= max(0.86, 1.0 - c.unavailable_away_players * 0.02)
                used.append("Disponibilidad de jugadores")
                drivers.append(
                    f"Bajas: equipo A {c.unavailable_home_players}, equipo B {c.unavailable_away_players}."
                )
                applied = True
            else:
                missing.append("disponibilidad de jugadores con impacto")
            missing.append("modelo de impacto de alineaciones" if c.has_lineups else "alineaciones")
            missing.append("calibración por cuotas" if c.has_odds else "cuotas")
        else:
            missing.extend(["disponibilidad de jugadores", "alineaciones", "cuotas"])

        scoreline = self._goal_model.build_scoreline(home_goals, away_goals)
        used.extend([
            "Fuerza de ataque ajustada por rival",
            "Vulnerabilidad defensiva ajustada por rival",
            "Grilla de marcadores Dixon-Coles",
        ])
        degraded = degraded_goal or not applied
        sources = ["historical_results", "api_football"]
        if c is not None and c.has_availability_news:
            sources.append("availability_news")

        return MatchPrediction(
            self.name, self.priority, ctx.fixture_id, ctx.home_team_id, ctx.away_team_id,
            outcome=scoreline.to_outcome(),
            expected_home_goals=round(home_goals, 2),
            expected_away_goals=round(away_goals, 2),
            scoreline=scoreline,
            most_likely_score=scoreline.most_likely_scoreline(),
            explanation=(
                f"Modelo de goles ajustado con contexto. Goles esperados: {ctx.home_team.name} "
                f"{home_goals:.2f} - {away_goals:.2f} {ctx.away_team.name}."
                if applied else
                f"Ningún contexto modificó el modelo de goles. Goles esperados: {ctx.home_team.name} "
                f"{home_goals:.2f} - {away_goals:.2f} {ctx.away_team.name}."
            ),
            drivers=drivers or ["No se aplicó ajuste de contexto"],
            features_used=used,
            features_missing=missing,
            sources=sources,
            degraded=degraded,
        )


# --------------------------------------------------------------------------- #
# Selector final  (port de FinalPredictionSelector)
# --------------------------------------------------------------------------- #
RANKING_BIAS_WEIGHT = 0.15


def select_final(ladder: list[MatchPrediction]) -> MatchPrediction:
    if not ladder:
        return MatchPrediction(
            "Oráculo final", 0, "", "", "",
            outcome=OutcomeProbabilities.uniform(),
            explanation="El Oráculo final no tenía predicciones de la escalera, así que devolvió la base.",
            drivers=["No había predicciones disponibles en la escalera."],
            features_missing=["predicciones de la escalera"],
            sources=["model ladder"],
            degraded=True,
        )

    ordered = sorted(ladder, key=lambda p: p.predictor_priority)
    usable = [p for p in ordered if not p.degraded]
    selected = usable[-1] if usable else ordered[0]
    skipped_higher = sorted(
        [p for p in ordered if p.predictor_priority > selected.predictor_priority and p.degraded],
        key=lambda p: p.predictor_priority, reverse=True,
    )

    outcome = selected.outcome
    bias_note = None
    elo = next((p for p in reversed(ordered) if p.predictor_name == "Elo" and not p.degraded), None)
    fifa = next((p for p in reversed(ordered) if p.predictor_name == "Ranking FIFA" and not p.degraded), None)
    if elo and fifa:
        consensus_pick = elo.outcome.top_pick
        if consensus_pick == fifa.outcome.top_pick and consensus_pick != selected.outcome.top_pick:
            consensus = OutcomeProbabilities(
                (elo.outcome.home_win + fifa.outcome.home_win) / 2,
                (elo.outcome.draw + fifa.outcome.draw) / 2,
                (elo.outcome.away_win + fifa.outcome.away_win) / 2,
            ).normalize()
            sw = 1.0 - RANKING_BIAS_WEIGHT
            outcome = OutcomeProbabilities(
                selected.outcome.home_win * sw + consensus.home_win * RANKING_BIAS_WEIGHT,
                selected.outcome.draw * sw + consensus.draw * RANKING_BIAS_WEIGHT,
                selected.outcome.away_win * sw + consensus.away_win * RANKING_BIAS_WEIGHT,
            ).normalize()
            bias_note = consensus_pick

    drivers = [f"Seleccionó {selected.predictor_name} como el escalón usable más alto."]
    drivers += [f"Omitió {p.predictor_name}: {_reason(p)}" for p in skipped_higher]
    drivers += selected.drivers
    if bias_note:
        drivers.append(
            f"Aplicó una calibración Elo/FIFA del {RANKING_BIAS_WEIGHT:.0%} porque ambos rankings "
            f"coincidieron contra {selected.predictor_name}."
        )

    return MatchPrediction(
        predictor_name="Oráculo final",
        predictor_priority=selected.predictor_priority,
        fixture_id=selected.fixture_id,
        home_team_id=selected.home_team_id,
        away_team_id=selected.away_team_id,
        outcome=outcome,
        expected_home_goals=selected.expected_home_goals,
        expected_away_goals=selected.expected_away_goals,
        scoreline=selected.scoreline,
        most_likely_score=selected.most_likely_score,
        explanation=_build_explanation(selected, skipped_higher, bias_note),
        drivers=drivers,
        features_used=list(selected.features_used),
        features_missing=list(selected.features_missing),
        sources=list(dict.fromkeys(selected.sources + ["model ladder"])),
        degraded=selected.degraded,
    )


def _reason(p: MatchPrediction) -> str:
    if not p.features_missing:
        return "no era usable"
    verb = "faltaba" if len(p.features_missing) == 1 else "faltaban"
    return f"no era usable: {verb} {', '.join(p.features_missing)}"


def _build_explanation(selected, skipped_higher, bias_note) -> str:
    bias = f" Aplicó una calibración Elo/FIFA del {RANKING_BIAS_WEIGHT:.0%}." if bias_note else ""
    if not skipped_higher:
        return f"El Oráculo final seleccionó {selected.predictor_name}, el escalón usable más alto. " \
               f"{selected.explanation}{bias}"
    skipped = "; ".join(f"{p.predictor_name} {_reason(p)}" for p in skipped_higher)
    return f"El Oráculo final seleccionó {selected.predictor_name} porque {skipped}. " \
           f"{selected.explanation}{bias}"


def build_ladder(results: list[ResultRef], years_window: int) -> list[Predictor]:
    """Construye la escalera completa. El GoalModel se entrena una vez y se reusa."""
    goal = GoalModel(results, years_window)
    return [
        NullModel(),
        FifaRankingModel(),
        EloModel(),
        RecentFormModel(),
        goal,
        GoalPlusRecentContextModel(goal),
    ]
