from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Адрес трекера и id не зашиты в код: всё берётся из .env (см. README, «Подключение к Keitaro»)."""

    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True)

    keitaro_url: str = ""
    keitaro_api_key: str = ""
    name_prefix: str = "test_Zaitsev_"
    database_url: str = "sqlite:///./app.db"
    # домен, группа и источник новой кампании; id выводит scripts/recon.py
    default_domain_id: int | None = None
    default_group_id: str | None = None  # в API Keitaro group_id строка
    default_source_id: int | None = None
    # Host-заголовки, на которые отвечает приложение (защита от DNS rebinding); в .env JSON: ["localhost","my.host"]
    allowed_hosts: list[str] = ["localhost", "127.0.0.1"]


settings = Settings()
