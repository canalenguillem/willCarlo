# STATUS — WillCarlo (ex Oloráculo)

> Documento de orientación para Claude Code. Resume qué es el proyecto, su estado
> actual, qué está verificado y qué falta. Empezá leyendo esto antes de tocar nada.

## Qué es

Predictor del Mundial 2026. Es un **port** del proyecto open-source
[MarianoVilla/Oloraculo](https://github.com/MarianoVilla/Oloraculo) desde su stack
original (.NET 9 / Blazor Server / EF Core / SQLite) a:

- **Backend:** Python + FastAPI
- **Persistencia:** MariaDB (SQLAlchemy)
- **Frontend:** Vite + TypeScript (servido con nginx)
- **Orquestación:** Docker Compose

La lógica de predicción se portó fiel al original: misma escalera de modelos, misma
matemática (Elo, Poisson con ajuste Dixon-Coles), mismas constantes y el mismo motor
Montecarlo con el cuadro oficial de 48 equipos.

## Cómo correrlo

```bash
docker compose up --build
```

- Frontend: http://localhost:5173
- API + docs: http://localhost:8000/docs
- MariaDB: localhost:3306

En el primer arranque el backend crea el esquema e importa los CSV semilla solos
(~49.000 resultados históricos; tarda unos segundos). Los datos quedan en el volumen
`db_data`.

## Mapa de archivos

```
backend/app/
  probability.py   Matemática: Elo, Poisson + Dixon-Coles, métricas. Port de Probability/*
  predictors.py    Escalera de 6 modelos + selector final. Port de Predictors/*
  simulation.py    Motor Montecarlo (grupos + eliminación). Port de Services/Simulation/*
  bracket.py       Cuadro WC2026 + asignación de terceros. Port de WorldCup2026Bracket.cs
  real_bracket.py  Cuadro REAL: posiciones jugadas + eliminación cargada a mano (sin port)
  live_results.py  Auto-carga de marcadores reales desde ESPN (keyless) (sin port)
  team_names.py    Normalización de nombres -> id. Port de TeamNameNormalizer.cs
  models.py        ORM SQLAlchemy (MariaDB). Port de DAL/ + Models/
  csv_import.py    Importación de los 4 CSV semilla. Port de CsvImportService.cs
  repository.py    Carga datos de la base y arma contextos de predicción
  config.py        Settings vía env (prefijo WILLCARLO_). Port de OloraculoConfig + appsettings
  main.py          App FastAPI + endpoints
backend/data/      Los 4 CSV semilla (grupos, FIFA, Elo, resultados históricos)
frontend/src/
  main.ts          Router + vistas (la principal es "Real"; Lab/Torneo/Bracket siguen en el código)
  api.ts           Cliente tipado de la API
  style.css        Estética "scoreboard"
docker-compose.yml MariaDB + backend + frontend
```

> Nota: `real_bracket.py` y `live_results.py` son agregados propios de este port (no
> existen en el original .NET). Reutilizan la matemática de `simulation.py` y `bracket.py`.

## La escalera de modelos (clave del proyecto)

Las predicciones se construyen por niveles; el oráculo elige el escalón usable más
alto (no degradado):

| Prioridad | Modelo                    | Señal                                          |
|-----------|---------------------------|------------------------------------------------|
| 0         | Modelo base               | probabilidad uniforme                          |
| 1         | Ranking FIFA              | puntos FIFA → expectativa Elo                  |
| 2         | Elo                       | rating Elo                                     |
| 3         | Forma reciente            | Elo + sesgo de recencia                        |
| 4         | Modelo de goles (Poisson) | fuerzas ataque/defensa ajustadas por rival     |
| 5         | Goles + contexto reciente | modelo de goles + disponibilidad de jugadores  |

Cuando Elo y FIFA coinciden en el pick contra el modelo elegido, se aplica una
calibración del 15% hacia ese consenso (`RANKING_BIAS_WEIGHT`).

## Estado actual: QUÉ FUNCIONA (verificado)

- Import de CSV: 12 grupos, 357 equipos, 453 ratings, ~49.000 resultados, 72 fixtures.
- `POST /api/lab`: devuelve la escalera completa de 6 modelos + oráculo final. Probado
  con Argentina–Francia (parejo) y Brasil–Escocia (favorito claro). Números trazables
  a los CSV.
- `POST /api/tournament/run`: Montecarlo completo con cuadro real de 48 equipos.
  Probabilidades de campeón suman 1.0. Columnas monótonas (campeón < final < semis <
  clasifica). Favoritos sensatos. ~2s cada 2000 simulaciones.
- **Pantalla "Real" (vista principal del frontend).** Sub-pestañas Grupos / Cuadro /
  Pronóstico / Proyección. Se apoya en:
  - `POST /api/results/refresh`: auto-carga marcadores reales desde el scoreboard
    público de ESPN (sin API key). Partido FINALIZADO → `status="final"` (cuenta para
    posiciones); EN VIVO → `status="live"`; programado → se ignora. Solo toca fixtures
    de grupos. Auto-refresco cada 60s en la UI con distintivo "VIVO".
  - `GET /api/bracket/real`: estado del cuadro real (tablas de grupos jugadas +
    eliminación). Resuelve slots parcialmente (`None` mientras no se conozca el equipo).
  - `POST/DELETE /api/knockout/{tie_id}/result`: carga/borra a mano el resultado de una
    llave de eliminación (con penales si hay empate). Valida que la llave sea jugable.
  - `POST /api/groups/simulate`: Montecarlo por grupo condicionado a lo ya jugado
    (distribución de puesto, rutas a 16avos, distribución de terceros).
  - `POST /api/tournament/bracket` y `/bracket/likely`: una tirada del cuadro vs. cuadro
    más probable (favorito por llave con su probabilidad).
- Frontend compila con TypeScript estricto y buildea limpio. Verificado en navegador.

> La marca ya está renombrada a **WillCarlo** en todo el código (título FastAPI, `<h1>`,
> prefijo de env `WILLCARLO_`, DB `willcarlo`). La antigua "TAREA 1" de renombrado está
> completa; ya no aplica.

## Comportamientos esperados (NO son bugs)

- **El escalón 5 ("Goles + contexto reciente") aparece siempre DEGRADADO.** Necesita
  datos de disponibilidad/lesiones que hoy no se cargan. El oráculo usa el Poisson
  (nivel 4) mientras tanto. Es correcto.
- **"Forma reciente" da delta 100.0 para equipos top.** Es el techo del clamp
  `[-100, 100]` de la fórmula original; para selecciones de elite se satura y termina
  igual que Elo. Fiel al port.
- **Las probabilidades de campeón están muy comprimidas** entre los favoritos (~5.5%
  para varios). Es consecuencia del modelo Poisson con xg simétricos en cruces parejos
  — captura la "personalidad" azarosa del oloráculo original.

## Convenciones que NO hay que romper (config / datos)

- el prefijo de variables de entorno `WILLCARLO_` (`config.py` + `docker-compose.yml`)
- el nombre de la base de datos `willcarlo`
- el volumen `db_data` (contiene la base ya poblada; borrarlo fuerza reimportar todo)

## Backlog (pendiente, en orden sugerido)

1. **Pantalla de rendimiento/evaluación** con Brier score, RPS y log loss (las métricas
   ya están en `probability.py`; falta guardar snapshots de predicción y compararlos
   contra resultados reales). Port de `/performance` + `EvaluationService.cs`.
2. **Paralelizar el Montecarlo** con `multiprocessing` para que 10.000 simulaciones no
   tarden ~10s en un solo hilo.
3. **Conectores de contexto opcionales** (API-Football para lesiones, OpenRouter para
   clasificar noticias) que pueblen la tabla `fixture_contexts` y activen el escalón 5.
   Los hooks de config (`WILLCARLO_API_FOOTBALL_API_KEY`, `WILLCARLO_OPENROUTER_API_KEY`)
   ya están previstos en `config.py`.

## Hecho recientemente (ya no es backlog)

- **Renombrado de marca** Oloráculo → WillCarlo (código + env + DB). Completo.
- **Carga de resultados reales**: vía ESPN automática (`live_results.py`) y carga manual
  de eliminación (`real_bracket.py` + `KnockoutResult`). La vista "Real" del frontend
  consume todo esto. Reemplaza el ítem "pantalla de carga de resultados" del backlog viejo.

## Referencia del original

El repo .NET está documentado en el README (sección "Mapeo de stack"). Si necesitás
ver cómo hace algo el original, los archivos C# equivalentes están listados en el mapa
de archivos de arriba.