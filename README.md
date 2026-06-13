# WillCarlo — port a Docker + Vite + TypeScript + FastAPI + MariaDB

Port del predictor del Mundial 2026 de [MarianoVilla/Oloraculo](https://github.com/MarianoVilla/Oloraculo)
desde su stack original (.NET 9 / Blazor Server / EF Core / SQLite) al stack:

- **Backend:** Python + FastAPI
- **Persistencia:** MariaDB (vía SQLAlchemy)
- **Frontend:** Vite + TypeScript (servido con nginx)
- **Orquestación:** Docker Compose

La lógica de predicción se portó fiel al original: misma escalera de modelos, misma
matemática (Elo, Poisson con ajuste Dixon-Coles), mismas constantes y el mismo motor
Montecarlo con el cuadro oficial de 48 equipos.

## Cómo correrlo

Requisito: Docker con Compose.

```bash
cp .env.example .env        # opcional: ya hay valores por defecto
docker compose up --build
```

Esto levanta tres servicios:

| Servicio   | URL                      | Qué es                                  |
|------------|--------------------------|-----------------------------------------|
| `frontend` | http://localhost:5173    | la interfaz (Laboratorio y Torneo)      |
| `backend`  | http://localhost:8000    | la API (docs en `/docs`)                |
| `db`       | localhost:3306           | MariaDB                                 |

En el primer arranque, el backend crea el esquema e importa los CSV semilla
automáticamente (grupos, ranking FIFA, Elo y ~49.000 resultados históricos). Tarda
unos segundos; después la base queda poblada en el volumen `db_data`.

## Pantallas

- **Laboratorio** (`/lab` en el original): elegís dos selecciones y ves cada escalón
  de la escalera más la decisión del oráculo final, con la barra 1X2 y los goles esperados.
- **Torneo** (`/tournament`): corre la simulación Montecarlo del torneo completo y
  muestra, por equipo, probabilidad de ser campeón, llegar a cada ronda y clasificar.

## La escalera de modelos

Igual que el original, las predicciones se construyen por niveles y el oráculo elige
el escalón usable más alto (no degradado):

| Prioridad | Modelo                       | Señal                                            |
|-----------|------------------------------|--------------------------------------------------|
| 0         | Modelo base                  | probabilidad uniforme                            |
| 1         | Ranking FIFA                 | puntos FIFA → expectativa Elo                    |
| 2         | Elo                          | rating Elo                                       |
| 3         | Forma reciente               | Elo + sesgo de recencia                          |
| 4         | Modelo de goles (Poisson)    | fuerzas ataque/defensa ajustadas por rival       |
| 5         | Goles + contexto reciente    | modelo de goles + disponibilidad de jugadores    |

Cuando Elo y FIFA coinciden en el pick contra el modelo elegido, se aplica una
calibración del 15% hacia ese consenso (`RANKING_BIAS_WEIGHT`), tal como en el original.

## Mapeo de stack (.NET → este port)

| Original (.NET)                              | Este port (Python/TS)                          |
|----------------------------------------------|------------------------------------------------|
| `Probability/ProbabilityHelper.cs`           | `backend/app/probability.py`                   |
| `Predictors/*` + `FinalPredictionSelector`   | `backend/app/predictors.py`                    |
| `Services/Simulation/SimulationService.cs`   | `backend/app/simulation.py`                    |
| `Services/Simulation/WorldCup2026Bracket.cs` | `backend/app/bracket.py`                        |
| `Helpers/TeamNameNormalizer.cs`              | `backend/app/team_names.py`                     |
| `Services/CsvImportService.cs`               | `backend/app/csv_import.py`                     |
| `DAL/OloraculoDbContext` + `Models/*` (EF)   | `backend/app/models.py` (SQLAlchemy)            |
| `OloraculoConfig` + `appsettings.json`       | `backend/app/config.py` (variables de entorno) |
| `Components/*` (Blazor + MudBlazor)          | `frontend/src/*` (Vite + TypeScript)            |
| SQLite                                        | MariaDB                                         |

## Configuración

Variables de entorno del backend (prefijo `WILLCARLO_`), con los mismos valores por
defecto que el `appsettings.json` original:

- `WILLCARLO_DATABASE_URL` — cadena SQLAlchemy (la setea docker-compose)
- `WILLCARLO_SIMULATION_COUNT` (10000)
- `WILLCARLO_SIMULATION_SEED` (2026)
- `WILLCARLO_RECENT_RESULT_COUNT` (8)
- `WILLCARLO_GOAL_MODEL_YEARS_WINDOW` (8)

## Desarrollo sin Docker

Backend:

```bash
cd backend
pip install -r requirements.txt
# apuntá a tu MariaDB (o usá sqlite para probar): 
export WILLCARLO_DATABASE_URL="sqlite:///./willcarlo.db"
uvicorn app.main:app --reload
```

Frontend:

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173, proxea /api a http://localhost:8000
```

## Qué quedó fuera

El original tiene integraciones opcionales (API-Football para fixtures y lesiones,
OpenRouter para clasificar noticias de disponibilidad, refresco de rankings desde la
web). El modelo de contexto (`Goles + contexto reciente`) está portado y listo para
recibir esas señales vía la tabla `fixture_contexts`, pero los servicios que las
pueblan automáticamente no se incluyen en este port. Los hooks de configuración
(`WILLCARLO_API_FOOTBALL_API_KEY`, `WILLCARLO_OPENROUTER_API_KEY`) ya están previstos.

## Nota sobre los datos

Los CSV semilla en `backend/data/` vienen del repositorio original. El historial de
resultados (~49.000 partidos) hace que el primer import tarde unos segundos y que el
entrenamiento del modelo de goles corra una sola vez al levantar la simulación.
