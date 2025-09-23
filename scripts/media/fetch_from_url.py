from pathlib import Path
import requests
from PIL import Image
from io import BytesIO
from scripts.utils.env import USER_AGENT


SESSION = requests.Session()
SESSION.headers.update({"User-Agent": USER_AGENT})


def download_to_webp(url: str, out_path: Path, max_width: int = 1600, quality: int = 80):
out_path.parent.mkdir(parents=True, exist_ok=True)
r = SESSION.get(url, timeout=30)
r.raise_for_status()
img = Image.open(BytesIO(r.content)).convert("RGB")
if img.width > max_width:
h = int(img.height * (max_width / img.width))
img = img.resize((max_width, h))
img.save(out_path, format="WEBP", quality=quality, method=6)
return str(out_path)
