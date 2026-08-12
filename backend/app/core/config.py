from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "DMIDOP"
    app_env: str = "development"
    api_prefix: str = "/api/v1"
    secret_key: str = "change-me-in-production-use-openssl-rand-hex-32"
    access_token_expire_minutes: int = 60 * 12
    algorithm: str = "HS256"
    # sqlite for local; postgresql+asyncpg://user:pass@localhost:5432/dmidop for prod
    database_url: str = "sqlite+aiosqlite:///./dmidop.db"
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    default_admin_email: str = "admin@dmidop.local"
    default_admin_password: str = "admin123!"
    market_tick_seconds: int = 5

    # Data science pipeline
    data_dir: str = "./data"
    models_dir: str = "./models"
    market_lookback_years: int = 5
    universe_size: int = 80
    forecast_horizons: str = "1,5,21"
    mlflow_tracking_uri: str = "./mlruns"
    mlflow_experiment: str = "dmidop"
    use_real_market_data: bool = True
    replay_enabled: bool = True

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def horizon_list(self) -> list[int]:
        return [int(x.strip()) for x in self.forecast_horizons.split(",") if x.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
