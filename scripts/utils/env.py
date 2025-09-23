import os
from pathlib import Path
from dotenv import load_dotenv


# Load .env if present (local runs). In Actions, use repo secrets → env.
load_dotenv(dotenv_path=Path(".env"))


GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")


ASSETS_DIR = Path("assets/images")
ASSETS_DIR.mkdir(parents=True, exist_ok=True)
TMP_DIR = Path("scripts/tmp")
CACHE_DIR = TMP_DIR / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


USER_AGENT = (
"BestMuscatBot/1.0 (+https://example.com) Requests"
)


def cache_path(name: str):
return CACHE_DIR / name
