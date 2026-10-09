"""Visual QA of the packaged webp atlases (round-trip check of the real files).

Renders a comparison sheet: 4x cell vs 1x cell of the same frames, on a
checkerboard, so crispness and 1x readability can be judged by eye. Also prints
alpha statistics for used / unused cells of every scale.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(r"d:\Coding\DesktopPet")
PET_DIR = ROOT / "pets" / "qinche-q"
OUT = ROOT / "tools" / "gen_pet" / "out" / "qa_package_compare.png"

CELL_1X = (192, 208)
STATES = ["idle", "running-right", "running-left", "waving", "jumping",
          "failed", "waiting", "running", "review"]
SHOW = [("idle", 0), ("idle", 2), ("running-right", 3), ("jumping", 2),
        ("failed", 4), ("review", 2)]


def load(name: str) -> Image.Image:
    with Image.open(PET_DIR / name) as im:
        return im.convert("RGBA")


def checker(w, h, size=12):
    y, x = np.mgrid[0:h, 0:w]
    b = ((x // size) + (y // size)) % 2 == 0
    img = np.zeros((h, w, 3), np.uint8)
    img[b] = (226, 226, 230)
    img[~b] = (178, 178, 186)
    return img


def cell(atlas: Image.Image, scale: int, row: int, col: int) -> Image.Image:
    cw, ch = CELL_1X[0] * scale, CELL_1X[1] * scale
    return atlas.crop((col * cw, row * ch, (col + 1) * cw, (row + 1) * ch))


def audit(atlas: Image.Image, scale: int, label: str) -> None:
    frames = {"idle": 6, "running-right": 8, "running-left": 8, "waving": 4, "jumping": 5,
              "failed": 8, "waiting": 6, "running": 6, "review": 6}
    empty_used, dirty_unused = [], []
    for row, state in enumerate(STATES):
        for col in range(8):
            a = np.asarray(cell(atlas, scale, row, col))[..., 3]
            has = a.max() > 8
            if col < frames[state] and not has:
                empty_used.append(f"{state}[{col}]")
            if col >= frames[state] and has:
                dirty_unused.append(f"{state}[{col}] max={a.max()}")
    print(f"  {label}: empty used cells={empty_used or 'none'} / "
          f"dirty unused cells={dirty_unused or 'none'}")


def main() -> None:
    one = load("spritesheet.webp")
    two = load("spritesheet@2x.webp")
    four = load("spritesheet@4x.webp")
    print("atlas sizes:", one.size, two.size, four.size)
    audit(one, 1, "1x")
    audit(two, 2, "2x")
    audit(four, 4, "4x")

    view = (384, 416)
    pad, lab = 10, 46
    cols = len(SHOW)
    w = pad + cols * (view[0] + pad)
    h = lab * 2 + pad + 2 * view[1] + 3 * pad
    sheet = Image.new("RGB", (w, h), (26, 22, 26))
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.truetype("msyh.ttc", 18)

    for i, (state, frame) in enumerate(SHOW):
        row = STATES.index(state)
        x = pad + i * (view[0] + pad)
        y_top = lab * 2 + pad
        y_bot = y_top + view[1] + pad
        for src, scale, y, tag in ((four, 4, y_top, "4x"), (one, 1, y_bot, "1x")):
            c = cell(src, scale, row, frame).resize(view, Image.Resampling.LANCZOS
                                                    if scale > 1 else Image.Resampling.BICUBIC)
            board = checker(*view, 24)
            arr = np.asarray(c).astype(np.float32)
            a = arr[..., 3:4] / 255.0
            comp = (arr[..., :3] * a + board * (1 - a)).astype(np.uint8)
            sheet.paste(Image.fromarray(comp), (x, y))
            draw.rectangle([x - 1, y - 1, x + view[0], y + view[1]], outline=(96, 74, 84))
            draw.text((x, y - 24), f"{tag} {state}#{frame}", fill=(238, 210, 218), font=font)

    sheet.save(OUT)
    print("comparison sheet:", OUT)


if __name__ == "__main__":
    main()