"""Build a Desktop Pet Launcher compatible 秦彻 Q版 pet package from image.png.

Pipeline:
  1. Matting   : remove the flat white background via multi-seed border flood fill,
                 reconstruct anti-aliased edges with a white-mixing alpha model.
  2. Animation : synthesise the 9 contract state rows with the exact contract
                 frame counts (idle 6 / running-right 8 / running-left 8 /
                 waving 4 / jumping 5 / failed 8 / waiting 6 / running 6 / review 6).
  3. Atlas     : compose the 4x master atlas 6144x7488 (8 cols x 9 rows, cell 768x832).
  4. QA        : contact sheet (1x), cutout preview, per-state GIFs, motion report.

Only the 4x master is produced here; 1x/2x + manifest are produced by the skill's
own scripts/package_pet.py, and validated by scripts/validate_pet_package.py.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(r"d:\Coding\DesktopPet")
SRC = ROOT / "image.png"
PET_DIR = ROOT / "pets" / "qinche-q"
OUT_DIR = ROOT / "tools" / "gen_pet" / "out"

# --- contract geometry -------------------------------------------------------
CELL_1X = (192, 208)
SCALE_X4 = 4
CELL_4X = (CELL_1X[0] * SCALE_X4, CELL_1X[1] * SCALE_X4)          # 768 x 832
ATLAS_4X = (CELL_4X[0] * 8, CELL_4X[1] * 9)                       # 6144 x 7488

# row order is fixed by the contract; frame counts are fixed too
STATES = [
    ("idle", 6),
    ("running-right", 8),
    ("running-left", 8),
    ("waving", 4),
    ("jumping", 5),
    ("failed", 8),
    ("waiting", 6),
    ("running", 6),
    ("review", 6),
]
STATE_FRAMES = dict(STATES)

# contract playback durations (ms), used for the QA GIFs
DURATIONS = {
    "idle": [280, 110, 110, 140, 140, 320],
    "running-right": [120] * 7 + [220],
    "running-left": [120] * 7 + [220],
    "waving": [140] * 3 + [280],
    "jumping": [140] * 4 + [280],
    "failed": [140] * 7 + [240],
    "waiting": [150] * 5 + [260],
    "running": [120] * 5 + [220],
    "review": [150] * 5 + [280],
}

CONTENT_H = 600.0        # 4x px, character height inside a 832px cell
BASE_TOP = 762.0         # 4x px, y of the character's bottom edge in the cell
SAFE_MARGIN = 6          # 4x px, content must stay this far from the cell border


# --------------------------------------------------------------------------- #
# stage 1: matting
# --------------------------------------------------------------------------- #
def dilate(mask: np.ndarray, rounds: int = 1) -> np.ndarray:
    out = mask.copy()
    for _ in range(rounds):
        grown = out.copy()
        grown[1:, :] |= out[:-1, :]
        grown[:-1, :] |= out[1:, :]
        grown[:, 1:] |= out[:, :-1]
        grown[:, :-1] |= out[:, 1:]
        out = grown
    return out


def bleed_colors(rgb: np.ndarray, seed: np.ndarray, rounds: int) -> np.ndarray:
    """Extend the colors of `seed` pixels outward (4-connected, no wrap-around)."""
    col = rgb.astype(np.float32).copy()
    filled = seed.copy()
    for _ in range(rounds):
        for axis, shift in ((0, 1), (0, -1), (1, 1), (1, -1)):
            sc = np.roll(col, shift, axis=axis)
            sf = np.roll(filled, shift, axis=axis)
            if axis == 0:
                edge = 0 if shift > 0 else -1
                sf[edge, :] = False
            else:
                edge = 0 if shift > 0 else -1
                sf[:, edge] = False
            take = (~filled) & sf
            col[take] = sc[take]
            filled |= take
    return col


def remove_white_background(rgb: np.ndarray) -> np.ndarray:
    """RGBA cutout: flood-fill the flat white background from every border seed,
    then rebuild anti-aliased edges with a white-mixing alpha model."""
    h, w, _ = rgb.shape
    cand = rgb.min(axis=2) >= 235
    reach = np.zeros_like(cand)
    reach[0, :] = cand[0, :]
    reach[-1, :] = cand[-1, :]
    reach[:, 0] = cand[:, 0]
    reach[:, -1] = cand[:, -1]

    iterations = 0
    while True:
        iterations += 1
        grown = dilate(reach) & cand
        if grown.sum() == reach.sum():
            break
        reach = grown
        if iterations > 5000:
            break
    bg = reach
    print(f"  matting: background {bg.mean() * 100:.1f}% of pixels "
          f"(fill converged in {iterations} passes)")

    # the 1px ring just outside the flat background holds the anti-aliased edge
    band = dilate(bg) & ~bg
    # nearest deep-interior colors, used to reverse the white mixing
    interior = ~dilate(bg, 2)
    fg = bleed_colors(rgb, interior, 6)

    denom = np.maximum(255.0 - fg, 1.0)
    frac = np.clip(((rgb.astype(np.float32) - fg) / denom).mean(axis=2), 0.0, 1.0)
    alpha = np.where(bg, 0.0, 1.0)
    alpha = np.where(band, 1.0 - frac, alpha)

    out_rgb = np.where(band[..., None], fg, rgb.astype(np.float32))
    out = np.dstack([np.clip(out_rgb, 0, 255), (alpha * 255.0).round()]).astype(np.uint8)
    return out


# --------------------------------------------------------------------------- #
# stage 2: per-state motion
# --------------------------------------------------------------------------- #
def state_motion(state: str, i: int, n: int):
    """Return (dx, dy, sx, sy, angle_deg) for frame i of n (4x px / degrees).

    dy is negative upwards. All motion is grounded in the single canonical base
    pose, so identity (face/outfit/palette/silhouette) cannot drift across rows.
    """
    p = 2.0 * math.pi * i / n
    dx = dy = 0.0
    sx = sy = 1.0
    ang = 0.0

    if state == "idle":                     # quiet breathing + micro sway
        ph = p + math.pi / 3
        sy = 1.0 + 0.020 * math.sin(ph)
        sx = 1.0 - 0.010 * math.sin(ph)
        dy = -14.0 * math.sin(ph)
        dx = 5.0 * math.sin(ph / 2.0)
        ang = 0.9 * math.sin(ph + math.pi / 6)
    elif state == "running-right":          # dragged right: lean + step bob
        bob = abs(math.sin(p * 2.0))
        dx = 10.0 * math.sin(p)
        dy = -16.0 * bob
        ang = 6.0 + 2.0 * math.sin(p * 2.0)
        sy = 1.0 + 0.012 * bob
    elif state == "running-left":           # dragged left: mirrored lean, unflipped art
        bob = abs(math.sin(p * 2.0))
        dx = -10.0 * math.sin(p)
        dy = -16.0 * bob
        ang = -6.0 - 2.0 * math.sin(p * 2.0)
        sy = 1.0 + 0.012 * bob
    elif state == "waving":                 # greeting sway
        ang = 5.5 * math.sin(p + math.pi / 4)
        dy = -12.0 * abs(math.sin(p))
        sx = 1.0 + 0.012 * math.sin(p * 2.0)
        sy = sx
    elif state == "jumping":                # crouch -> launch -> peak -> land
        keys = [
            (0.0, 16.0, 1.05, 0.94, 0.0),
            (0.0, -40.0, 0.96, 1.06, -1.0),
            (0.0, -92.0, 1.00, 1.03, -2.0),
            (0.0, -46.0, 0.99, 1.02, -1.0),
            (0.0, 12.0, 1.04, 0.95, 1.0),
        ]
        dx, dy, sx, sy, ang = keys[i % len(keys)]
    elif state == "failed":                 # slumped, desaturated, trembling
        ang = -4.5 + 1.0 * math.sin(p * 3.0)
        dy = 20.0 + 3.0 * math.sin(p * 4.0)
        dx = 2.5 * math.sin(p * 3.0)
        sy = 0.955
        sx = 1.02
    elif state == "waiting":                # expectant, calm small bob
        sy = 1.0 + 0.014 * math.sin(p)
        sx = 1.0 - 0.007 * math.sin(p)
        dy = -16.0 * math.sin(p)
        ang = 1.8 * math.sin(p + math.pi / 2.0)
    elif state == "running":                # focused task work: quick small bob
        bob = abs(math.sin(p * 2.0))
        dy = -13.0 * bob
        ang = 2.6 * math.sin(p * 2.0)
        sy = 1.0 + 0.015 * bob
    elif state == "review":                 # reading / checking: slow sway
        ang = 3.4 * math.sin(p)
        dy = -9.0 * math.sin(p + math.pi / 3.0)
        dx = 6.0 * math.sin(p)
        sy = 1.0 + 0.008 * math.sin(p * 2.0)
    return dx, dy, sx, sy, ang


def affine_coeffs(base_size, dx, dy, sx, sy, angle_deg):
    """Out -> base-image mapping for the pillow AFFINE transform."""
    bw, bh = base_size
    off = (CELL_4X[0] / 2.0 - bw / 2.0, BASE_TOP - bh)
    pivot = np.array([bw / 2.0, bh])
    th = math.radians(angle_deg)
    m = np.array([[math.cos(th) / sx, math.sin(th) / sx],
                  [-math.sin(th) / sy, math.cos(th) / sy]], dtype=np.float64)
    t = np.array([dx, dy], dtype=np.float64)
    n = pivot - m @ (t + np.array(off) + pivot)
    return (m[0, 0], m[0, 1], n[0], m[1, 0], m[1, 1], n[1])


def premultiply(rgba: np.ndarray) -> Image.Image:
    a = rgba[..., 3:4].astype(np.float32) / 255.0
    pm = np.dstack([rgba[..., :3].astype(np.float32) * a, rgba[..., 3:4].astype(np.float32)])
    return Image.fromarray(pm.astype(np.uint8), "RGBA")


def unpremultiply(im: Image.Image) -> np.ndarray:
    arr = np.asarray(im).astype(np.float32)
    a = arr[..., 3:4] / 255.0
    rgb = np.where(a > 1e-4, arr[..., :3] / np.maximum(a, 1e-4), 0.0)
    return np.dstack([np.clip(rgb, 0, 255), arr[..., 3]]).astype(np.uint8)


def render_frame(base_pm: Image.Image, dx, dy, sx, sy, ang, desaturate=False) -> np.ndarray:
    coeffs = affine_coeffs(base_pm.size, dx, dy, sx, sy, ang)
    cell = base_pm.transform(CELL_4X, Image.Transform.AFFINE, coeffs,
                             resample=Image.Resampling.BICUBIC)
    rgba = unpremultiply(cell)
    if desaturate:
        rgb = rgba[..., :3].astype(np.float32)
        gray = rgb @ np.array([0.299, 0.587, 0.114], dtype=np.float32)
        mix = 0.45 * rgb + 0.55 * gray[..., None]
        rgba[..., :3] = np.clip(mix * 0.94, 0, 255).astype(np.uint8)
    return rgba


def content_bbox(rgba: np.ndarray):
    a = rgba[..., 3]
    ys, xs = np.nonzero(a > 8)
    if len(xs) == 0:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())


# --------------------------------------------------------------------------- #
# QA helpers
# --------------------------------------------------------------------------- #
def checkerboard(w, h, size=16, light=(224, 224, 228), dark=(176, 176, 184)):
    y, x = np.mgrid[0:h, 0:w]
    board = np.where(((x // size) + (y // size)) % 2 == 0, 0, 1)
    img = np.zeros((h, w, 3), np.uint8)
    img[board == 0] = light
    img[board == 1] = dark
    return img


def over(img_rgba: np.ndarray, bg_rgb: np.ndarray) -> Image.Image:
    a = img_rgba[..., 3:4].astype(np.float32) / 255.0
    out = img_rgba[..., :3].astype(np.float32) * a + bg_rgb.astype(np.float32) * (1 - a)
    return Image.fromarray(out.round().astype(np.uint8), "RGB")


def label_font(size=22):
    for name in ("msyh.ttc", "msyhbd.ttc", "simhei.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def make_contact_sheet(frames: dict[str, list[np.ndarray]]) -> Image.Image:
    """1x contact sheet: the acceptance gate for character pets."""
    pad, lab = 8, 150
    cw, ch = CELL_1X
    w = lab + 8 * (cw + pad) + pad
    h = pad + 9 * (ch + pad)
    sheet = Image.new("RGB", (w, h), (28, 24, 28))
    font = label_font(20)
    draw = ImageDraw.Draw(sheet)
    for row, (state, _) in enumerate(STATES):
        y = pad + row * (ch + pad)
        draw.text((10, y + ch // 2 - 12), state, fill=(240, 214, 220), font=font)
        for col in range(8):
            x = lab + col * (cw + pad)
            cell = Image.fromarray(frames[state][col] if col < len(frames[state])
                                   else np.zeros((ch, cw, 4), np.uint8), "RGBA")
            cell = cell.resize((cw, ch), Image.Resampling.LANCZOS)
            board = checkerboard(cw, ch, 12)
            sheet.paste(over(np.asarray(cell), board), (x, y))
            draw.rectangle([x - 1, y - 1, x + cw, y + ch], outline=(90, 70, 80))
    return sheet


def make_gif(frames: list[np.ndarray], durations: list[int], cell, bg, path: Path):
    board = checkerboard(cell[0], cell[1], 14) if bg == "checker" else None
    outs = []
    for f in frames:
        im = Image.fromarray(f, "RGBA").resize(cell, Image.Resampling.LANCZOS)
        background = board if board is not None else np.full((cell[1], cell[0], 3), bg, np.uint8)
        outs.append(over(np.asarray(im), background))
    outs[0].save(path, save_all=True, append_images=outs[1:], duration=durations,
                 loop=0, disposal=2, optimize=False)
    print(f"  gif: {path.name} ({len(outs)} frames)")


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    PET_DIR.mkdir(parents=True, exist_ok=True)

    print("stage 1: matting")
    src = Image.open(SRC).convert("RGB")
    cut = remove_white_background(np.asarray(src))
    ys, xs = np.nonzero(cut[..., 3] > 8)
    cut = cut[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    ch, cw = cut.shape[:2]
    print(f"  cutout: {cw}x{ch}")

    board = checkerboard(cw, ch, 20)
    over(cut, board).save(OUT_DIR / "qa_cutout.png")

    base_h = int(round(CONTENT_H))
    base_w = int(round(cw * CONTENT_H / ch))
    base_pm = premultiply(cut).resize((base_w, base_h), Image.Resampling.LANCZOS)
    print(f"  base sprite at 4x: {base_w}x{base_h} (placed bottom-center, y={BASE_TOP:.0f})")

    print("stage 2: frames")
    frames: dict[str, list[np.ndarray]] = {}
    report = {}
    for state, n in STATES:
        strip = []
        for i in range(n):
            dx, dy, sx, sy, ang = state_motion(state, i, n)
            strip.append(render_frame(base_pm, dx, dy, sx, sy, ang,
                                      desaturate=(state == "failed")))
        frames[state] = strip
        boxes = [content_bbox(f) for f in strip]
        xs_min = min(b[0] for b in boxes); ys_min = min(b[1] for b in boxes)
        xs_max = max(b[2] for b in boxes); ys_max = max(b[3] for b in boxes)
        spans = []
        for i in range(1, len(strip)):
            prev_a = strip[i - 1][..., 3]
            cur_a = strip[i][..., 3]
            vis = (prev_a > 8) | (cur_a > 8)
            diff = np.abs(strip[i].astype(np.int16) - strip[i - 1].astype(np.int16))
            spans.append((float(diff[vis].mean()) if vis.any() else 0.0,
                          float((diff[vis] > 8).mean() * 100.0) if vis.any() else 0.0))
        report[state] = dict(frames=n, x=(xs_min, xs_max), y=(ys_min, ys_max),
                             delta_mean=round(float(np.mean([s[0] for s in spans])), 2),
                             moved_pct=round(float(np.mean([s[1] for s in spans])), 2))
        ok = (xs_min >= SAFE_MARGIN and ys_min >= SAFE_MARGIN
              and xs_max <= CELL_4X[0] - SAFE_MARGIN and ys_max <= CELL_4X[1] - SAFE_MARGIN)
        print(f"  {state:<14} frames={n} bbox=x[{xs_min},{xs_max}] y[{ys_min},{ys_max}] "
              f"delta(mean {report[state]['delta_mean']}, moved {report[state]['moved_pct']}%) "
              f"{'OK' if ok else '!! OUT OF SAFE AREA'}")

    print("stage 3: atlas")
    atlas = np.zeros((ATLAS_4X[1], ATLAS_4X[0], 4), np.uint8)
    for row, (state, _) in enumerate(STATES):
        for col, frame in enumerate(frames[state]):
            y0, x0 = row * CELL_4X[1], col * CELL_4X[0]
            atlas[y0:y0 + CELL_4X[1], x0:x0 + CELL_4X[0]] = frame
    master = PET_DIR / "spritesheet@4x.webp"
    Image.fromarray(atlas, "RGBA").save(master, "WEBP", quality=95, method=6)
    print(f"  4x master: {master} ({master.stat().st_size / 1e6:.1f} MB)")

    print("stage 4: QA artifacts")
    make_contact_sheet(frames).save(OUT_DIR / "qa_contact_1x.png")
    make_gif(frames["idle"], DURATIONS["idle"], CELL_1X, "checker", OUT_DIR / "qa_idle_1x.gif")
    make_gif(frames["jumping"], DURATIONS["jumping"], CELL_1X, "checker", OUT_DIR / "qa_jump_1x.gif")
    make_gif(frames["running-right"], DURATIONS["running-right"], CELL_1X, "checker",
             OUT_DIR / "qa_runright_1x.gif")

    # gallery previews (dark elegant background)
    prev_bg = np.full((CELL_1X[1] * 2, CELL_1X[0] * 2, 3), 0, np.uint8)
    prev_bg[:] = np.array([26, 20, 24], np.uint8)
    preview = Image.fromarray(frames["idle"][0], "RGBA").resize(
        (CELL_1X[0] * 2, CELL_1X[1] * 2), Image.Resampling.LANCZOS)
    over(np.asarray(preview), prev_bg).save(PET_DIR / "preview.png")
    make_gif(frames["idle"] + frames["waving"], DURATIONS["idle"] + DURATIONS["waving"],
             (CELL_1X[0] * 2, CELL_1X[1] * 2), (26, 20, 24), PET_DIR / "preview.gif")

    write_manifest()
    (OUT_DIR / "motion_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    (OUT_DIR / "qa_contact_1x.png").exists() and print(f"  contact sheet: {OUT_DIR / 'qa_contact_1x.png'}")


def write_manifest() -> None:
    manifest = {
        "id": "qinche-q",
        "name": "秦彻",
        "displayName": "秦彻",
        "description": "《恋与深空》秦彻 Q版桌宠（同人二次创作，仅供个人使用）",
        "spritesheetPath": "spritesheet.webp",
        "spritesheets": {
            "1x": "spritesheet.webp",
            "2x": "spritesheet@2x.webp",
            "4x": "spritesheet@4x.webp",
        },
        "cellSize": {"width": 192, "height": 208},
        "sourceScale": 4,
        "pixelated": False,
        "version": "1.0.0",
        "author": "DesktopPet (fan art)",
        "tags": ["恋与深空", "秦彻", "Q版", "chibi"],
        "license": "Fan Art - Personal Use Only",
        "preview": "preview.png",
        "format": "atlas-8x9",
        "resolution": "192x208",
        "createdAt": "2026-10-08",
    }
    (PET_DIR / "pet.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (PET_DIR / "README.md").write_text(README, encoding="utf-8")
    (PET_DIR / "LICENSE").write_text(LICENSE, encoding="utf-8")
    print(f"  manifest: {PET_DIR / 'pet.json'}")


README = """# 秦彻 · Q版桌面宠物

《恋与深空》秦彻 Q版桌宠，兼容 Desktop Pet Launcher 宠物包格式。

## 包内容

- `pet.json` — 清单（8x9 图集 / 192x208 单元格 / 1x·2x·4x）
- `spritesheet.webp` — 1x 兼容图集 `1536x1872`
- `spritesheet@2x.webp` — 2x 图集 `3072x3744`
- `spritesheet@4x.webp` — 4x master `6144x7488`
- `preview.png` / `preview.gif` — 预览

## 状态行

| 行 | 状态 | 帧数 |
| --- | --- | ---: |
| 0 | idle | 6 |
| 1 | running-right | 8 |
| 2 | running-left | 8 |
| 3 | waving | 4 |
| 4 | jumping | 5 |
| 5 | failed | 8 |
| 6 | waiting | 6 |
| 7 | running | 6 |
| 8 | review | 6 |

未使用的单元格保持完全透明。

## 安装

复制 `qinche-q/` 到 `%USERPROFILE%\\.codex\\pets\\`，或在启动器设置中添加自定义宠物目录。

## 声明

同人二次创作，仅限个人欣赏使用，不得用于商业用途。角色版权归《恋与深空》权利方所有。
"""

LICENSE = """Fan Art - Personal Use Only

本桌宠素材为《恋与深空》秦彻的粉丝二次创作（Q版化处理与程序化动画）。
仅允许个人、非商业用途的欣赏与本地使用；不得再分发用于商业目的。
原角色及相关知识产权归权利方所有。
"""


if __name__ == "__main__":
    main()