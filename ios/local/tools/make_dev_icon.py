"""Generate the dev app icon: the release icon plus a corner "DEV" badge.

Run from the repository root with the build virtualenv:

    .codex/runtime-venv/bin/python ipa/local/tools/make_dev_icon.py

Writes ipa/local/Resources/Assets.xcassets/AppIconDev.appiconset/AppIcon-1024-dev.png
"""
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "Resources/Assets.xcassets"
SOURCE = ASSETS / "AppIcon.appiconset/AppIcon-1024.png"
TARGET = ASSETS / "AppIconDev.appiconset"

ICON_SIZES = {
    "AppIcon20x20@2x": 40, "AppIcon20x20@3x": 60,
    "AppIcon29x29@2x": 58, "AppIcon29x29@3x": 87,
    "AppIcon40x40@2x": 80, "AppIcon40x40@3x": 120,
    "AppIcon60x60@2x": 120, "AppIcon60x60@3x": 180,
    "AppIcon76x76@2x": 152, "AppIcon83.5x83.5@2x": 167,
}

BADGE_TEXT = "DEV"
BADGE_FILL = (15, 23, 42, 255)      # slate, matches the Nord shell
BADGE_TEXT_COLOR = (255, 255, 255, 255)


def font(size: int):
    for candidate in (
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ):
        if Path(candidate).exists():
            try:
                return ImageFont.truetype(candidate, size)
            except OSError:
                continue
    return ImageFont.load_default()


def main():
    image = Image.open(SOURCE).convert("RGB")
    if image.size != (1024, 1024):
        image = image.resize((1024, 1024), Image.LANCZOS)

    draw = ImageDraw.Draw(image)
    size = 1024
    text_font = font(150)
    box = draw.textbbox((0, 0), BADGE_TEXT, font=text_font)
    text_width, text_height = box[2] - box[0], box[3] - box[1]
    pad_x, pad_y = 54, 34
    badge_width, badge_height = text_width + pad_x * 2, text_height + pad_y * 2
    margin = 64
    left, top = size - margin - badge_width, size - margin - badge_height

    draw.rounded_rectangle(
        (left, top, left + badge_width, top + badge_height),
        radius=54,
        fill=BADGE_FILL,
        outline=(255, 255, 255, 235),
        width=8,
    )
    draw.text(
        (left + pad_x - box[0], top + pad_y - box[1]),
        BADGE_TEXT,
        font=text_font,
        fill=BADGE_TEXT_COLOR,
    )

    # Loose PNGs for the prototype build: the asset catalog would need actool,
    # which requires a simulator runtime this machine does not have.
    for variant in ("release", "dev"):
        folder = ROOT / "Resources/Icons" / variant
        folder.mkdir(parents=True, exist_ok=True)
        source = image if variant == "dev" else Image.open(SOURCE).convert("RGB")
        for name, size in ICON_SIZES.items():
            source.resize((size, size), Image.LANCZOS).save(folder / f"{name}.png", format="PNG")

    TARGET.mkdir(parents=True, exist_ok=True)
    image.save(TARGET / "AppIcon-1024-dev.png", format="PNG")
    (TARGET / "Contents.json").write_text(json.dumps({
        "images": [{
            "filename": "AppIcon-1024-dev.png",
            "idiom": "universal",
            "platform": "ios",
            "size": "1024x1024",
        }],
        "info": {"author": "xcode", "version": 1},
    }, indent=2) + "\n", encoding="utf-8")
    print(TARGET / "AppIcon-1024-dev.png")


if __name__ == "__main__":
    main()
