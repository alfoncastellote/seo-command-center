"""Environment-driven configuration for the panel."""
import os
import pathlib

APP_DIR = pathlib.Path(__file__).resolve().parent
ROOT = APP_DIR.parent


def env(key: str, default: str = "") -> str:
    value = os.environ.get(key)
    return value if value not in (None, "") else default


DATA_DIR = pathlib.Path(env("DATA_DIR", str(ROOT / "data"))).expanduser()
DB_PATH = pathlib.Path(env("DB_PATH", str(DATA_DIR / "panel.db"))).expanduser()

ACCESS_KEY = env("ACCESS_KEY", "changeme")
# Derive a stable signing secret when one is not provided.
SESSION_SECRET = env("SESSION_SECRET", f"svp-{ACCESS_KEY}-session-secret")
BRAND_NAME = env("BRAND_NAME", "SEO Visibility")

DATAFORSEO_LOGIN = env("DATAFORSEO_LOGIN")
DATAFORSEO_PASSWORD = env("DATAFORSEO_PASSWORD")

HOST = env("HOST", "0.0.0.0")
PORT = int(env("PORT", "8000"))

SESSION_COOKIE = "svp_session"
SESSION_MAX_AGE = int(env("SESSION_MAX_AGE", str(60 * 60 * 24 * 14)))  # 14 days

# Defaults written into the settings table on first boot.
DEFAULT_SETTINGS = {
    "concurrency": "8",
    "ai_daily_cap": "2",
    "geogrid_daily_cap": "1",
    "ai_schedule_enabled": "1",
    "ai_schedule_dow": "1",     # Monday (0 = Monday)
    "ai_schedule_hour": "6",
    "geogrid_schedule_enabled": "1",
    "geogrid_schedule_dow": "1",
    "geogrid_schedule_hour": "7",
    "brand_name": BRAND_NAME,
}
