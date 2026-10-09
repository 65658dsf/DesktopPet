"""Export the application's actual frame blends for visual QA, without settings."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from PySide6.QtCore import QSize
from PySide6.QtWidgets import QApplication
from petpack import DURATIONS, STATE_ROWS, _load_package
from pet_window import PetWindow, SpriteRenderer

LABELS = {
    "idle": "待机 · 眨眼", "running-right": "向右移动", "running-left": "向左移动",
    "waving": "挥手", "jumping": "跳跃", "failed": "故障", "waiting": "等待",
    "running": "忙碌", "review": "查看", "chin-rest": "托腮", "poke": "戳一戳",
}
SAMPLE_MS = 20


def duration_ms(value):
    """Random resting intervals use their midpoint, leaving action timing intact."""
    return round(sum(value) / 2) if isinstance(value, (list, tuple)) else value


def transition_ms(renderer, state, index, duration):
    legacy_blinks = {"idle": [1, 2, 3, 4], "review": [3], "poke": [2]}
    spec = (renderer.atlas.package.manifest.get("animationClips") or {}).get(state, {})
    blinking = index in spec.get("blinkFrames", legacy_blinks.get(state, []))
    return min(35 if blinking else 70, int(duration * 0.75))


def export_sequence(renderer, states, output, *, poke=False):
    output.mkdir(parents=True, exist_ok=True)
    (output / "keyframes").mkdir(parents=True, exist_ok=True)
    timings = renderer.atlas.clip_durations()
    frames = []
    poses = []
    segments = []
    previous = renderer.pixmap("idle", 0) if poke else renderer.pixmap(
        states[-1], renderer.atlas.frames(states[-1]) - 1)
    if poke:
        segments.append((previous, previous, 600, 0, "intro"))
    for state in states:
        for index, timing in enumerate(timings.get(state, DURATIONS.get(state, []))):
            duration = duration_ms(timing)
            target = renderer.pixmap(state, index)
            pose_name = f"keyframes/{index:02d}.png" if len(states) == 1 else f"keyframes/{state}-{index:02d}.png"
            if not target.save(str(output / pose_name)):
                raise RuntimeError(f"Cannot save {pose_name}")
            poses.append({"state": state, "index": index, "file": pose_name, "delay": duration})
            segments.append((previous, target, duration, transition_ms(renderer, state, index, duration),
                             f"{state}-{index}"))
            previous = target
    if poke:
        segments.append((previous, renderer.pixmap("idle", 0), 870, 70, "outro"))

    # Sampling the entire timeline at 20ms keeps cumulative timing accurate. A
    # short final transition slice must not become a 10ms GIF frame: browsers
    # frequently stretch those to 100ms, making a smooth animation look jerky.
    total = sum(segment[2] for segment in segments)
    sampled_total = max(SAMPLE_MS, round(total / SAMPLE_MS) * SAMPLE_MS)
    segment_index = 0
    segment_start = 0
    last_key = None
    for moment in range(0, sampled_total, SAMPLE_MS):
        while (segment_index < len(segments) - 1
               and moment >= segment_start + segments[segment_index][2]):
            segment_start += segments[segment_index][2]
            segment_index += 1
        start, target, duration, transition, identifier = segments[segment_index]
        elapsed = moment - segment_start
        if transition and elapsed < transition:
            progress = elapsed / transition
            pixmap = PetWindow._blend_frames(start, target, progress * progress * (3 - 2 * progress))
            key = (identifier, elapsed)
        else:
            pixmap = target
            key = (identifier, "hold")
        if key == last_key:
            frames[-1]["delay"] += SAMPLE_MS
        else:
            name = f"frame-{len(frames):04d}.png"
            if not pixmap.save(str(output / name)):
                raise RuntimeError(f"Cannot save {name}")
            frames.append({"file": name, "delay": SAMPLE_MS})
            last_key = key
    (output / "frames.json").write_text(json.dumps(frames, indent=2), encoding="utf-8")
    details = {
        "states": states, "width": previous.width(), "height": previous.height(),
        "durationMs": sampled_total, "sourceDurationMs": total,
        "frameCount": len(frames), "poses": poses,
        "timing": "Real clip durations; random resting ranges use their midpoint; sampled every 20ms.",
    }
    (output / "details.json").write_text(json.dumps(details, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Exported {len(frames)} blended frames ({sampled_total}ms) to {output}")
    return details


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--poke", action="store_true", help="Preview the interactive poke reaction")
    modes.add_argument("--all-states", action="store_true", help="Preview all nine menu states independently")
    args = parser.parse_args()
    app = QApplication([])
    package = _load_package(ROOT / "pets/qinche-q")
    if package is None:
        raise RuntimeError("Cannot load the QinChe package")
    renderer = SpriteRenderer(package)
    renderer.configure(QSize(192, 208), 2, False)
    if renderer.atlas.clip_errors:
        raise RuntimeError(f"Invalid animation clips: {renderer.atlas.clip_errors}")
    if args.all_states:
        output = ROOT / "build/qa-animation/all-states"
        output.mkdir(parents=True, exist_ok=True)
        states = []
        for state in STATE_ROWS:
            details = export_sequence(renderer, (state,), output / state)
            states.append({"state": state, "label": LABELS[state], "directory": state,
                           "animatedClip": state in renderer.atlas.clip_durations(), **details})
        manifest = {"pet": package.display_name, "states": states, "sampleMs": SAMPLE_MS}
        (output / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    else:
        resting_action = "chin-rest" if "chin-rest" in renderer.atlas.clip_durations() else "review"
        states = ("poke",) if args.poke else ("idle", resting_action)
        renderer.prepare_frames(["idle", *states])
        output = ROOT / "build/qa-animation" / ("poke" if args.poke else "smooth")
        export_sequence(renderer, states, output, poke=args.poke)
    app.quit()


if __name__ == "__main__":
    main()
