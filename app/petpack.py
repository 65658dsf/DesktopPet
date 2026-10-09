"""Pet package discovery / loading, following the launcher contract.

Scan roots:
  %USERPROFILE%\\.codex\\pets\\<pet-id>\\
  %APPDATA%\\top.nether.pet\\pets\\<pet-id>\\
  <app folder>\\pets\\<pet-id>\\
  user configured `petFolders` (a folder of packages, or a package folder itself)

Atlas scale selection: smallest available scale that is at least
`max(window_width / 192, window_height / 208) * devicePixelRatio`.
"""

from __future__ import annotations

import json
import logging
import math
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPainter

CELL = (192, 208)

STATE_ROWS = ["idle", "running-right", "running-left", "waving", "jumping",
              "failed", "waiting", "running", "review"]
STATE_FRAMES = {"idle": 6, "running-right": 8, "running-left": 8, "waving": 4,
                "jumping": 5, "failed": 8, "waiting": 6, "running": 6, "review": 6}

# contract playback durations (ms) — first value is frame 0
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

SCALE_KEYS = {1: "1x", 2: "2x", 4: "4x"}
DEFAULT_SHEETS = {1: "spritesheet.webp", 2: "spritesheet@2x.webp", 4: "spritesheet@4x.webp"}


@dataclass
class PetPackage:
    root: Path
    manifest: dict

    @property
    def id(self) -> str:
        return str(self.manifest.get("id") or self.root.name)

    @property
    def display_name(self) -> str:
        return str(self.manifest.get("displayName") or self.manifest.get("name") or self.id)

    @property
    def description(self) -> str:
        return str(self.manifest.get("description") or "")

    @property
    def cell(self) -> tuple[int, int]:
        cell = self.manifest.get("cellSize") or {}
        return int(cell.get("width", CELL[0])), int(cell.get("height", CELL[1]))

    @property
    def pixelated(self) -> bool:
        return bool(self.manifest.get("pixelated", False))

    def sheet_path(self, scale: int) -> Path | None:
        sheets = self.manifest.get("spritesheets") or {}
        name = sheets.get(SCALE_KEYS[scale])
        target = self.root / (name or DEFAULT_SHEETS[scale])
        if name and target.is_file():
            return target
        # fall back to 1x compatibility path when a high-res sheet is missing
        compat = self.root / str(self.manifest.get("spritesheetPath") or DEFAULT_SHEETS[1])
        return compat if compat.is_file() else None

    def available_scales(self) -> list[int]:
        sheets = self.manifest.get("spritesheets") or {}
        scales = [s for s in (4, 2, 1) if (sheets.get(SCALE_KEYS[s]) or (s == 1))]
        scales = [s for s in scales if self.sheet_path(s) is not None]
        return scales or [1]

    def choose_scale(self, required: float) -> int:
        for scale in sorted(self.available_scales()):
            if scale >= required:
                return scale
        return max(self.available_scales())

    def animation_path(self, name: str) -> Path:
        """Resolve an optional clip inside this package, including symlink checks."""
        if not isinstance(name, str) or not name:
            raise ValueError("clip spritesheetPath must be a relative filename")
        relative = Path(name)
        if relative.is_absolute() or relative.drive or ".." in relative.parts:
            raise ValueError("clip spritesheetPath must remain inside the package")
        target = (self.root / relative).resolve()
        if not target.is_relative_to(self.root.resolve()) or not target.is_file():
            raise ValueError("clip spritesheet is missing or outside the package")
        return target


def scan_roots(extra_folders: list[str] | None = None) -> list[Path]:
    roots: list[Path] = []
    home = Path(os.environ.get("USERPROFILE", Path.home()))
    roots.append(home / ".codex" / "pets")
    appdata = os.environ.get("APPDATA")
    if appdata:
        roots.append(Path(appdata) / "top.nether.pet" / "pets")
    exe_dir = Path(sys.argv[0]).resolve().parent
    roots.append(exe_dir / "pets")
    roots.append(Path(__file__).resolve().parent.parent / "pets")   # dev tree
    bundled = getattr(sys, "_MEIPASS", None)                        # frozen exe payload
    if bundled:
        roots.append(Path(bundled) / "bundled_pets")
    for folder in extra_folders or []:
        if folder:
            roots.append(Path(folder).expanduser())
    seen, unique = set(), []
    for root in roots:
        key = str(root).lower()
        if key not in seen:
            seen.add(key)
            unique.append(root)
    return unique


def _load_package(root: Path) -> PetPackage | None:
    manifest_path = root / "pet.json"
    if not manifest_path.is_file():
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(manifest, dict):
        return None
    pkg = PetPackage(root=root, manifest=manifest)
    return pkg if pkg.sheet_path(1) is not None else None


def scan_packages(extra_folders: list[str] | None = None) -> list[PetPackage]:
    found: dict[str, PetPackage] = {}
    for root in scan_roots(extra_folders):
        if not root.is_dir():
            continue
        if (root / "pet.json").is_file():                 # a package folder itself
            pkg = _load_package(root)
            if pkg:
                found.setdefault(pkg.id, pkg)
            continue
        try:
            children = sorted(p for p in root.iterdir() if p.is_dir())
        except OSError:
            continue
        for child in children:
            pkg = _load_package(child)
            if pkg:
                found.setdefault(pkg.id, pkg)
    return list(found.values())


@dataclass
class AnimationClip:
    """Frames retain their source pixels on a common, transparent logical canvas."""

    images: list[QImage]
    durations: list[int | tuple[int, int]]


class Atlas:
    """Loads the standard atlas plus optional, independently authored action clips."""

    def __init__(self, package: PetPackage, scale: int) -> None:
        self.package = package
        self.scale = scale
        path = package.sheet_path(scale)
        if path is None:
            raise FileNotFoundError(f"no spritesheet for {package.id}")
        self.path = path
        self.image = self._load(path)
        if self.image.isNull():
            raise ValueError(f"cannot decode {path}")
        self._clips: dict[str, AnimationClip] = {}
        self.clip_errors: dict[str, str] = {}
        clips = package.manifest.get("animationClips") or {}
        if isinstance(clips, dict):
            for state, spec in clips.items():
                if not isinstance(state, str) or not state:
                    continue
                try:
                    self._clips[state] = self._load_clip(state, spec)
                except (OSError, TypeError, ValueError, OverflowError) as exc:
                    self.clip_errors[state] = str(exc)
                    logging.getLogger(__name__).warning("Ignoring %s animation clip: %s", state, exc)

    @staticmethod
    def _load(path: Path) -> QImage:
        image = QImage(str(path))
        if not image.isNull():
            return image.convertToFormat(QImage.Format.Format_RGBA8888)
        # Qt without a webp plugin: fall back to Pillow -> PNG bytes
        try:
            from PIL import Image as PILImage
            import io

            buf = io.BytesIO()
            with PILImage.open(path) as im:
                im.convert("RGBA").save(buf, "PNG")
            return QImage.fromData(buf.getvalue(), "PNG").convertToFormat(
                QImage.Format.Format_RGBA8888)
        except Exception:
            return QImage()

    def frames(self, state: str) -> int:
        if state in self._clips:
            return len(self._clips[state].images)
        return STATE_FRAMES.get(state, 6)

    def clip_durations(self) -> dict[str, list[int | tuple[int, int]]]:
        """Only accepted clips may override playback timing and frame counts."""
        return {state: list(clip.durations) for state, clip in self._clips.items()}

    @staticmethod
    def _integer(value, minimum: int, maximum: int, name: str) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
            raise ValueError(f"{name} must be an integer from {minimum} to {maximum}")
        return value

    @staticmethod
    def _duration(value) -> int | tuple[int, int]:
        def milliseconds(number) -> int:
            if isinstance(number, bool) or not isinstance(number, (int, float)):
                raise ValueError("clip durations must be numeric")
            if not math.isfinite(number) or not 30 <= number <= 60000:
                raise ValueError("clip duration outside 30–60000 ms")
            return round(number)

        if isinstance(value, (list, tuple)):
            if len(value) != 2:
                raise ValueError("clip duration range needs two endpoints")
            lower, upper = map(milliseconds, value)
            if lower > upper:
                raise ValueError("clip duration range is reversed")
            return lower, upper
        return milliseconds(value)

    @staticmethod
    def _alpha_bounds(image: QImage) -> tuple[int, int, int, int]:
        from PIL import Image as PILImage

        source = PILImage.frombytes("RGBA", (image.width(), image.height()),
                                    bytes(image.constBits()), "raw", "RGBA", image.bytesPerLine())
        bounds = source.getchannel("A").point([0] * 32 + [255] * 224).getbbox()
        if bounds is None:
            raise ValueError("clip contains an empty frame")
        left, top, right, bottom = bounds
        return left, top, right - left, bottom - top

    def _load_clip(self, state: str, spec: dict) -> AnimationClip:
        if not isinstance(spec, dict):
            raise ValueError("clip definition must be an object")
        path = self.package.animation_path(spec.get("spritesheetPath"))
        sheet = self._load(path)
        if sheet.isNull():
            raise ValueError("cannot decode clip spritesheet")
        count = self._integer(spec.get("frameCount", STATE_FRAMES.get(state, 6)), 1, 256, "frameCount")
        columns = self._integer(spec.get("columns", count), 1, 256, "columns")
        explicit_frames = spec.get("frames")
        if explicit_frames is not None and (not isinstance(explicit_frames, list) or len(explicit_frames) != count):
            raise ValueError("clip frames must match frameCount")
        rows = math.ceil(count / columns)
        crops: list[QImage] = []
        for index in range(count):
            if explicit_frames is not None:
                entry = explicit_frames[index]
                rect = entry.get("rect") if isinstance(entry, dict) else None
                if not isinstance(rect, (list, tuple)) or len(rect) != 4:
                    raise ValueError("each clip frame needs rect: [x, y, width, height]")
                x, y, width, height = [self._integer(n, 0, 32768, "frame coordinate") for n in rect]
            else:
                column, row = index % columns, index // columns
                x, y = column * sheet.width() // columns, row * sheet.height() // rows
                width = (column + 1) * sheet.width() // columns - x
                height = (row + 1) * sheet.height() // rows - y
            if width <= 0 or height <= 0 or x + width > sheet.width() or y + height > sheet.height():
                raise ValueError("clip frame lies outside its spritesheet")
            frame = sheet.copy(x, y, width, height)
            crops.append(frame.copy(*self._alpha_bounds(frame)))

        raw_durations = spec.get("durations", DURATIONS.get(state, [150] * count))
        if not isinstance(raw_durations, (list, tuple)) or len(raw_durations) != count:
            raise ValueError("clip durations must match frameCount")
        durations = [self._duration(value) for value in raw_durations]
        cw, ch = self.package.cell
        raw_offsets = spec.get("offsets", [[0, 0]] * count)
        if not isinstance(raw_offsets, (list, tuple)) or len(raw_offsets) != count:
            raise ValueError("clip offsets must match frameCount")
        offsets: list[tuple[float, float]] = []
        for offset in raw_offsets:
            if not isinstance(offset, (list, tuple)) or len(offset) != 2:
                raise ValueError("each clip offset needs [x, y] in logical cell units")
            for value, limit in zip(offset, (cw, ch)):
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise ValueError("clip offsets must be numeric")
                if not math.isfinite(value) or not -limit <= value <= limit:
                    raise ValueError("clip offset lies outside the logical cell")
            offsets.append((float(offset[0]), float(offset[1])))

        def dimension(name: str, default: float, maximum: float) -> float:
            value = spec.get(name, default)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"clip {name} must be numeric")
            if not math.isfinite(value) or not 0 < value <= maximum:
                raise ValueError(f"clip {name} lies outside the logical cell")
            return float(value)

        baseline = dimension("baseline", ch - 18, ch)
        content_height = dimension("contentHeight", min(150, baseline), baseline)
        content_width = max(1, cw - 12)
        density = max(max(image.height() for image in crops) / content_height,
                      max(image.width() for image in crops) / content_width)
        # Keep the exact logical aspect ratio at the nearest native raster size.
        # Every frame shares this scale; eyelids/arms cannot change the pet's size.
        divisor = math.gcd(cw, ch)
        multiplier = max(1, math.ceil(density * divisor))
        density = multiplier / divisor
        canvas_width, canvas_height = cw // divisor * multiplier, ch // divisor * multiplier
        frames = []
        for crop, (offset_x, offset_y) in zip(crops, offsets):
            # Source crops keep native pixels. Logical offsets restore authored
            # motion such as jump height after the common baseline alignment.
            x = (canvas_width - crop.width()) // 2 + round(offset_x * density)
            y = round((baseline + offset_y) * density) - crop.height()
            if x < 0 or y < 0 or x + crop.width() > canvas_width or y + crop.height() > canvas_height:
                raise ValueError("clip offset would crop a frame outside the logical cell")
            image = QImage(canvas_width, canvas_height, QImage.Format.Format_RGBA8888)
            image.fill(Qt.GlobalColor.transparent)
            painter = QPainter(image)
            painter.drawImage(x, y, crop)
            painter.end()
            frames.append(image)
        return AnimationClip(frames, durations)

    def cell_image(self, state: str, index: int) -> QImage:
        count = self.frames(state)
        index = max(0, min(index, count - 1))
        if state in self._clips:
            return QImage(self._clips[state].images[index])
        if state not in STATE_ROWS:
            state = "idle"
        row = STATE_ROWS.index(state)
        cw, ch = self.package.cell
        cw *= self.scale
        ch *= self.scale
        return self.image.copy(index * cw, row * ch, cw, ch)
