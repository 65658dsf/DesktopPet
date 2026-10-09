"""Generate the tray / application icon from the packaged atlas (head crop)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(r"d:\Coding\DesktopPet")
PET_DIR = ROOT / "pets" / "qinche-q"
ASSETS = ROOT / "app" / "assets"
CELL_4X = (768, 832)


def head_square(atlas: Image.Image) -> Image.Image:
    cell = atlas.crop((0, 0, CELL_4X[0], CELL_4X[1]))
    top = cell.crop((0, 0, CELL_4X[0], int(CELL_4X[1] * 0.62)))     # head + shoulders
    alpha = np.asarray(top)[..., 3]
    ys, xs = np.nonzero(alpha > 16)
    x0, x1 = int(xs.min()), int(xs.max())
    y0, y1 = int(ys.min()), int(ys.max())
    size = max(x1 - x0, y1 - y0)
    cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
    half = size // 2 + int(size * 0.06)
    box = (cx - half, cy - half, cx + half, cy + half)
    square = Image.new("RGBA", (half * 2, half * 2), (0, 0, 0, 0))
    square.paste(top.crop(box), (0, 0))
    return square


def main() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    with Image.open(PET_DIR / "spritesheet@4x.webp") as opened:
        atlas = opened.convert("RGBA")
    square = head_square(atlas)

    # soft dark disc behind the head so the icon reads on any tray background
    disc = Image.new("RGBA", square.size, (0, 0, 0, 0))
    mask = Image.new("L", square.size, 0)
    from PIL import ImageDraw

    draw = ImageDraw.Draw(mask)
    pad = int(square.size[0] * 0.02)
    draw.ellipse([pad, pad, square.size[0] - pad, square.size[1] - pad], fill=255)
    disc.paste(Image.new("RGBA", square.size, (24, 16, 20, 255)), (0, 0), mask)
    composed = Image.alpha_composite(disc, square)

    sizes = [16, 24, 32, 48, 64, 128, 256]
    composed.resize((256, 256), Image.Resampling.LANCZOS).save(
        ASSETS / "qinche.ico", sizes=[(s, s) for s in sizes])
    composed.resize((256, 256), Image.Resampling.LANCZOS).save(ASSETS / "icon_preview.png")
    print("icon written:", ASSETS / "qinche.ico")


if __name__ == "__main__":
    main()