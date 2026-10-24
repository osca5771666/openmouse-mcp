from __future__ import annotations

import math
import random
import time
import threading
from dataclasses import dataclass


@dataclass(frozen=True)
class Point:
    x: float
    y: float


@dataclass(frozen=True)
class TrajectoryStep:
    point: Point
    delay: float


def ease_in_out_cubic(t: float) -> float:
    if t < 0.5:
        return 4.0 * t * t * t
    return 1.0 - pow(-2.0 * t + 2.0, 3.0) / 2.0


def cubic_bezier(p0: Point, p1: Point, p2: Point, p3: Point, t: float) -> Point:
    u = 1.0 - t
    x = (
        (u**3) * p0.x
        + 3 * (u**2) * t * p1.x
        + 3 * u * (t**2) * p2.x
        + (t**3) * p3.x
    )
    y = (
        (u**3) * p0.y
        + 3 * (u**2) * t * p1.y
        + 3 * u * (t**2) * p2.y
        + (t**3) * p3.y
    )
    return Point(x, y)


def build_trajectory(
    start: Point,
    end: Point,
    rng: random.Random | None = None,
    speed_profile: str = "balanced",
) -> list[TrajectoryStep]:
    """Return a timed cubic-Bezier path with mild jitter and one possible pause."""
    rng = rng or random.Random()
    dx = end.x - start.x
    dy = end.y - start.y
    distance = math.hypot(dx, dy)
    if distance < 0.5:
        return [TrajectoryStep(Point(end.x, end.y), 0.0)]

    length = max(distance, 1.0)
    perp_x = -dy / length
    perp_y = dx / length
    bend_1 = rng.uniform(-0.13, 0.13) * min(distance, 650)
    bend_2 = rng.uniform(-0.13, 0.13) * min(distance, 650)
    p1 = Point(start.x + dx * 0.27 + perp_x * bend_1, start.y + dy * 0.27 + perp_y * bend_1)
    p2 = Point(start.x + dx * 0.73 + perp_x * bend_2, start.y + dy * 0.73 + perp_y * bend_2)

    if speed_profile == "fast":
        duration = min(
            0.38,
            max(0.1, 0.06 + distance / 3200.0 + rng.uniform(-0.01, 0.025)),
        )
        steps = max(10, min(36, int(duration * (105 + rng.uniform(-12, 12)))))
        pause_probability = 0.38
        pause_min, pause_max = 0.012, 0.045
        jitter_cap = 0.85
        jitter_divisor = 1200.0
    elif speed_profile == "human":
        duration = min(
            1.35,
            max(0.32, 0.24 + distance / 1300.0 + rng.uniform(-0.05, 0.1)),
        )
        steps = max(22, min(82, int(duration * (58 + rng.uniform(-8, 8)))))
        pause_probability = 0.8
        pause_min, pause_max = 0.05, 0.16
        jitter_cap = 1.45
        jitter_divisor = 850.0
    else:
        duration = min(1.1, max(0.24, 0.2 + distance / 1500.0 + rng.uniform(-0.04, 0.08)))
        steps = max(18, min(72, int(duration * (55 + rng.uniform(-8, 8)))))
        pause_probability = 0.72
        pause_min, pause_max = 0.035, 0.14
        jitter_cap = 1.35
        jitter_divisor = 950.0
    pause_at = rng.randint(max(6, steps // 3), max(7, (steps * 3) // 5))
    pause_duration = (
        rng.uniform(pause_min, pause_max) if rng.random() < pause_probability else 0.0
    )
    jitter_scale = min(jitter_cap, 0.2 + distance / jitter_divisor)
    phase = rng.uniform(0, math.tau)

    points: list[TrajectoryStep] = []
    previous_time = 0.0
    for index in range(1, steps + 1):
        raw_t = index / steps
        t = ease_in_out_cubic(raw_t)
        point = cubic_bezier(start, p1, p2, end, t)
        taper = math.sin(math.pi * t)
        wobble = math.sin(t * math.tau * rng.uniform(2.2, 3.4) + phase)
        jitter_x = rng.uniform(-jitter_scale, jitter_scale) * taper
        jitter_y = rng.uniform(-jitter_scale, jitter_scale) * taper
        point = Point(point.x + jitter_x + wobble * 0.22, point.y + jitter_y)

        target_time = duration * raw_t
        if index == pause_at and pause_duration:
            target_time += pause_duration
        delay = max(0.0, target_time - previous_time)
        points.append(TrajectoryStep(point, delay))
        previous_time = target_time

    points[-1] = TrajectoryStep(Point(end.x, end.y), points[-1].delay)
    return points


def random_action_delay(
    minimum: float = 0.2,
    maximum: float = 1.3,
    rng: random.Random | None = None,
) -> float:
    rng = rng or random.Random()
    return rng.uniform(minimum, maximum)


def wait_cancellable(
    seconds: float,
    cancel_event: threading.Event,
    interval: float = 0.02,
) -> None:
    if seconds <= 0:
        return
    deadline = time.monotonic() + seconds
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return
        if cancel_event.wait(min(interval, remaining)):
            return
