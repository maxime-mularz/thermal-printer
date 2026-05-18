from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    printer_type: str = "usb"
    printer_vendor_id: int = 0x04b8
    printer_product_id: int = 0x0e20
    printer_in_ep: int = 0x82
    printer_out_ep: int = 0x01
    printer_width: int = 48
    printer_profile: str = "TM-T88V"

    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_token: str = "change-me"

    telegram_bot_token: str = ""
    telegram_allowed_user_ids: str = ""

    # Rate limiting
    rate_limit_per_hour: int = 20
    rate_limit_per_day: int = 100

    # Météo
    weather_enabled: bool = True
    weather_latitude: float = 48.8566
    weather_longitude: float = 2.3522
    weather_city: str = "Paris"
    weather_daily_hour: int = 7
    weather_daily_minute: int = 0

    # Blague du jour (blagues-api.fr, token JWT requis - inscription gratuite)
    blagues_api_token: str = ""

    @field_validator("printer_vendor_id", "printer_product_id", "printer_in_ep", "printer_out_ep", mode="before")
    @classmethod
    def parse_hex_int(cls, v):
        if isinstance(v, str):
            return int(v, 16) if v.lower().startswith("0x") else int(v)
        return v


settings = Settings()
