# scripts/media/optimize_images.py
from pathlib import Path
from PIL import Image

ROOT = Path("assets/images")

def optimize_dir(root: Path = ROOT):
    if not root.exists():
        return
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix.lower() == ".webp":
            try:
                img = Image.open(p).convert("RGB")
                # re-save as WEBP to strip EXIF and normalize quality
                img.save(p, format="WEBP", quality=80, method=6)
            except Exception:
                # Don't fail the pipeline on a single bad image
                pass

if __name__ == "__main__":
    optimize_dir()
