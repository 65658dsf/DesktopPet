#!/usr/bin/env python3
"""Validate a Desktop Pet package.

Run with:
  wsl uv run --with pillow --with pydantic scripts/validate_pet_package.py <pet-dir>
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from PIL import Image
from pydantic import BaseModel, Field, ValidationError


EXPECTED_SIZES = {
    "1x": (1536, 1872),
    "2x": (3072, 3744),
    "4x": (6144, 7488),
}

STATE_FRAMES = {
    "idle": 6,
    "running-right": 8,
    "running-left": 8,
    "waving": 4,
    "jumping": 5,
    "failed": 8,
    "waiting": 6,
    "running": 6,
    "review": 6,
}


class CellSize(BaseModel):
    width: int = 192
    height: int = 208


class SpriteSheets(BaseModel):
    one_x: str = Field(alias="1x")
    two_x: str | None = Field(default=None, alias="2x")
    four_x: str | None = Field(default=None, alias="4x")


class PetManifest(BaseModel):
    id: str
    display_name: str = Field(alias="displayName")
    description: str
    spritesheet_path: str = Field(alias="spritesheetPath")
    spritesheets: SpriteSheets | None = None
    cell_size: CellSize = Field(default_factory=CellSize, alias="cellSize")
    source_scale: int = Field(default=1, alias="sourceScale")
    pixelated: bool = False


def image_info(path: Path) -> dict[str, Any]:
    with Image.open(path) as image:
        return {
            "path": str(path),
            "size": [image.width, image.height],
            "mode": image.mode,
            "format": image.format,
            "has_alpha": image.mode in {"RGBA", "LA"} or "transparency" in image.info,
        }


def validate_image(path: Path, scale: str, errors: list[str], warnings: list[str]) -> dict[str, Any] | None:
    if not path.is_file():
        errors.append(f"missing {scale} spritesheet: {path}")
        return None

    try:
        info = image_info(path)
    except Exception as error:  # noqa: BLE001
        errors.append(f"cannot open {scale} spritesheet {path}: {error}")
        return None

    expected = EXPECTED_SIZES[scale]
    if tuple(info["size"]) != expected:
        errors.append(f"{scale} spritesheet is {info['size']}, expected {list(expected)}: {path}")
    if not info["has_alpha"]:
        warnings.append(f"{scale} spritesheet does not advertise alpha: {path}")
    else:
        inspect_atlas_cells(path, scale, errors, warnings)
    return info


def inspect_atlas_cells(path: Path, scale: str, errors: list[str], warnings: list[str]) -> None:
    scale_factor = int(scale[0])
    cell_width = 192 * scale_factor
    cell_height = 208 * scale_factor

    with Image.open(path) as opened:
        image = opened.convert("RGBA")
        alpha = image.getchannel("A")

        for row_index, (state, used_frames) in enumerate(STATE_FRAMES.items()):
            for column in range(8):
                box = (
                    column * cell_width,
                    row_index * cell_height,
                    (column + 1) * cell_width,
                    (row_index + 1) * cell_height,
                )
                cell_alpha = alpha.crop(box)
                has_pixels = cell_alpha.getbbox() is not None
                cell_name = f"{scale} {state} row {row_index} col {column}"
                if column < used_frames and not has_pixels:
                    errors.append(f"{cell_name} is empty")
                if column >= used_frames and has_pixels:
                    warnings.append(f"{cell_name} should be transparent because the frame is unused")


def validate_package(pet_dir: Path) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    manifest_path = pet_dir / "pet.json"

    if not manifest_path.is_file():
        return {"ok": False, "errors": [f"missing manifest: {manifest_path}"], "warnings": []}

    try:
        manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest = PetManifest.model_validate(manifest_data)
    except (json.JSONDecodeError, ValidationError) as error:
        return {"ok": False, "errors": [f"invalid manifest: {error}"], "warnings": []}

    spritesheets = manifest.spritesheets or SpriteSheets.model_validate({"1x": manifest.spritesheet_path})
    discovered = {
        "1x": spritesheets.one_x,
        "2x": spritesheets.two_x,
        "4x": spritesheets.four_x,
    }

    image_results: dict[str, Any] = {}
    for scale, relative in discovered.items():
        if relative is None:
            continue
        result = validate_image(pet_dir / relative, scale, errors, warnings)
        if result:
            image_results[scale] = result

    if manifest.spritesheet_path != discovered["1x"]:
        errors.append("spritesheetPath must point to the 1x compatibility atlas")
    if manifest.cell_size.width != 192 or manifest.cell_size.height != 208:
        errors.append("cellSize must remain the 1x logical cell size 192x208")
    if discovered["4x"] and manifest.source_scale < 4:
        warnings.append("4x atlas exists but sourceScale is less than 4")
    if not discovered["4x"]:
        warnings.append("package is legacy-compatible only; no 4x master declared")

    return {
        "ok": not errors,
        "pet_dir": str(pet_dir),
        "manifest": manifest_data,
        "images": image_results,
        "errors": errors,
        "warnings": warnings,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pet_dir", type=Path)
    args = parser.parse_args()

    result = validate_package(args.pet_dir.expanduser().resolve())
    print(json.dumps(result, indent=2, ensure_ascii=False))
    raise SystemExit(0 if result["ok"] else 1)


if __name__ == "__main__":
    main()
