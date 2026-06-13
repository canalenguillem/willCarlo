"""Núcleo matemático de WillCarlo.

Port fiel de Oloraculo.Web/Probability/* (ProbabilityHelper, ScorelineDistribution,
OutcomeProbabilities). Mantiene las mismas constantes y fórmulas que la versión .NET
para que las predicciones sean equivalentes.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass


# --------------------------------------------------------------------------- #
# OutcomeProbabilities  (1X2)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class OutcomeProbabilities:
    home_win: float
    draw: float
    away_win: float

    @staticmethod
    def uniform() -> "OutcomeProbabilities":
        return OutcomeProbabilities(1 / 3, 1 / 3, 1 / 3)

    @property
    def total(self) -> float:
        return self.home_win + self.draw + self.away_win

    @property
    def top_pick(self) -> str:
        if self.home_win >= self.draw and self.home_win >= self.away_win:
            return "Home"
        if self.draw >= self.home_win and self.draw >= self.away_win:
            return "Draw"
        return "Away"

    @property
    def is_valid(self) -> bool:
        t = self.total
        return (
            self.home_win >= 0
            and self.draw >= 0
            and self.away_win >= 0
            and t > 0
            and not math.isnan(t)
            and not math.isinf(t)
        )

    def normalize(self) -> "OutcomeProbabilities":
        t = self.total
        if t <= 0 or math.isnan(t) or math.isinf(t):
            return OutcomeProbabilities.uniform()
        return OutcomeProbabilities(self.home_win / t, self.draw / t, self.away_win / t)

    def as_dict(self) -> dict:
        return {"home_win": self.home_win, "draw": self.draw, "away_win": self.away_win}


# --------------------------------------------------------------------------- #
# ScorelineDistribution  (grilla de marcadores)
# --------------------------------------------------------------------------- #
@dataclass
class ScorelineDistribution:
    max_goals: int
    matrix: list[list[float]]

    def probability(self, home: int, away: int) -> float:
        if home <= self.max_goals and away <= self.max_goals:
            return self.matrix[home][away]
        return 0.0

    def to_outcome(self) -> OutcomeProbabilities:
        home_win = draw = away_win = 0.0
        for h in range(self.max_goals + 1):
            for a in range(self.max_goals + 1):
                p = self.matrix[h][a]
                if h > a:
                    home_win += p
                elif h == a:
                    draw += p
                else:
                    away_win += p
        return OutcomeProbabilities(home_win, draw, away_win).normalize()

    def most_likely_scoreline(self) -> tuple[int, int]:
        best = (0, 0, -1.0)
        for h in range(self.max_goals + 1):
            for a in range(self.max_goals + 1):
                if self.matrix[h][a] > best[2]:
                    best = (h, a, self.matrix[h][a])
        return best[0], best[1]


# --------------------------------------------------------------------------- #
# Helpers (port de ProbabilityHelper)
# --------------------------------------------------------------------------- #
def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def elo_expectation(a: float, b: float) -> float:
    """Probabilidad esperada de que A le gane a B según puntos Elo/FIFA."""
    return 1.0 / (1.0 + math.pow(10, (b - a) / 400.0))


def outcome_from_expectation(expected_home: float, strength_gap: float) -> OutcomeProbabilities:
    """Convierte una expectativa Elo en probabilidades 1X2 con probabilidad de
    empate que decae cuanto mayor es la brecha de fuerza."""
    closeness_gap = abs(strength_gap)
    draw_probability = 0.30 * math.exp(-closeness_gap / 550.0) + 0.08
    draw_probability = _clamp(draw_probability, 0.08, 0.34)
    remaining = 1.0 - draw_probability
    return OutcomeProbabilities(
        expected_home * remaining,
        draw_probability,
        remaining * (1.0 - expected_home),
    ).normalize()


def _poisson(lam: float, k: int) -> float:
    factorial = 1.0
    for i in range(2, k + 1):
        factorial *= i
    return math.pow(lam, k) * math.exp(-lam) / factorial


def _dixon_coles_tau(home_goals: int, away_goals: int, lam_home: float, lam_away: float, rho: float) -> float:
    """Ajuste tau de Dixon-Coles (1997) para resultados de pocos goles."""
    if (home_goals, away_goals) == (0, 0):
        return 1.0 - lam_home * lam_away * rho
    if (home_goals, away_goals) == (0, 1):
        return 1.0 + lam_home * rho
    if (home_goals, away_goals) == (1, 0):
        return 1.0 + lam_away * rho
    if (home_goals, away_goals) == (1, 1):
        return 1.0 - rho
    return 1.0


def poisson_scoreline(
    lam_home: float,
    lam_away: float,
    max_goals: int = 8,
    low_score_rho: float = -0.06,
) -> ScorelineDistribution:
    """Grilla de probabilidades de marcador (Poisson independiente + tau Dixon-Coles)."""
    lam_home = _clamp(lam_home, 0.05, 6.0)
    lam_away = _clamp(lam_away, 0.05, 6.0)
    matrix = [[0.0] * (max_goals + 1) for _ in range(max_goals + 1)]
    total = 0.0
    for h in range(max_goals + 1):
        for a in range(max_goals + 1):
            p = _poisson(lam_home, h) * _poisson(lam_away, a) * _dixon_coles_tau(
                h, a, lam_home, lam_away, low_score_rho
            )
            p = max(p, 0.0)
            matrix[h][a] = p
            total += p
    if total > 0:
        for h in range(max_goals + 1):
            for a in range(max_goals + 1):
                matrix[h][a] /= total
    return ScorelineDistribution(max_goals=max_goals, matrix=matrix)


def sample_score(distribution: ScorelineDistribution, rng: random.Random) -> tuple[int, int]:
    """Muestrea un marcador concreto desde la grilla acumulada."""
    roll = rng.random()
    cumulative = 0.0
    for h in range(distribution.max_goals + 1):
        for a in range(distribution.max_goals + 1):
            cumulative += distribution.probability(h, a)
            if roll <= cumulative:
                return h, a
    return distribution.most_likely_scoreline()


# --------------------------------------------------------------------------- #
# Métricas de evaluación
# --------------------------------------------------------------------------- #
def brier_score(p: OutcomeProbabilities, actual: str) -> float:
    h = 1 if actual == "Home" else 0
    d = 1 if actual == "Draw" else 0
    a = 1 if actual == "Away" else 0
    return (p.home_win - h) ** 2 + (p.draw - d) ** 2 + (p.away_win - a) ** 2


def ranked_probability_score(p: OutcomeProbabilities, actual: str) -> float:
    o1 = 1 if actual == "Home" else 0
    o2 = 1 if actual in ("Home", "Draw") else 0
    p1 = p.home_win
    p2 = p.home_win + p.draw
    return ((p1 - o1) ** 2 + (p2 - o2) ** 2) / 2.0


def log_loss(p: OutcomeProbabilities, actual: str) -> float:
    probability = {"Home": p.home_win, "Draw": p.draw}.get(actual, p.away_win)
    return -math.log(_clamp(probability, 0.001, 0.999))
