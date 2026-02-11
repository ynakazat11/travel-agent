from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    anthropic_api_key: str = ""
    amadeus_client_id: str = ""
    amadeus_client_secret: str = ""

    # Paths
    data_dir: Path = Path(__file__).parent.parent.parent / "data"

    @property
    def transfer_partners_path(self) -> Path:
        return self.data_dir / "transfer_partners.json"

    @property
    def point_valuations_path(self) -> Path:
        return self.data_dir / "point_valuations.json"


settings = Settings()
