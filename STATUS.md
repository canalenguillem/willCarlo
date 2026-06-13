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
  team_names.py    Normalización de nombres -> id. Port de TeamNameNormalizer.cs
  models.py        ORM SQLAlchemy (MariaDB). Port de DAL/ + Models/
  csv_import.py    Importación de los 4 CSV semilla. Port de CsvImportService.cs
  repository.py    Carga datos de la base y arma contextos de predicción
  config.py        Settings vía env (prefijo OLORACULO_). Port de OloraculoConfig + appsettings
  main.py          App FastAPI + endpoints
backend/data/      Los 4 CSV semilla (grupos, FIFA, Elo, resultados históricos)
frontend/src/
  main.ts          Router + vistas Laboratorio y Torneo
  api.ts           Cliente tipado de la API
  style.css        Estética "scoreboard"
docker-compose.yml MariaDB + backend + frontend
```

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
- Frontend compila con TypeScript estricto y buildea limpio. Vistas Laboratorio y
  Torneo funcionando contra la API real (verificado en navegador).

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

## TAREA 1 (primera, en curso): renombrar la marca a "WillCarlo"

Cambiar SOLO la marca visible de "Oloráculo" a **WillCarlo**:

- `frontend/src/main.ts` — el `<h1>` del header (busca "Olorác")
- `frontend/index.html` — el `<title>`
- `backend/app/main.py` — el `title=` del `FastAPI(...)` (sale en `/docs`)

NO tocar (rompe la config o borra datos del volumen):
- el prefijo de variables de entorno `OLORACULO_` (`config.py` + `docker-compose.yml`)
- el nombre de la base de datos `oloraculo`
- el volumen `db_data`
- el `name` en `package.json` (interno, opcional)

Mostrar el diff antes de aplicar.

## Backlog (pendiente, en orden sugerido)

1. **Pantalla de carga de resultados reales** desde la UI (el endpoint
   `POST /api/matches/{id}/result` ya existe; falta la vista de fixtures con inputs de
   marcador). Port de la pantalla `/matches` del original.
2. **Pantalla de rendimiento/evaluación** con Brier score, RPS y log loss (las métricas
   ya están en `probability.py`; falta guardar snapshots de predicción y compararlos
   contra resultados reales). Port de `/performance` + `EvaluationService.cs`.
3. **Paralelizar el Montecarlo** con `multiprocessing` para que 10.000 simulaciones no
   tarden ~10s en un solo hilo.
4. **Conectores de contexto opcionales** (API-Football para lesiones, OpenRouter para
   clasificar noticias) que pueblen la tabla `fixture_contexts` y activen el escalón 5.
   Los hooks de config (`OLORACULO_API_FOOTBALL_API_KEY`, `OLORACULO_OPENROUTER_API_KEY`)
   ya están previstos en `config.py`.

## Referencia del original

El repo .NET está documentado en el README (sección "Mapeo de stack"). Si necesitás
ver cómo hace algo el original, los archivos C# equivalentes están listados en el mapa
de archivos de arriba.