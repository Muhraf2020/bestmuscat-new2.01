from pathlib import Path
import requests
from scripts.utils.env import GOOGLE_MAPS_API_KEY, USER_AGENT


SESSION = requests.Session()
SESSION.headers.update({"User-Agent": USER_AGENT})


BASE = "https://maps.googleapis.com/maps/api/place/photo"


def fetch_google_photo(photo_reference: str, out_path: Path, maxwidth: int = 1600):
if not GOOGLE_MAPS_API_KEY:
return None
out_path.parent.mkdir(parents=True, exist_ok=True)
params = {
"photoreference": photo_reference,
"maxwidth": str(maxwidth),
"key": GOOGLE_MAPS_API_KEY,
}
# Google returns a redirect to the actual image
with SESSION.get(BASE, params=params, timeout=30, allow_redirects=True) as r:
r.raise_for_status()
with open(out_path, "wb") as f:
f.write(r.content)
return str(out_path)
