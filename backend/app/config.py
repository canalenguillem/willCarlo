"""Configuración de la app. Port de OloraculoConfig.cs + appsettings.json.

Las claves de simulación/modelo conservan los mismos valores por defecto que la
versión .NET. Los secretos (API-Football, OpenRouter) y la conexión a la base se
leen de variables de entorno.
"""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="WILLCARLO_", env_file=".env", extra="ignore")

    # Base de datos (MariaDB)
    database_url: str = "mysql+pymysql://willcarlo:willcarlo@db:3306/willcarlo"

    # Simulación / modelos (mismos defaults que appsettings.json)
    simulation_count: int = 10000
    simulation_seed: int | None = 2026
    recent_result_count: int = 8
    goal_model_years_window: int = 8

    # Datos semilla
    data_dir: str = "data"

    # Integraciones opcionales (lesiones / contexto)
    api_football_base_url: str = "https://v3.football.api-sports.io/"
    api_football_api_key: str | None = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1/"
    openrouter_api_key: str | None = None
    openrouter_model: str = "openai/gpt-4o-mini"


settings = Settings()
