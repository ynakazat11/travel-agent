from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# Load .env into os.environ before Settings reads env vars
load_dotenv(_PROJECT_ROOT / ".env", override=True)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

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
