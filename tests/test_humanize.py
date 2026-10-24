from __future__ import annotations

import random

from mouse_mcp.humanize import Point, build_trajectory, random_action_delay


def test_trajectory_reaches_exact_target_with_many_steps() -> None:
    trajectory = build_trajectory(Point(10, 20), Point(800, 420), random.Random(7))

    assert len(trajectory) >= 18
    assert trajectory[-1].point == Point(800, 420)
    assert sum(step.delay for step in trajectory) >= 0.24
    assert any(step.delay > 0 for step in trajectory)


def test_trajectory_is_not_a_straight_instant_jump() -> None:
    trajectory = build_trajectory(Point(0, 0), Point(900, 500), random.Random(21))
    intermediate = [(step.point.x, step.point.y) for step in trajectory[:-1]]
    expected_y = [point[0] * (500 / 900) for point in intermediate]
    max_deviation = max(
        abs(point[1] - line_y) for point, line_y in zip(intermediate, expected_y, strict=True)
    )

    assert len(set((round(x), round(y)) for x, y in intermediate)) > 10
    assert max_deviation > 1.0
    assert trajectory[-1].point.x == 900
    assert trajectory[-1].point.y == 500


def test_action_delay_stays_inside_specification() -> None:
    rng = random.Random(3)
    delays = [random_action_delay(rng=rng) for _ in range(200)]

    assert min(delays) >= 0.2
    assert max(delays) <= 1.3
