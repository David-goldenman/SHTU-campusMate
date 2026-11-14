"""Regenerate the iOS app icons from the shared brand artwork.

Run from the repository root (project virtualenv):
    uv run --no-sync python ios/shell/tools/make_app_icon.py

Produces two catalogs:

- ``AppIcon``     the plain icon, used by the local build;
- ``AppIconWeb``  the same artwork with a "web" badge in the bottom-right
                  corner, used by the web-shell build that talks to a desktop.

The App Store rejects icons with an alpha channel, so the transparent margin of
the brand icon is flattened onto its own periwinkle background.
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

PROJECT = Path(__file__).resolve().parents[3]
SOURCE = PROJECT / "web" / "brand" / "campusmate-app-icon.png"
ASSETS = PROJECT / "ios" / "shell" / "campusMate" / "Assets.xcassets"
BACKGROUND = (77, 116, 252)
BADGE = (24, 32, 48)
BADGE_TEXT = (255, 255, 255)


def flattened() -> Image.Image:
    icon = Image.open(SOURCE).convert("RGBA")
    flat = Image.new("RGB", icon.size, BACKGROUND)
    flat.paste(icon, (0, 0), icon)
    return flat.resize((1024, 1024), Image.LANCZOS)


def badge(icon: Image.Image, label: str) -> Image.Image:
    """Draw a rounded pill with the label in the bottom-right corner."""
    canvas = icon.copy()
    draw = ImageDraw.Draw(canvas, "RGBA")
    size = 1024
    font_size = int(size * 0.15)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/SFNSRounded.ttf", font_size)
    except OSError:
        font = ImageFont.load_default(size=font_size)
    left, top, right, bottom = draw.textbbox((0, 0), label, font=font)
    text_w, text_h = right - left, bottom - top
    pad_x, pad_y = int(size * 0.05), int(size * 0.03)
    width, height = text_w + pad_x * 2, text_h + pad_y * 2
    x, y = size - width - int(size * 0.06), size - height - int(size * 0.06)
    draw.rounded_rectangle([x, y, x + width, y + height], radius=height // 3, fill=BADGE)
    draw.text((x + pad_x - left, y + pad_y - top), label, font=font, fill=BADGE_TEXT)
    return canvas


def write_catalog(name: str, image: Image.Image) -> None:
    folder = ASSETS / f"{name}.appiconset"
    folder.mkdir(parents=True, exist_ok=True)
    image.save(folder / "AppIcon-1024.png", optimize=True)
    (folder / "Contents.json").write_text(
        """{
  "images" : [
    {
      "filename" : "AppIcon-1024.png",
      "idiom" : "universal",
      "platform" : "ios",
      "size" : "1024x1024"
    }
  ],
  "info" : {
    "author" : "xcode",
    "version" : 1
  }
}
""",
        encoding="utf-8",
    )
    print(f"wrote {folder.relative_to(PROJECT)}")


def main() -> None:
    base = flattened()
    write_catalog("AppIcon", base)
    write_catalog("AppIconWeb", badge(base, "web"))


if __name__ == "__main__":
    main()
