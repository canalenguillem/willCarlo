"""Auto-carga de resultados reales desde una fuente pública sin clave (ESPN).

Consulta el scoreboard JSON de ESPN para el Mundial (keyless), mapea los nombres
de equipo a los ids de la base con el normalizador del proyecto y vuelca los
marcadores en los fixtures de fase de grupos:

  - partido FINALIZADO  -> is_played=True,  status="final"  (cuenta para posiciones)
  - partido EN VIVO      -> is_played=False, status="live"   (no finaliza posiciones)
  - programado (pre)     -> se ignora (no se sobreescribe nada)

Solo toca partidos de grupos: las llaves de eliminación no son fixtures con
equipos fijos, así que esos eventos se omiten (carga manual en la pestaña Real).
"""
from __future__ import annotations

import datetime as dt
import json
import re
import urllib.request

from sqlalchemy.orm import Session

from .models import Fixture, Team
from .team_names import _remove_diacritics, canonical_name

ESPN_URL = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard"
# Rango que cubre todo el torneo; ESPN lo resuelve en una sola llamada.
TOURNAMENT_DATES = "20260611-20260719"


def _compact(name: str) -> str:
    """Clave tolerante para cruzar grafías: sin diacríticos, sin la palabra 'and'
    ni signos. 'Bosnia-Herzegovina' y 'Bosnia and Herzegovina' -> 'bosniaherzegovina'."""
    base = _remove_diacritics(canonical_name(name)).lower()
    tokens = [t for t in re.split(r"[^a-z0-9]+", base) if t and t != "and"]
    return "".join(tokens)


def _team_lookup(db: Session) -> dict[str, str]:
    lut: dict[str, str] = {}
    for t in db.query(Team).all():
        lut[_compact(t.name)] = t.id
        lut[_compact(t.id)] = t.id
    return lut


def _parse_dt(value: str | None) -> dt.datetime | None:
    """Fecha ISO de ESPN ('2026-06-13T19:00Z') -> datetime naive en UTC."""
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        try:
            return dt.datetime.fromisoformat(value[:10])
        except ValueError:
            return None


def _fetch_events(dates: str = TOURNAMENT_DATES) -> list[dict]:
    req = urllib.request.Request(f"{ESPN_URL}?dates={dates}", headers={"User-Agent": "willcarlo/1.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.load(resp).get("events", [])


def refresh_group_results(db: Session) -> dict:
    """Trae el scoreboard y actualiza fixtures de grupos y resultados de eliminatorias."""
    lut = _team_lookup(db)
    fixtures = {frozenset((f.home_team_id, f.away_team_id)): f for f in db.query(Fixture).all()}

    updated: list[str] = []
    live: list[str] = []
    skipped = 0
    unmatched: list[str] = []
    ko_events: list[dict] = []  # eliminatorias FINALIZADAS, para asignarlas a sus llaves

    for ev in _fetch_events():
        comp = ev["competitions"][0]
        st = ev["status"]["type"]
        state = st.get("state")  # "pre" | "in" | "post"

        sides: dict[str, tuple[str | None, str, int, bool]] = {}
        for c in comp["competitors"]:
            disp = c["team"]["displayName"]
            try:
                score = int(c.get("score") or 0)
            except (TypeError, ValueError):
                score = 0
            sides[c.get("homeAway")] = (lut.get(_compact(disp)), disp, score, bool(c.get("winner")))

        if "home" not in sides or "away" not in sides:
            continue
        h_id, h_name, h_score, h_win = sides["home"]
        a_id, a_name, a_score, a_win = sides["away"]
        if not h_id or not a_id:
            unmatched.append(f"{h_name} vs {a_name}")
            continue

        fx = fixtures.get(frozenset((h_id, a_id)))
        if fx is None:
            # No es un partido de grupo: candidato a eliminatoria (solo si está finalizado).
            if st.get("completed"):
                ko_events.append({
                    "h_id": h_id, "a_id": a_id, "h_score": h_score, "a_score": a_score,
                    "winner_id": h_id if h_win else a_id if a_win else None,
                    "label": f"{h_name} {h_score}-{a_score} {a_name}",
                })
            continue

        # Fecha de juego: se guarda aunque el partido no se haya jugado (sirve para ordenar).
        kickoff = _parse_dt(ev.get("date"))
        if kickoff is not None:
            fx.kickoff_utc = kickoff

        if state == "pre":
            skipped += 1
            continue

        # Atribuir los goles al lado correcto del fixture (su orientación puede diferir).
        fx.home_goals, fx.away_goals = (h_score, a_score) if fx.home_team_id == h_id else (a_score, h_score)

        if st.get("completed"):
            fx.is_played = True
            fx.status = "final"
            updated.append(f"{h_name} {h_score}-{a_score} {a_name}")
        else:
            fx.is_played = False
            fx.status = "live"
            clock = ev["status"].get("displayClock") or ""
            live.append(f"{h_name} {h_score}-{a_score} {a_name} {clock}".strip())

    db.commit()
    ko_updated = _assign_knockout_results(db, ko_events)
    return {"updated": updated, "live": live, "skipped": skipped, "unmatched": unmatched, "knockout": ko_updated}


def _assign_knockout_results(db: Session, ko_events: list[dict]) -> list[str]:
    """Vuelca los resultados finalizados de eliminatorias en sus llaves del cuadro real.

    Va por rondas: al guardar una ronda, la siguiente ya conoce a sus equipos. Solo
    asigna llaves cuyos dos equipos están definidos (playable) y aún sin resultado.
    Orienta los goles al lado local de la llave y, si hay empate, fija los penales con
    el ganador que marca ESPN. Devuelve los marcadores aplicados."""
    if not ko_events:
        return []
    from . import real_bracket, repository
    from .models import KnockoutResult, RatingType

    by_pair = {frozenset((e["h_id"], e["a_id"])): e for e in ko_events}
    fifa = repository.latest_ratings(db, RatingType.Fifa)
    names = repository.team_names(db)

    applied: list[str] = []
    progress = True
    while progress:
        progress = False
        state = real_bracket.real_bracket_state(db, fifa, names)
        existing = {r.tie_id for r in db.query(KnockoutResult).all()}
        ko = state["knockout"]
        all_ties = [*ko["round_of_32"], *ko["round_of_16"], *ko["quarter_finals"], *ko["semi_finals"], ko["final"]]
        for tie in all_ties:
            if not tie["playable"] or tie["tie_id"] in existing:
                continue
            hid, aid = tie["home"]["team_id"], tie["away"]["team_id"]
            ev = by_pair.get(frozenset((hid, aid)))
            if ev is None:
                continue
            hg, ag = (ev["h_score"], ev["a_score"]) if ev["h_id"] == hid else (ev["a_score"], ev["h_score"])
            pen = None
            if hg == ag:
                pen = "home" if ev["winner_id"] == hid else "away" if ev["winner_id"] == aid else None
                if pen is None:
                    continue  # empate sin ganador conocido: no se puede resolver la llave
            db.add(KnockoutResult(tie_id=tie["tie_id"], home_goals=hg, away_goals=ag, penalty_winner=pen))
            db.commit()
            applied.append(ev["label"])
            progress = True
    return applied
