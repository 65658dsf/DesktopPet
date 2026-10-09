"""Frame playback for the standard atlas and optional expressive clips."""

from __future__ import annotations

import math
import random
from collections.abc import Mapping, Sequence
from time import monotonic

from PySide6.QtCore import QObject, QTimer, Qt, Signal

from petpack import DURATIONS

FrameDuration = int | tuple[int, int]


class Animator(QObject):
    frame_changed = Signal(str, int)
    finished = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.timeout.connect(self._tick)
        self._deadline: float | None = None
        self.state = "idle"
        self.frame = 0
        self.speed = 1.0
        self.paused = False
        self.playing = False
        self._loop = True
        self._cycles_left = 1
        self._durations: dict[str, list[FrameDuration]] = {
            state: list(durations) for state, durations in DURATIONS.items()
        }
        self._frame_duration = self._durations["idle"][0]

    def set_clips(self, clips: Mapping[str, Sequence] | None = None) -> None:
        """Replace package timing overrides, retaining all standard states.

        Each item is a frame duration in milliseconds or a ``[min, max]``
        range. Ranges are sampled once on entering a frame, so a resting
        pose can linger naturally while eyelids still close quickly. Invalid
        third-party overrides are ignored and never replace built-in timing.
        """
        durations: dict[str, list[FrameDuration]] = {
            state: list(values) for state, values in DURATIONS.items()
        }
        for state, values in (clips or {}).items():
            if not isinstance(state, str) or not state or not isinstance(values, (list, tuple)):
                continue
            if not values or len(values) > 256:
                continue
            try:
                timings = [self._normalize_duration(value) for value in values]
            except (TypeError, ValueError, OverflowError):
                continue
            durations[state] = timings
        self._durations = durations
        if self.state not in durations:
            self.play("idle")
        else:
            self.frame = 0 if self.paused else min(self.frame, len(durations[self.state]) - 1)
            self._sample_duration()
            self._reset_deadline()
            if self.playing:
                self.frame_changed.emit(self.state, self.frame)
            self._schedule()

    @staticmethod
    def _normalize_duration(value) -> FrameDuration:
        def milliseconds(number) -> int:
            if isinstance(number, bool) or not isinstance(number, (int, float)):
                raise ValueError("frame duration must be numeric")
            if not math.isfinite(number) or not 30 <= number <= 60000:
                raise ValueError("frame duration outside 30–60000 ms")
            return int(round(number))

        if isinstance(value, (list, tuple)):
            if len(value) != 2:
                raise ValueError("duration range needs two endpoints")
            minimum, maximum = (milliseconds(number) for number in value)
            if minimum > maximum:
                raise ValueError("duration range is reversed")
            return minimum, maximum
        return milliseconds(value)

    def has_clip(self, state: str) -> bool:
        return state in self._durations

    def configure(self, speed: float = 1.0, paused: bool = False) -> None:
        self.speed = max(0.05, float(speed)) if math.isfinite(float(speed)) else 1.0
        self.paused = paused
        self._timer.stop()
        if paused:
            self._deadline = None
            # Reduced motion should rest on a neutral pose, not leave an eye
            # closed or a hand suspended halfway through an action.
            if self.frame != 0:
                self.frame = 0
                self._sample_duration()
                self.frame_changed.emit(self.state, 0)
        else:
            self._reset_deadline()
            self._schedule()

    def play(self, state: str, loop: bool = True, cycles: int = 1) -> None:
        if state not in self._durations:
            state = "idle"
        if state == self.state and loop and self.playing and self._loop:
            return                                    # keep the loop running
        self.stop()
        self.state = state
        self.frame = 0
        self._loop = loop
        self._cycles_left = max(1, cycles)
        self.playing = True
        self._sample_duration()
        self._reset_deadline()
        self.frame_changed.emit(state, 0)
        self._schedule()

    def stop(self) -> None:
        self._timer.stop()
        self.playing = False
        self._deadline = None

    def _duration_ms(self) -> float:
        return max(30.0, self._frame_duration / self.speed)

    def _reset_deadline(self) -> None:
        self._deadline = (monotonic() + self._duration_ms() / 1000
                          if self.playing and not self.paused else None)

    def transition_duration_ms(self) -> int:
        """Time left for displaying this frame, including playback speed."""
        if self.paused or not self.playing or self._deadline is None:
            return 0
        return max(0, int(round(min(self._duration_ms(),
                                    (self._deadline - monotonic()) * 1000))))

    def _schedule(self) -> None:
        if self.paused or not self.playing:
            return
        if self._deadline is None:
            self._reset_deadline()
        # The deadline is established before frame_changed: rendering and event
        # handling consume this frame's time instead of slowing every cycle.
        ms = (self._deadline - monotonic()) * 1000
        self._timer.start(max(1, int(round(ms))))

    def _sample_duration(self) -> None:
        duration = self._durations[self.state][self.frame]
        self._frame_duration = random.randint(*duration) if isinstance(duration, tuple) else duration

    def _tick(self) -> None:
        if self.paused or not self.playing:
            return
        now = monotonic()
        if self._deadline is None:
            self._reset_deadline()
        if now < self._deadline:
            self._schedule()
            return
        # Catch up only a few brief motion frames after a blocked event loop.
        # Emit once, and preserve long resting poses even after a suspend/resume.
        for advanced in range(4):
            count = len(self._durations[self.state])
            nxt = self.frame + 1
            if nxt >= count:
                if self._loop:
                    nxt = 0
                else:
                    self._cycles_left -= 1
                    if self._cycles_left <= 0:
                        self.playing = False
                        self._deadline = None
                        self.finished.emit(self.state)
                        return
                    nxt = 0
            self.frame = nxt
            self._sample_duration()
            duration = self._duration_ms() / 1000
            self._deadline += duration
            if self._deadline > now:
                break
            if self._frame_duration >= 500 or advanced == 3:
                self._deadline = now + duration
                break
        self.frame_changed.emit(self.state, self.frame)
        self._schedule()
