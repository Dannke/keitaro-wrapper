from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True)

    keitaro_url: str = "https://keitaro.example.com"
    keitaro_api_key: str = ""
    name_prefix: str = "test_Zaitsev_"
    database_url: str = "sqlite:///./app.db"
    # Значения keitaro.example.com, найдены scripts/recon.py: example.com / FORTESTS / FORTESTS
    default_domain_id: int = 1
    default_group_id: str = "2"  # в API Keitaro group_id строка
    default_source_id: int = 3
    # Host-заголовки, на которые отвечает приложение (защита от DNS rebinding); в .env JSON: ["localhost","my.host"]
    allowed_hosts: list[str] = ["localhost", "127.0.0.1"]


settings = Settings()
