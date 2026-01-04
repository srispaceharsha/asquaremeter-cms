#!/usr/bin/env python3
"""Regenerate thumbnails and web images from full-size images"""

from pathlib import Path
from PIL import Image

CATALOG_PATH = Path(__file__).parent / "catalog"

def regenerate_images():
    full_dir = CATALOG_PATH / "full"
    thumb_dir = CATALOG_PATH / "thumb"
    web_dir = CATALOG_PATH / "web"

    if not full_dir.exists():
        print("No full/ directory found")
        return

    images = list(full_dir.glob("*.jpg"))
    print(f"Regenerating {len(images)} images...")

    for img_path in images:
        img = Image.open(img_path)

        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")

        # Thumbnail: 300px wide, quality 90
        thumb = img.copy()
        thumb.thumbnail((300, 10000), Image.LANCZOS)
        thumb.save(thumb_dir / img_path.name, "JPEG", quality=90)

        # Web: 1200px wide, quality 92
        web = img.copy()
        web.thumbnail((1200, 10000), Image.LANCZOS)
        web.save(web_dir / img_path.name, "JPEG", quality=92)

        print(f"  ✓ {img_path.name}")

    print(f"\nDone! Regenerated {len(images)} thumbnails and web images.")

if __name__ == "__main__":
    regenerate_images()
