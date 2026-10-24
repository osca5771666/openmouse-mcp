import assert from "node:assert/strict";
import test from "node:test";

await import("../content/humanize.js");

const { clamp, createTrajectory } = globalThis.MouseMcpHumanize;

test("clamp keeps browser coordinates inside the viewport", () => {
  assert.equal(clamp(-5, 0, 100), 0);
  assert.equal(clamp(50, 0, 100), 50);
  assert.equal(clamp(105, 0, 100), 100);
});

test("trajectory ends exactly at the target and has intermediate points", () => {
  const trajectory = createTrajectory({ x: 2, y: 3 }, { x: 700, y: 420 });
  const last = trajectory.at(-1);

  assert.deepEqual(last.point, { x: 700, y: 420 });
  assert.ok(trajectory.length >= 18);
  assert.ok(trajectory.some((step) => step.delay > 0));
});

test("trajectory is not a single instant jump", () => {
  const trajectory = createTrajectory({ x: 0, y: 0 }, { x: 900, y: 500 });
  const unique = new Set(
    trajectory.slice(0, -1).map((step) => `${step.point.x.toFixed(2)},${step.point.y.toFixed(2)}`),
  );

  assert.ok(unique.size > 10);
});
