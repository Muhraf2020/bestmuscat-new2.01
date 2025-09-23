# scripts/media/fetch_photos_google.py
from pathlib import Path
from io import BytesIO
import requests
from PIL import Image

from scripts.utils.env import GOOGLE_MAPS_API_KEY, USER_AGENT

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": USER_AGENT})

BASE = "https://maps.googleapis.com/maps/api/place/photo"

def fetch_google_photo(photo_reference: str, out_path: Path, maxwidth: int = 1600):
    """
    Download a Google Places photo by reference and save it as a real WEBP.
    Returns str(out_path) on success, else None.
    """
    if not GOOGLE_MAPS_API_KEY or not photo_reference:
        return None

    out_path.parent.mkdir(parents=True, exist_ok=True)

    params = {
        "photoreference": photo_reference,
        "maxwidth": str(maxwidth),
        "key": GOOGLE_MAPS_API_KEY,
    }

    # Google returns a redirect to the actual image bytes
    r = SESSION.get(BASE, params=params, timeout=30, allow_redirects=True)
    r.raise_for_status()

    # Convert returned image (usually JPEG) to true WEBP
    img = Image.open(BytesIO(r.content)).convert("RGB")
    if img.width > maxwidth:
        new_h = int(img.height * (maxwidth / img.width))
        img = img.resize((maxwidth, new_h))
    img.save(out_path, format="WEBP", quality=80, method=6)
    return str(out_path)
