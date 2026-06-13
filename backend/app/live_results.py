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
    """Trae el scoreboard y actualiza los fixtures de grupos. Devuelve un resumen."""
    lut = _team_lookup(db)
    fixtures = {frozenset((f.home_team_id, f.away_team_id)): f for f in db.query(Fixture).all()}

    updated: list[str] = []
    live: list[str] = []
    skipped = 0
    unmatched: list[str] = []

    for ev in _fetch_events():
        comp = ev["competitions"][0]
        st = ev["status"]["type"]
        state = st.get("state")  # "pre" | "in" | "post"

        sides: dict[str, tuple[str | None, str, int]] = {}
        for c in comp["competitors"]:
            disp = c["team"]["displayName"]
            try:
                score = int(c.get("score") or 0)
            except (TypeError, ValueError):
                score = 0
            sides[c.get("homeAway")] = (lut.get(_compact(disp)), disp, score)

        if "home" not in sides or "away" not in sides:
            continue
        h_id, h_name, h_score = sides["home"]
        a_id, a_name, a_score = sides["away"]
        if not h_id or not a_id:
            unmatched.append(f"{h_name} vs {a_name}")
            continue

        fx = fixtures.get(frozenset((h_id, a_id)))
        if fx is None:
            continue  # eliminación u otro: no hay fixture de grupo

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
    return {"updated": updated, "live": live, "skipped": skipped, "unmatched": unmatched}
