from pathlib import Path
from PIL import Image


ROOT = Path("assets/images")


def optimize_dir(root: Path = ROOT):
if not root.exists():
return
for p in root.rglob("*"):
if not p.is_file():
continue
if p.suffix.lower() in {".webp"}:
# re-save to strip metadata
try:
img = Image.open(p).convert("RGB")
img.save(p, format="WEBP", quality=80, method=6)
except Exception:
pass


if __name__ == "__main__":
optimize_dir()
