"""Application configuration."""

import os
from pathlib import Path
from dotenv import load_dotenv

# Use absolute path to .env so it works regardless of systemd working directory
_env_path = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(_env_path)


class Settings:
    PROJECT_NAME: str = "CryptoEdge Pro"
    VERSION: str = "1.0.0"

    # Gemini (supports multiple keys: GEMINI_API_KEY, GEMINI_API_KEY_2, GEMINI_API_KEY_3 ...)
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_API_KEY_2: str = os.getenv("GEMINI_API_KEY_2", "")
    GEMINI_API_KEY_3: str = os.getenv("GEMINI_API_KEY_3", "")
    GEMINI_MODEL: str = "gemini-2.5-flash"

    @property
    def gemini_keys(self) -> list[str]:
        """Return all configured Gemini API keys."""
        keys = [self.GEMINI_API_KEY, self.GEMINI_API_KEY_2, self.GEMINI_API_KEY_3]
        return [k for k in keys if k]

    _gemini_key_index: int = 0

    def get_next_gemini_key(self) -> str:
        """Round-robin through available Gemini API keys."""
        keys = self.gemini_keys
        if not keys:
            return ""
        key = keys[self._gemini_key_index % len(keys)]
        Settings._gemini_key_index += 1
        return key

    # Binance
    BINANCE_API_KEY: str = os.getenv("BINANCE_API_KEY", "")
    BINANCE_API_SECRET: str = os.getenv("BINANCE_API_SECRET", "")

    # OKX
    OKX_API_KEY: str = os.getenv("OKX_API_KEY", "")
    OKX_API_SECRET: str = os.getenv("OKX_API_SECRET", "")
    OKX_API_PASSPHRASE: str = os.getenv("OKX_API_PASSPHRASE", "")

    # DeepSeek
    DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "")
    DEEPSEEK_MODEL: str = "deepseek-chat"
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"

    # CoinMarketCap (fallback data source)
    CMC_API_KEY: str = os.getenv("CMC_API_KEY", "")

    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./data/reports.db")

    # Frontend
    FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:3000")

    # Symbols to track (3 coins × 2 reports/day = 6 Gemini calls)
    SYMBOLS: list[str] = ["BTCUSDT", "SOLUSDT", "SUIUSDT"]
    SYMBOL_NAMES: dict[str, str] = {
        "BTCUSDT": "Bitcoin",
        "SOLUSDT": "Solana",
        "SUIUSDT": "SUI",
    }

    # Schedule times (Beijing time UTC+8)
    SCHEDULE_HOURS: list[int] = [6, 20]


settings = Settings()

