"""Regenerate the iOS app icon from the shared brand artwork.

Run with the project virtualenv: uv run --no-sync python ipa/tools/make_app_icon.py
The App Store rejects icons with an alpha channel, so the transparent margin of
the brand icon is flattened onto its own periwinkle background.
"""
from pathlib import Path

from PIL import Image

PROJECT = Path(__file__).resolve().parents[2]
SOURCE = PROJECT / "web" / "brand" / "campusmate-app-icon.png"
TARGET = PROJECT / "ipa" / "campusMate" / "Assets.xcassets" / "AppIcon.appiconset" / "AppIcon-1024.png"
BACKGROUND = (77, 116, 252)


def main():
    icon = Image.open(SOURCE).convert("RGBA")
    flattened = Image.new("RGB", icon.size, BACKGROUND)
    flattened.paste(icon, (0, 0), icon)
    flattened.resize((1024, 1024), Image.LANCZOS).save(TARGET, optimize=True)
    print(f"wrote {TARGET.relative_to(PROJECT)}")


if __name__ == "__main__":
    main()
