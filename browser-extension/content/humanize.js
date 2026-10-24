(() => {
  "use strict";

  const clamp = (value, minimum, maximum) =>
    Math.max(minimum, Math.min(maximum, value));

  const randomBetween = (minimum, maximum) =>
    minimum + Math.random() * (maximum - minimum);

  const easeInOutCubic = (t) =>
    t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;

  const cubicBezier = (p0, p1, p2, p3, t) => {
    const u = 1 - t;
    return {
      x:
        u * u * u * p0.x +
        3 * u * u * t * p1.x +
        3 * u * t * t * p2.x +
        t * t * t * p3.x,
      y:
        u * u * u * p0.y +
        3 * u * u * t * p1.y +
        3 * u * t * t * p2.y +
        t * t * t * p3.y,
    };
  };

  const createTrajectory = (start, end) => {
    const dx = end.x - start.x;
    const dy = end.y - start.y;
    const distance = Math.hypot(dx, dy);
    if (distance < 0.5) {
      return [{ point: { ...end }, delay: 0 }];
    }

    const length = Math.max(distance, 1);
    const perpX = -dy / length;
    const perpY = dx / length;
    const bend1 = randomBetween(-0.13, 0.13) * Math.min(distance, 650);
    const bend2 = randomBetween(-0.13, 0.13) * Math.min(distance, 650);
    const p1 = {
      x: start.x + dx * 0.27 + perpX * bend1,
      y: start.y + dy * 0.27 + perpY * bend1,
    };
    const p2 = {
      x: start.x + dx * 0.73 + perpX * bend2,
      y: start.y + dy * 0.73 + perpY * bend2,
    };
    const duration = clamp(
      0.2 + distance / 1500 + randomBetween(-0.04, 0.08),
      0.24,
      1.1,
    );
    const steps = Math.round(
      clamp(duration * (55 + randomBetween(-8, 8)), 18, 72),
    );
    const pauseAt = Math.floor(
      randomBetween(Math.max(6, steps / 3), Math.max(7, (steps * 3) / 5)),
    );
    const pauseDuration =
      Math.random() < 0.72 ? randomBetween(0.035, 0.14) : 0;
    const jitterScale = Math.min(1.35, 0.25 + distance / 950);
    const phase = randomBetween(0, Math.PI * 2);
    const wobbleFrequency = randomBetween(2.2, 3.4);
    const trajectory = [];
    let previousTime = 0;

    for (let index = 1; index <= steps; index += 1) {
      const rawT = index / steps;
      const t = easeInOutCubic(rawT);
      const point = cubicBezier(start, p1, p2, end, t);
      const taper = Math.sin(Math.PI * t);
      const wobble = Math.sin(t * Math.PI * 2 * wobbleFrequency + phase);
      const jitterX = randomBetween(-jitterScale, jitterScale) * taper;
      const jitterY = randomBetween(-jitterScale, jitterScale) * taper;
      let targetTime = duration * rawT;
      if (index === pauseAt && pauseDuration) {
        targetTime += pauseDuration;
      }
      trajectory.push({
        point: {
          x: point.x + jitterX + wobble * 0.22,
          y: point.y + jitterY,
        },
        delay: Math.max(0, targetTime - previousTime),
      });
      previousTime = targetTime;
    }
    trajectory[trajectory.length - 1].point = { ...end };
    return trajectory;
  };

  globalThis.MouseMcpHumanize = {
    clamp,
    createTrajectory,
    randomBetween,
  };
})();
