#!/usr/bin/env python3
"""Export 2x/1x atlases from a 4x Desktop Pet master and update pet.json.

Run with:
  wsl uv run --with pillow --with pydantic scripts/package_pet.py <pet-dir> --write-manifest
  wsl uv run --with pillow --with pydantic scripts/package_pet.py <pet-dir> --write-manifest --install-root ~/.codex/pets
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path

from PIL import Image
from pydantic import BaseModel, Field


FOUR_X_SIZE = (6144, 7488)
TWO_X_SIZE = (3072, 3744)
ONE_X_SIZE = (1536, 1872)


class PetManifest(BaseModel):
    id: str
    display_name: str = Field(alias="displayName")
    description: str
    spritesheet_path: str = Field(alias="spritesheetPath")


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "desktop-pet"


def read_manifest(path: Path) -> dict:
    if not path.is_file():
        raise SystemExit(f"missing manifest: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    PetManifest.model_validate(data)
    return data


def resize_master(master: Image.Image, target: tuple[int, int], output: Path) -> None:
    resized = master.resize(target, Image.Resampling.LANCZOS)
    resized.save(output, "WEBP", lossless=True, quality=100, method=6)


def package_pet(pet_dir: Path, write_manifest: bool, install_root: Path | None) -> dict:
    manifest_path = pet_dir / "pet.json"
    manifest = read_manifest(manifest_path)
    master_path = pet_dir / "spritesheet@4x.webp"

    if not master_path.is_file():
        raise SystemExit(f"missing 4x master: {master_path}")

    with Image.open(master_path) as opened:
        master = opened.convert("RGBA")
        if master.size != FOUR_X_SIZE:
            raise SystemExit(f"4x master is {master.size}, expected {FOUR_X_SIZE}: {master_path}")
        resize_master(master, TWO_X_SIZE, pet_dir / "spritesheet@2x.webp")
        resize_master(master, ONE_X_SIZE, pet_dir / "spritesheet.webp")

    manifest["id"] = slugify(str(manifest.get("id") or manifest.get("displayName") or "desktop-pet"))
    manifest["spritesheetPath"] = "spritesheet.webp"
    manifest["spritesheets"] = {
        "1x": "spritesheet.webp",
        "2x": "spritesheet@2x.webp",
        "4x": "spritesheet@4x.webp",
    }
    manifest["cellSize"] = {"width": 192, "height": 208}
    manifest["sourceScale"] = 4
    manifest.setdefault("pixelated", False)

    if write_manifest:
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    installed_to = None
    if install_root is not None:
        target_dir = install_root.expanduser().resolve() / manifest["id"]
        if target_dir.exists():
            shutil.rmtree(target_dir)
        shutil.copytree(
            pet_dir,
            target_dir,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store", "Thumbs.db"),
        )
        installed_to = str(target_dir)

    return {
        "ok": True,
        "pet_dir": str(pet_dir),
        "manifest_path": str(manifest_path),
        "wrote_manifest": write_manifest,
        "installed_to": installed_to,
        "outputs": [
            str(pet_dir / "spritesheet.webp"),
            str(pet_dir / "spritesheet@2x.webp"),
            str(pet_dir / "spritesheet@4x.webp"),
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pet_dir", type=Path)
    parser.add_argument("--write-manifest", action="store_true")
    parser.add_argument("--install-root", type=Path, help="Optional root folder to receive <pet-id>/")
    args = parser.parse_args()

    result = package_pet(args.pet_dir.expanduser().resolve(), args.write_manifest, args.install_root)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
