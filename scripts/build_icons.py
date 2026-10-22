"""Build display-size PNG assets from the existing campusMate source artwork."""
from pathlib import Path
from PIL import Image

BRAND = Path(__file__).resolve().parents[1] / 'web' / 'brand'


def main():
    with Image.open(BRAND / 'campusmate-app-icon.png') as original:
        for size, name in ((96, 'campusmate-icon-96.png'), (48, 'campusmate-favicon-48.png'),
                           (180, 'campusmate-touch-180.png')):
            image = original.convert('RGBA').resize((size, size), Image.Resampling.LANCZOS)
            destination = BRAND / name
            image.save(destination, optimize=True)
            print(f'{name}: {size}x{size}, {destination.stat().st_size} bytes')


if __name__ == '__main__':
    main()
