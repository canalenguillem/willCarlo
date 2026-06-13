"""Motor de simulación Montecarlo del torneo. Port de Services/Simulation/*.

Corre el torneo completo N veces (fase de grupos + eliminación con el cuadro real
de 2026) y devuelve, por equipo, la frecuencia con que gana el grupo, clasifica,
llega a cada ronda y sale campeón. Las predicciones por par de equipos se cachean
(MatchSamplerCache) para no recomputar la escalera en cada simulación.
"""
from __future__ import annotations

import random
from collections import defaultdict
from dataclasses import dataclass, field

from . import bracket as brk
from . import probability as prob
from .bracket import SlotKind
from .predictors import MatchContext, MatchPrediction, Predictor, TeamRef, select_final


# --------------------------------------------------------------------------- #
# Tabla de grupo y desempates (port de GroupTable.cs)
# --------------------------------------------------------------------------- #
@dataclass
class SimulatedMatch:
    group: str
    team_a: str
    team_b: str
    goals_a: int
    goals_b: int


@dataclass
class GroupStanding:
    group: str
    team_id: str
    points: int = 0
    goals_for: int = 0
    goals_against: int = 0

    @property
    def goal_diff(self) -> int:
        return self.goals_for - self.goals_against


class GroupTable:
    def __init__(self, name: str, team_ids: list[str], fifa_points: dict[str, float]):
        self.name = name
        self.fifa_points = fifa_points
        self.standings = {t: GroupStanding(name, t) for t in team_ids}
        self.matches: list[SimulatedMatch] = []

    def add_match(self, m: SimulatedMatch) -> None:
        self.matches.append(m)
        a, b = self.standings[m.team_a], self.standings[m.team_b]
        a.goals_for += m.goals_a
        a.goals_against += m.goals_b
        b.goals_for += m.goals_b
        b.goals_against += m.goals_a
        if m.goals_a > m.goals_b:
            a.points += 3
        elif m.goals_b > m.goals_a:
            b.points += 3
        else:
            a.points += 1
            b.points += 1

    def _fifa(self, team_id: str) -> float:
        return self.fifa_points.get(team_id, float("-inf"))

    def rank(self) -> list[GroupStanding]:
        # Agrupa por puntos, desempata dentro de cada bloque y aplana.
        by_points: dict[int, list[GroupStanding]] = defaultdict(list)
        for s in self.standings.values():
            by_points[s.points].append(s)
        ranked: list[GroupStanding] = []
        for pts in sorted(by_points.keys(), reverse=True):
            ranked.extend(self._rank_tied(by_points[pts]))
        return ranked

    def _rank_tied(self, tied: list[GroupStanding]) -> list[GroupStanding]:
        if len(tied) <= 1:
            return tied
        criteria = [
            "h2h_points", "h2h_gd", "h2h_gf",
            "overall_gd", "overall_gf", "conduct", "fifa",
        ]
        for criterion in criteria:
            blocks: dict[float, list[GroupStanding]] = defaultdict(list)
            for team in tied:
                blocks[self._criterion_value(team, tied, criterion)].append(team)
            if len(blocks) <= 1:
                continue
            out: list[GroupStanding] = []
            for key in sorted(blocks.keys(), reverse=True):
                out.extend(self._rank_tied(blocks[key]))
            return out
        return sorted(tied, key=lambda t: (-self._fifa(t.team_id), t.team_id))

    def _criterion_value(self, team, tied, criterion) -> float:
        ids = {t.team_id for t in tied}
        if criterion == "overall_gd":
            return team.goal_diff
        if criterion == "overall_gf":
            return team.goals_for
        if criterion == "conduct":
            return 0
        if criterion == "fifa":
            return self._fifa(team.team_id)
        pts, gf, ga = self._head_to_head(team.team_id, ids)
        if criterion == "h2h_points":
            return pts
        if criterion == "h2h_gd":
            return gf - ga
        if criterion == "h2h_gf":
            return gf
        return 0

    def _head_to_head(self, team_id: str, ids: set[str]) -> tuple[int, int, int]:
        points = gf = ga = 0
        for m in self.matches:
            if m.team_a not in ids or m.team_b not in ids:
                continue
            if m.team_a == team_id:
                f, a = m.goals_a, m.goals_b
            elif m.team_b == team_id:
                f, a = m.goals_b, m.goals_a
            else:
                continue
            gf += f
            ga += a
            if f > a:
                points += 3
            elif f == a:
                points += 1
        return points, gf, ga


def rank_best_thirds(thirds: list[GroupStanding], fifa_points: dict[str, float]) -> list[GroupStanding]:
    return sorted(
        thirds,
        key=lambda t: (-t.points, -t.goal_diff, -t.goals_for,
                       -fifa_points.get(t.team_id, float("-inf")), t.team_id),
    )


# --------------------------------------------------------------------------- #
# Cache de predicciones por par (port de MatchSamplerCache.cs)
# --------------------------------------------------------------------------- #
class MatchSamplerCache:
    def __init__(self, predict_pair):
        self._predict_pair = predict_pair  # (home_id, away_id) -> MatchPrediction (final)
        self._cache: dict[str, MatchPrediction] = {}

    def _get(self, home_id: str, away_id: str) -> MatchPrediction:
        key = f"{home_id}|{away_id}"
        cached = self._cache.get(key)
        if cached is None:
            cached = self._predict_pair(home_id, away_id)
            self._cache[key] = cached
        return cached

    def sample_score(self, home_id: str, away_id: str, rng: random.Random) -> tuple[int, int]:
        return self._sample_from(self._get(home_id, away_id), rng)

    def knockout_winner(self, home_id: str, away_id: str, rng: random.Random) -> str:
        final = self._get(home_id, away_id)
        score = self._sample_from(final, rng)
        if score[0] > score[1]:
            return home_id
        if score[1] > score[0]:
            return away_id
        # Empate -> definición proporcional a prob. de victoria de cada lado.
        o = final.outcome
        decisive = o.home_win + o.away_win
        p_home = o.home_win / decisive if decisive > 0 else 0.5
        return home_id if rng.random() < p_home else away_id

    def knockout_result(self, home_id: str, away_id: str, rng: random.Random) -> tuple[int, int, str, bool]:
        """Como knockout_winner, pero devuelve (goles_local, goles_visita, ganador,
        definido_por_penales). Misma lógica y secuencia de rng que knockout_winner."""
        final = self._get(home_id, away_id)
        score = self._sample_from(final, rng)
        if score[0] != score[1]:
            winner = home_id if score[0] > score[1] else away_id
            return score[0], score[1], winner, False
        o = final.outcome
        decisive = o.home_win + o.away_win
        p_home = o.home_win / decisive if decisive > 0 else 0.5
        winner = home_id if rng.random() < p_home else away_id
        return score[0], score[1], winner, True

    @staticmethod
    def _sample_from(final: MatchPrediction, rng: random.Random) -> tuple[int, int]:
        if final.scoreline is not None:
            return prob.sample_score(final.scoreline, rng)
        roll = rng.random()
        o = final.outcome
        if roll < o.home_win:
            return 1, 0
        if roll < o.home_win + o.draw:
            return 1, 1
        return 0, 1


# --------------------------------------------------------------------------- #
# Contexto de predicción de la simulación (port de SimulationPredictionContext.cs)
# --------------------------------------------------------------------------- #
class SimulationPredictionContext:
    """Mantiene equipos, ratings y resultados en memoria, y entrena la escalera una
    sola vez para predecir cualquier par de equipos en cancha neutral."""

    def __init__(self, teams, elo, fifa, recent_by_team, ladder: list[Predictor]):
        self._teams = teams                      # id -> name
        self._elo = elo                          # id -> float
        self._fifa = fifa                        # id -> float
        self._recent = recent_by_team            # id -> list[ResultRef]
        self._ladder = ladder

    def predict_pair(self, home_id: str, away_id: str) -> MatchPrediction:
        ctx = MatchContext(
            fixture_id=f"pair:{home_id}:{away_id}",
            home_team=TeamRef(home_id, self._teams.get(home_id, home_id)),
            away_team=TeamRef(away_id, self._teams.get(away_id, away_id)),
            neutral_venue=True,
            home_elo=self._elo.get(home_id),
            away_elo=self._elo.get(away_id),
            home_fifa=self._fifa.get(home_id),
            away_fifa=self._fifa.get(away_id),
            home_recent=self._recent.get(home_id, []),
            away_recent=self._recent.get(away_id, []),
            fixture_context=None,
        )
        ladder = [p.predict(ctx) for p in self._ladder]
        return select_final(ladder)


# --------------------------------------------------------------------------- #
# Resultado de la simulación
# --------------------------------------------------------------------------- #
@dataclass
class TeamTournamentProbability:
    team_id: str
    group: str
    win_group: float
    qualify: float
    reach_round_of_16: float
    reach_quarter_final: float
    reach_semi_final: float
    reach_final: float
    win_tournament: float
    expected_group_points: float


@dataclass
class _Counter:
    win_group: int = 0
    qualify: int = 0
    r16: int = 0
    qf: int = 0
    sf: int = 0
    final: int = 0
    champion: int = 0
    group_points: int = 0


# --------------------------------------------------------------------------- #
# Motor Montecarlo (port de SimulationService.RunAsync)
# --------------------------------------------------------------------------- #
@dataclass
class SimulationInput:
    groups: list[tuple[str, list[str]]]              # [(name, [team_ids])]
    fifa_points: dict[str, float]
    known_group_scores: dict[tuple[str, str, str], tuple[int, int]]  # (group,a,b)->(ga,gb)
    context: SimulationPredictionContext
    known_knockout: dict[int, str] = field(default_factory=dict)  # tie_id -> ganador real ya definido


def run_simulation(data: SimulationInput, simulations: int, seed: int | None) -> list[TeamTournamentProbability]:
    rng = random.Random(seed)
    teams = sorted({t for _, ids in data.groups for t in ids})
    counters = {t: _Counter() for t in teams}
    sampler = MatchSamplerCache(data.context.predict_pair)

    for _ in range(simulations):
        group_slots: dict[str, tuple[str, str, str]] = {}  # group -> (winner, runner_up, third)
        thirds: list[GroupStanding] = []

        for name, ids in data.groups:
            table = _simulate_group(name, ids, data, sampler, rng)
            ranked = table.rank()
            for s in ranked:
                counters[s.team_id].group_points += s.points
            counters[ranked[0].team_id].win_group += 1
            group_slots[name] = (ranked[0].team_id, ranked[1].team_id, ranked[2].team_id)
            thirds.append(ranked[2])

        best_thirds = rank_best_thirds(thirds, data.fifa_points)[:8]
        for winner, runner_up, _third in group_slots.values():
            counters[winner].qualify += 1
            counters[runner_up].qualify += 1
        for t in best_thirds:
            counters[t.team_id].qualify += 1

        third_assignments = brk.assign_third_place_groups([t.group for t in best_thirds])
        third_by_group = {t.group.upper(): t.team_id for t in best_thirds}
        _run_knockout(group_slots, third_by_group, third_assignments, sampler, rng, counters, data.known_knockout)

    group_of = {t: name for name, ids in data.groups for t in ids}
    n = float(simulations)
    out = [
        TeamTournamentProbability(
            team_id=t,
            group=group_of[t],
            win_group=counters[t].win_group / n,
            qualify=counters[t].qualify / n,
            reach_round_of_16=counters[t].r16 / n,
            reach_quarter_final=counters[t].qf / n,
            reach_semi_final=counters[t].sf / n,
            reach_final=counters[t].final / n,
            win_tournament=counters[t].champion / n,
            expected_group_points=round(counters[t].group_points / n, 2),
        )
        for t in teams
    ]
    out.sort(key=lambda x: x.win_tournament, reverse=True)
    return out


def _simulate_group(name, ids, data, sampler, rng) -> GroupTable:
    table = GroupTable(name, ids, data.fifa_points)
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            a, b = ids[i], ids[j]
            known = data.known_group_scores.get((name, a, b))
            if known is None:
                # comprobar el par invertido y respetar la orientación
                inv = data.known_group_scores.get((name, b, a))
                score = (inv[1], inv[0]) if inv is not None else sampler.sample_score(a, b, rng)
            else:
                score = known
            table.add_match(SimulatedMatch(name, a, b, score[0], score[1]))
    return table


def simulate_group_positions(data: SimulationInput, simulations: int, seed: int | None, names: dict[str, str]) -> dict:
    """Montecarlo por grupo: fija los partidos jugados y simula los que faltan, y
    devuelve para cada equipo la probabilidad de terminar en cada puesto (1º..nº),
    sus puntos esperados y su posición esperada. Condiciona sobre lo ya jugado."""
    rng = random.Random(seed)
    sampler = MatchSamplerCache(data.context.predict_pair)
    groups = data.groups

    counts = {name: {tid: [0] * len(ids) for tid in ids} for name, ids in groups}
    points = {name: {tid: 0 for tid in ids} for name, ids in groups}

    # Casilleros de tercero del cuadro (8 cruces ganador-vs-3º): acumula qué grupo y
    # qué equipo cae en cada uno tras la asignación oficial de los 8 mejores terceros.
    third_tie_ids = [
        t.id for t in brk.ROUND_OF_32
        if t.home.kind == SlotKind.GROUP_THIRD or t.away.kind == SlotKind.GROUP_THIRD
    ]
    third_group = {tid: defaultdict(int) for tid in third_tie_ids}
    third_team = {tid: defaultdict(int) for tid in third_tie_ids}
    third_qualifies = {name: 0 for name, _ in groups}  # veces que el 3º del grupo entra entre los 8

    for _ in range(simulations):
        thirds: list[GroupStanding] = []
        for name, ids in groups:
            ranked = _simulate_group(name, ids, data, sampler, rng).rank()
            for pos, s in enumerate(ranked):
                counts[name][s.team_id][pos] += 1
                points[name][s.team_id] += s.points
            thirds.append(ranked[2])
        best = rank_best_thirds(thirds, data.fifa_points)[:8]
        for t in best:
            third_qualifies[t.group] += 1
        assignments = brk.assign_third_place_groups([t.group for t in best])
        third_by_group = {t.group.upper(): t.team_id for t in best}
        for tid, grp in assignments.items():
            g = grp.upper()
            third_group[tid][g] += 1
            third_team[tid][third_by_group[g]] += 1

    sims = float(simulations)
    groups_out: list[dict] = []
    for name, ids in groups:
        teams = []
        for tid in ids:
            p_pos = [c / sims for c in counts[name][tid]]
            exp_position = sum((i + 1) * p for i, p in enumerate(p_pos))
            teams.append({
                "team_id": tid,
                "name": names.get(tid, tid),
                "p_pos": [round(p, 4) for p in p_pos],
                "exp_points": round(points[name][tid] / sims, 2),
                "exp_position": round(exp_position, 2),
            })
        teams.sort(key=lambda t: t["exp_position"])  # mejor proyección primero
        groups_out.append({"name": name, "teams": teams, "p_third_qualifies": round(third_qualifies[name] / sims, 4)})

    third_slots: dict[int, dict] = {}
    for tid in third_tie_ids:
        by_group = sorted(third_group[tid].items(), key=lambda kv: kv[1], reverse=True)
        by_team = sorted(third_team[tid].items(), key=lambda kv: kv[1], reverse=True)
        third_slots[tid] = {
            "by_group": [{"group": g, "p": round(c / sims, 4)} for g, c in by_group],
            "by_team": [{"team_id": t, "name": names.get(t, t), "p": round(c / sims, 4)} for t, c in by_team[:6]],
        }

    return {"simulations": simulations, "groups": groups_out, "third_slots": third_slots}


def most_likely_bracket(data: SimulationInput, simulations: int, seed: int | None, names: dict[str, str]) -> dict:
    """Cuadro MÁS PROBABLE (no una tirada al azar): toma los clasificados más probables
    de cada grupo (Montecarlo, condicionado a lo jugado), asigna los 8 terceros más
    probables y resuelve cada llave con el FAVORITO, indicando su probabilidad de pasar."""
    proj = simulate_group_positions(data, simulations, seed, names)
    by_name = {g["name"]: g for g in proj["groups"]}

    group_slots: dict[str, tuple[str, str, str]] = {}
    for name, g in by_name.items():
        t = g["teams"]  # ordenado mejor -> peor
        group_slots[name] = (t[0]["team_id"], t[1]["team_id"], t[2]["team_id"])

    # Tercero de cada casillero = el MÁS PROBABLE de ese casillero (misma cifra que la
    # caja "Dieciseisavos de final" en Fase de grupos: by_team[0]). Si un mismo equipo
    # encabeza dos casilleros, se prioriza el casillero más definido y el otro toma el
    # siguiente más probable, para que el cuadro quede coherente.
    team_group = {tid: name for name, ids in data.groups for tid in ids}
    ts = proj["third_slots"]
    third_for_tie: dict[int, str] = {}
    used: set[str] = set()
    for tid in sorted(ts, key=lambda t: ts[t]["by_team"][0]["p"] if ts[t]["by_team"] else 0.0, reverse=True):
        for cand in ts[tid]["by_team"]:
            if cand["team_id"] not in used:
                third_for_tie[tid] = cand["team_id"]
                used.add(cand["team_id"])
                break
    third_labels = {tid: team_group.get(team, "?") for tid, team in third_for_tie.items()}

    winners: dict[int, str] = {}

    def resolve(tie: brk.BracketTie, slot: brk.BracketSlot) -> str | None:
        if slot.kind == SlotKind.GROUP_WINNER:
            return group_slots[slot.group][0]
        if slot.kind == SlotKind.GROUP_RUNNER_UP:
            return group_slots[slot.group][1]
        if slot.kind == SlotKind.GROUP_THIRD:
            return third_for_tie.get(tie.id)
        if slot.kind == SlotKind.WINNER_OF_TIE:
            return winners[slot.tie_id]
        return None

    def play(tie: brk.BracketTie) -> dict:
        h = resolve(tie, tie.home)
        a = resolve(tie, tie.away)
        o = data.context.predict_pair(h, a).outcome
        decisive = o.home_win + o.away_win
        p_home = o.home_win / decisive if decisive > 0 else 0.5
        p_home_adv = o.home_win + o.draw * p_home  # prob. de que el local pase la llave
        home_fav = p_home_adv >= 0.5
        winner = h if home_fav else a
        win_prob = p_home_adv if home_fav else 1 - p_home_adv
        winners[tie.id] = winner
        return {
            "tie_id": tie.id,
            "stage": tie.stage,
            "home": {"team_id": h, "name": names.get(h, h), "label": _slot_label(tie, tie.home, third_labels)},
            "away": {"team_id": a, "name": names.get(a, a), "label": _slot_label(tie, tie.away, third_labels)},
            "home_score": None,
            "away_score": None,
            "penalties": False,
            "winner_id": winner,
            "winner_name": names.get(winner, winner),
            "win_prob": round(win_prob, 4),
        }

    knockout = {
        "round_of_32": [play(t) for t in brk.ROUND_OF_32],
        "round_of_16": [play(t) for t in brk.ROUND_OF_16],
        "quarter_finals": [play(t) for t in brk.QUARTER_FINALS],
        "semi_finals": [play(t) for t in brk.SEMI_FINALS],
        "final": play(brk.FINAL),
    }
    champ = winners[brk.FINAL.id]
    return {
        "simulations": simulations,
        "champion": {"team_id": champ, "name": names.get(champ, champ)},
        "groups": proj["groups"],
        "knockout": knockout,
    }


def _run_knockout(group_slots, third_by_group, third_assignments, sampler, rng, counters, known=None) -> None:
    known = known or {}
    winners: dict[int, str] = {}

    def resolve(tie: brk.BracketTie, slot: brk.BracketSlot) -> str:
        if slot.kind == SlotKind.GROUP_WINNER:
            return group_slots[slot.group][0]
        if slot.kind == SlotKind.GROUP_RUNNER_UP:
            return group_slots[slot.group][1]
        if slot.kind == SlotKind.GROUP_THIRD:
            return third_by_group[third_assignments[tie.id].upper()]
        if slot.kind == SlotKind.WINNER_OF_TIE:
            return winners[slot.tie_id]
        raise ValueError(f"Slot no soportado: {slot.kind}")

    def play(tie: brk.BracketTie) -> str:
        # Si la llave ya se jugó de verdad, se fija el ganador real (no se samplea).
        winner = known.get(tie.id)
        if winner is None:
            home = resolve(tie, tie.home)
            away = resolve(tie, tie.away)
            winner = sampler.knockout_winner(home, away, rng)
        winners[tie.id] = winner
        return winner

    for tie in brk.ROUND_OF_32:
        counters[play(tie)].r16 += 1
    for tie in brk.ROUND_OF_16:
        counters[play(tie)].qf += 1
    for tie in brk.QUARTER_FINALS:
        counters[play(tie)].sf += 1
    for tie in brk.SEMI_FINALS:
        counters[play(tie)].final += 1
    counters[play(brk.FINAL)].champion += 1


# --------------------------------------------------------------------------- #
# Una sola corrida: devuelve el cuadro jugado (no probabilidades agregadas)
# --------------------------------------------------------------------------- #
def _slot_label(tie: brk.BracketTie, slot: brk.BracketSlot, third_assignments: dict[int, str]) -> str:
    """Etiqueta de procedencia de un slot: 1A (ganador), 2B (segundo), 3C (tercero
    asignado) o W73 (ganador del cruce 73)."""
    if slot.kind == SlotKind.GROUP_WINNER:
        return f"1{slot.group}"
    if slot.kind == SlotKind.GROUP_RUNNER_UP:
        return f"2{slot.group}"
    if slot.kind == SlotKind.GROUP_THIRD:
        return f"3{third_assignments.get(tie.id, '?').upper()}"
    if slot.kind == SlotKind.WINNER_OF_TIE:
        return f"W{slot.tie_id}"
    return "?"


def simulate_one_bracket(data: SimulationInput, seed: int | None, names: dict[str, str]) -> dict:
    """Juega el torneo UNA vez y devuelve el cuadro completo: posiciones de grupo y,
    por cada cruce, los equipos, el marcador, el ganador y si se definió por penales."""
    rng = random.Random(seed)
    sampler = MatchSamplerCache(data.context.predict_pair)

    group_slots: dict[str, tuple[str, str, str]] = {}
    thirds: list[GroupStanding] = []
    groups_out: list[dict] = []

    for name, ids in data.groups:
        ranked = _simulate_group(name, ids, data, sampler, rng).rank()
        group_slots[name] = (ranked[0].team_id, ranked[1].team_id, ranked[2].team_id)
        thirds.append(ranked[2])
        groups_out.append({
            "name": name,
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
                for i, s in enumerate(ranked)
            ],
        })

    best_thirds = rank_best_thirds(thirds, data.fifa_points)[:8]
    third_assignments = brk.assign_third_place_groups([t.group for t in best_thirds])
    third_by_group = {t.group.upper(): t.team_id for t in best_thirds}

    winners: dict[int, str] = {}

    def resolve(tie: brk.BracketTie, slot: brk.BracketSlot) -> str:
        if slot.kind == SlotKind.GROUP_WINNER:
            return group_slots[slot.group][0]
        if slot.kind == SlotKind.GROUP_RUNNER_UP:
            return group_slots[slot.group][1]
        if slot.kind == SlotKind.GROUP_THIRD:
            return third_by_group[third_assignments[tie.id].upper()]
        if slot.kind == SlotKind.WINNER_OF_TIE:
            return winners[slot.tie_id]
        raise ValueError(f"Slot no soportado: {slot.kind}")

    def team_obj(team_id: str, label: str) -> dict:
        return {"team_id": team_id, "name": names.get(team_id, team_id), "label": label}

    def play(tie: brk.BracketTie) -> dict:
        home_id = resolve(tie, tie.home)
        away_id = resolve(tie, tie.away)
        hs, away_goals, winner_id, penalties = sampler.knockout_result(home_id, away_id, rng)
        winners[tie.id] = winner_id
        return {
            "tie_id": tie.id,
            "stage": tie.stage,
            "home": team_obj(home_id, _slot_label(tie, tie.home, third_assignments)),
            "away": team_obj(away_id, _slot_label(tie, tie.away, third_assignments)),
            "home_score": hs,
            "away_score": away_goals,
            "winner_id": winner_id,
            "winner_name": names.get(winner_id, winner_id),
            "penalties": penalties,
        }

    knockout = {
        "round_of_32": [play(t) for t in brk.ROUND_OF_32],
        "round_of_16": [play(t) for t in brk.ROUND_OF_16],
        "quarter_finals": [play(t) for t in brk.QUARTER_FINALS],
        "semi_finals": [play(t) for t in brk.SEMI_FINALS],
        "final": play(brk.FINAL),
    }
    champion_id = winners[brk.FINAL.id]

    return {
        "seed": seed,
        "groups": groups_out,
        "knockout": knockout,
        "champion": {"team_id": champion_id, "name": names.get(champion_id, champion_id)},
    }
