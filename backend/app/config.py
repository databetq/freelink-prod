from functools import lru_cache
from pathlib import Path
from decimal import Decimal
from typing import Annotated

from pydantic import Field, NonNegativeInt, PositiveInt, SecretStr, StringConstraints
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[1] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str
    database_connect_timeout: PositiveInt = 3
    frontend_origin: str = "http://localhost:5173"
    google_client_id: str = ""
    google_client_secret: SecretStr = SecretStr("")
    google_redirect_uri: str = "http://localhost:8000/auth/google/callback"
    session_secret: SecretStr = SecretStr("")
    session_cookie_secure: bool = False
    escrow_chain_id: PositiveInt = 11155111
    escrow_contract_address: Annotated[str, StringConstraints(pattern=r"^0x[0-9a-fA-F]{40}$")] | None = None
    escrow_thb_per_eth: Annotated[Decimal, Field(gt=0, max_digits=14, decimal_places=2)] | None = None
    escrow_rpc_url: SecretStr = SecretStr("")
    # Unset waits for finalized blocks. A testnet demo can count a few confirmations instead.
    escrow_confirmations: NonNegativeInt | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
